"""Authenticated maintenance controls. Uploaded archives are data, never executable SQL."""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession, get_current_user, require_admin
from app.core import database
from app.core.http import get_client_ip
from app.core.rate_limiter import MAX_ATTEMPTS, credential_limiter
from app.core.security import verify_password
from app.models.user_account import UserAccount
from app.schemas.enums import ActiveStatusEnum
from app.services import audit, backup_archive, maintenance_state, power_control, configuration
from app.services.audit import AuditAction
from app.services.backup_restore import get_service
from app.services.camera_manager import camera_manager
from app.services.runtime_operations import coordinator, finish_on_disconnect, run_blocking, station_lock

router = APIRouter(prefix='/config', tags=['Maintenance'])


class OperationRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    operation_id: uuid.UUID


class RestoreRequest(OperationRequest):
    validation_id: uuid.UUID
    token: str = Field(min_length=20, max_length=200)
    password: SecretStr
    confirmation: str


class RecoveryRequest(BaseModel):
    password: SecretStr


async def reauthenticate(db, admin, password=None):
    current = await db.scalar(select(UserAccount).where(UserAccount.id == admin.id)
        .options(selectinload(UserAccount.role)).execution_options(populate_existing=True))
    if (current is None or current.status != ActiveStatusEnum.ACTIVE or not current.role
            or current.role.name != 'Admin'):
        raise HTTPException(403, 'Active administrator required')
    if password is None:
        return
    # Failures are attached to the raised error: the audit handler writes them after the
    # request transaction has rolled back, so no row lock is held while writing.
    key = f'reauth:{current.id}'
    subject = f'Maintenance re-authentication for {audit.quoted(current.username)}'
    locked, remaining = credential_limiter.is_locked(key)
    if locked:
        raise audit.attach(too_many_attempts(remaining), AuditAction.LOGIN_BLOCKED,
                           f'{subject} refused: locked for {remaining} more seconds', actor=current)
    if not await run_blocking(verify_password, password.get_secret_value(), current.password_hash):
        now_locked, info = credential_limiter.record_failure(key)
        failed = f'{subject} failed: incorrect administrator password'
        if now_locked:
            error = audit.attach(too_many_attempts(info), AuditAction.REAUTH_FAILED, failed,
                                 actor=current)
            raise audit.attach(error, AuditAction.ACCOUNT_LOCKED,
                               f'{subject} locked for {info} seconds after {MAX_ATTEMPTS} '
                               'incorrect passwords', actor=current)
        raise audit.attach(HTTPException(403, 'Administrator password is incorrect'),
                           AuditAction.REAUTH_FAILED, f'{failed} ({info} attempts left)',
                           actor=current)
    credential_limiter.record_success(key)


def too_many_attempts(seconds):
    return HTTPException(
        429, f'Too many incorrect administrator passwords. Try again in {seconds} seconds.',
        headers={'Retry-After': str(max(seconds, 1))})


def session_digest(request):
    return hashlib.sha256(request.headers.get('authorization', '').encode()).hexdigest()


def fresh_authorization(request, actor_id, password=None):
    """Recheck the original token in a fresh transaction after queueing/draining.

    The dependency's ORM account may have been replaced or revoked while waiting.
    Never authorize delayed maintenance using that cached object.
    """
    header = request.headers.get('authorization', '')

    async def authorize():
        async with database.async_session_factory() as session:
            current = await get_current_user(session, header)
            await require_admin(current)
            if current.id != actor_id:
                raise HTTPException(403, 'Operation belongs to another administrator')
            await reauthenticate(session, current, password)
    return authorize


async def safe_operation(awaitable):
    try:
        return await finish_on_disconnect(awaitable)
    except backup_archive.ArchiveError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, 'Storage operation failed; check available disk space and permissions') from exc


@router.get('/maintenance')
async def maintenance_status(db: DbSession, admin: AdminUser):
    state = await maintenance_state.get_state(db)
    return {**coordinator.status(), 'power': state.power, 'retention': state.retention}


