"""Authenticated maintenance controls. Uploaded archives are data, never executable SQL."""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession
from app.core.security import verify_password
from app.models.user_account import UserAccount
from app.schemas.enums import ActiveStatusEnum
from app.services import backup_archive, maintenance_state, power_control, configuration
from app.services.backup_restore import get_service
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
    if password is not None and not await run_blocking(verify_password, password.get_secret_value(), current.password_hash):
        raise HTTPException(403, 'Administrator password is incorrect')


def session_digest(request):
    return hashlib.sha256(request.headers.get('authorization', '').encode()).hexdigest()


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
async def create_backup(body: OperationRequest, db: DbSession, admin: AdminUser):
    await reauthenticate(db, admin)
    return await safe_operation(get_service().backup(body.operation_id, admin.id))


@router.get('/backups/{operation_id}')
async def download_backup(operation_id: uuid.UUID, db: DbSession, admin: AdminUser):
    result = await operation_status(operation_id, db, admin)
    if result['kind'] != 'backup' or result['status'] != 'completed':
        raise HTTPException(409, 'Backup is not available')
    path = get_service().directory(operation_id) / 'station.zip'
    backup_archive._no_links(path)
    if not path.is_file():
        raise HTTPException(410, 'Backup file is no longer available')
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
                        raise HTTPException(413, 'Backup exceeds upload limit')
                    backup_archive._space(directory, len(chunk))
                    output.write(chunk)
            return await safe_operation(service.validate(path, identifier, admin.id, session_digest(request)))
        except BaseException:
            path.unlink(missing_ok=True)
            raise


@router.post('/restores')
async def restore_backup(body: RestoreRequest, request: Request, db: DbSession, admin: AdminUser):
    if body.confirmation != 'REPLACE':
        raise HTTPException(422, 'Type REPLACE to confirm station replacement')
    await reauthenticate(db, admin, body.password)
    return await safe_operation(get_service().restore(body.operation_id, body.validation_id,
        body.token, admin.id, session_digest(request)))


@router.post('/restart')
async def restart(body: OperationRequest, db: DbSession, admin: AdminUser):
    await reauthenticate(db, admin)
    return await safe_operation(power_control.request_power('restart', str(body.operation_id), admin.id))


@router.post('/shutdown')
async def shutdown(body: OperationRequest, db: DbSession, admin: AdminUser):
    await reauthenticate(db, admin)
    return await safe_operation(power_control.request_power('shutdown', str(body.operation_id), admin.id))


@router.post('/power/cancel')
async def cancel_power(body: RecoveryRequest, db: DbSession, admin: AdminUser):
    await reauthenticate(db, admin, body.password)
    return await safe_operation(power_control.cancel_power())


@router.post('/maintenance/recover')
async def recover(body: RecoveryRequest, db: DbSession, admin: AdminUser):
    await reauthenticate(db, admin, body.password)
    service = get_service()
    async def recover_station():
        async with service._lock:
            state = await maintenance_state.get_state(db)
            if state.power and state.power.get('status') in {'dispatching', 'accepted', 'unknown'}:
                raise HTTPException(409, 'Cancel the pending power operation first')
            if coordinator.state != 'recovery-required':
                raise HTTPException(409, 'Station does not require recovery')
            await service.recover()
            if coordinator.state != 'ready':
                await coordinator.finish_recovery()
        return coordinator.status()
    return await safe_operation(recover_station())


@router.post('/maintenance/apply')
async def apply_cameras(body: OperationRequest, db: DbSession, admin: AdminUser):
    async def apply():
        async with get_service()._lock:
            identifier = str(body.operation_id)
            previous = await maintenance_state.operation_result(db, identifier)
            if previous:
                if previous.get('actor_id') != str(admin.id) or previous.get('kind') != 'camera-configuration':
                    raise HTTPException(409, 'Operation ID already used')
                if previous.get('status') == 'completed':
                    return previous['configuration']
                raise HTTPException(409, 'Previous camera application is incomplete; use a new operation ID to retry')
            async with coordinator.exclusive('camera-configuration'):
                config = await configuration.get_config(db)
                result = {'id': identifier, 'kind': 'camera-configuration', 'actor_id': str(admin.id), 'status': 'applying'}
                await maintenance_state.record_operation(db, identifier, result)
                await db.commit()
                async with station_lock:
                    await configuration.apply_camera_config(config)
                    await configuration.sync_devices(db)
                response = configuration.config_response(config)
                await maintenance_state.record_operation(db, identifier, {**result, 'status': 'completed', 'configuration': response})
                await db.commit()
                return response
    return await safe_operation(apply())