@router.get('/operations/{operation_id}')
async def operation_status(operation_id: uuid.UUID, db: DbSession, admin: AdminUser):
    result = await maintenance_state.operation_result(db, str(operation_id))
    if not result:
        raise HTTPException(404, 'Operation not found')
    if result.get('actor_id') != str(admin.id):
        raise HTTPException(403, 'This operation belongs to another administrator')
    return result


@router.post('/backups')
async def create_backup(body: OperationRequest, db: DbSession, admin: AdminUser, request: Request):
    await reauthenticate(db, admin)
    return await safe_operation(get_service().backup(body.operation_id, admin.id,
        authorize=fresh_authorization(request, admin.id), actor_name=admin.full_name,
        client_ip=get_client_ip(request)))


@router.get('/backups/{operation_id}')
async def download_backup(operation_id: uuid.UUID, db: DbSession, admin: AdminUser,
                          request: Request):
    result = await operation_status(operation_id, db, admin)
    if result['kind'] != 'backup' or result['status'] != 'completed':
        raise HTTPException(409, 'Backup is not available')
    path = get_service().directory(operation_id) / 'station.zip'
    backup_archive._no_links(path)
    if not path.is_file():
        raise HTTPException(410, 'Backup file is no longer available')
    # The archive holds every record and credential hash: no audit row, no download.
    created = (result.get('manifest') or {}).get('created_at')
    await audit.emit(AuditAction.BACKUP_DOWNLOADED,
                     f'Backup {operation_id} downloaded: archive created {audit.clean(created)}, '
                     f'{path.stat().st_size} bytes; archive contains credential hashes',
                     actor=admin, ip=get_client_ip(request), required=True)
    return FileResponse(path, media_type='application/zip', filename=f'bananavision-{operation_id}.zip',
                        headers={'Cache-Control': 'no-store'})


@router.post('/restores/validate')
async def validate_backup(request: Request, db: DbSession, admin: AdminUser):
    # Raw octet-stream avoids unbounded multipart spooling before our size checks.
    identifier = uuid.uuid4()
    service = get_service()
    async with coordinator.operation():
        await reauthenticate(db, admin)
        directory = service.directory(identifier)
        path = directory / 'upload.zip'
        length = 0
        try:
            with path.open('xb') as output:
                async for chunk in request.stream():
                    length += len(chunk)
                    if length > backup_archive.MAX_ARCHIVE_BYTES:
                        raise audit.attach(
                            HTTPException(413, 'Backup exceeds upload limit'),
                            AuditAction.RESTORE_VALIDATION_FAILED,
                            f'Backup upload {identifier} rejected: exceeds the '
                            f'{backup_archive.MAX_ARCHIVE_BYTES} byte upload limit',
                            actor=admin)
                    backup_archive._space(directory, len(chunk))
                    output.write(chunk)
            return await safe_operation(service.validate(
                path, identifier, admin.id, session_digest(request), actor_name=admin.full_name,
                client_ip=get_client_ip(request)))
        except BaseException:
            path.unlink(missing_ok=True)
            raise


@router.post('/restores')
async def restore_backup(body: RestoreRequest, request: Request, db: DbSession, admin: AdminUser):
    if body.confirmation != 'REPLACE':
        raise HTTPException(422, 'Type REPLACE to confirm station replacement')
    await reauthenticate(db, admin, body.password)
    return await safe_operation(get_service().restore(body.operation_id, body.validation_id,
        body.token, admin.id, session_digest(request),
        authorize=fresh_authorization(request, admin.id, body.password),
        actor_name=admin.full_name, client_ip=get_client_ip(request)))


@router.post('/restart')
async def restart(body: OperationRequest, db: DbSession, admin: AdminUser, request: Request):
    await reauthenticate(db, admin)
    return await safe_operation(power_control.request_power('restart', str(body.operation_id), admin.id,
        authorize=fresh_authorization(request, admin.id), client_ip=get_client_ip(request)))


@router.post('/shutdown')
async def shutdown(body: OperationRequest, db: DbSession, admin: AdminUser, request: Request):
    await reauthenticate(db, admin)
    return await safe_operation(power_control.request_power('shutdown', str(body.operation_id), admin.id,
        authorize=fresh_authorization(request, admin.id), client_ip=get_client_ip(request)))


@router.post('/power/cancel')
async def cancel_power(body: RecoveryRequest, db: DbSession, admin: AdminUser, request: Request):
    await reauthenticate(db, admin, body.password)
    return await safe_operation(power_control.cancel_power(
        authorize=fresh_authorization(request, admin.id, body.password), actor_id=admin.id,
        client_ip=get_client_ip(request)))


@router.post('/maintenance/recover')
async def recover(body: RecoveryRequest, db: DbSession, admin: AdminUser, request: Request):
    await reauthenticate(db, admin, body.password)
    service = get_service()
    authorize = fresh_authorization(request, admin.id, body.password)
    actor, ip = admin, get_client_ip(request)
    async def recover_station():
        async with service._lock:
            await authorize()
            state = await maintenance_state.get_state(db)
            if state.power and state.power.get('status') in {'dispatching', 'accepted', 'unknown'}:
                raise HTTPException(409, 'Cancel the pending power operation first')
            if coordinator.state != 'recovery-required':
                raise HTTPException(409, 'Station does not require recovery')
            before = coordinator.state
            await service.recover()
            if coordinator.state != 'ready':
                await coordinator.finish_recovery()
            await audit.emit(AuditAction.MAINTENANCE_RECOVERED,
                             f'Station recovery completed: {before} → {coordinator.state}',
                             actor=actor, ip=ip)
            # Events kept while admission was closed are written now that the station is ready.
            await audit.flush_deferred()
        return coordinator.status()
    return await safe_operation(recover_station())


@router.post('/maintenance/apply')
async def apply_cameras(body: OperationRequest, db: DbSession, admin: AdminUser, request: Request):
    actor_id, actor_name, ip = admin.id, getattr(admin, 'full_name', None), get_client_ip(request)
    authorize = fresh_authorization(request, actor_id)
    async def apply():
        async with get_service()._lock:
            await authorize()
            identifier = str(body.operation_id)
            previous = await maintenance_state.operation_result(db, identifier)
            if previous:
                if previous.get('actor_id') != str(actor_id) or previous.get('kind') != 'camera-configuration':
                    raise HTTPException(409, 'Operation ID already used')
                if previous.get('status') == 'completed':
                    return previous['configuration']
                raise HTTPException(409, 'Previous camera application is incomplete; use a new operation ID to retry')
            async with coordinator.exclusive('camera-configuration'):
                await authorize()
                config = await configuration.get_config(db)
                result = {'id': identifier, 'kind': 'camera-configuration', 'actor_id': str(actor_id), 'status': 'applying'}
                await maintenance_state.record_operation(db, identifier, result)
                await db.commit()
                async with station_lock:
                    await configuration.apply_camera_config(config)
                    await configuration.sync_devices(db)
                response = configuration.config_response(config)
                await maintenance_state.record_operation(db, identifier, {**result, 'status': 'completed', 'configuration': response})
                # This request owns the exclusive section; the row commits with the outcome.
                await audit.record(db, AuditAction.CONFIG_APPLIED,
                                   f'Saved camera configuration revision {response["revision"]} '
                                   f'applied (operation {identifier}): '
                                   f'{response["application_status"]}; {camera_results(response)}',
                                   actor_id=actor_id, actor_name=actor_name, ip=ip)
                await db.commit()
                return response
    return await safe_operation(apply())


def camera_results(response):
    """'CAM-001 device 0 online, ...' for each saved camera slot."""
    online = set(camera_manager.online_cameras)
    names = [name for name in response['camera_ids'].split(', ') if name]
    return ', '.join(
        f"{audit.clean(name, 40)} device {index} {'online' if index in online else 'offline'}"
        for name, index in zip(names, response['camera_device_ids'], strict=False))
