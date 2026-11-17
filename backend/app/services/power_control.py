"""Drained, durable and idempotent OS power requests; acceptance is not completion."""
import asyncio
import platform
import subprocess
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.time import now_manila
from app.models.user_account import UserAccount
from app.services import audit
from app.services.audit import AuditAction
from app.services.runtime_operations import coordinator, run_blocking, station_lock
from app.services.maintenance_state import get_state, record_operation, operation_result


def boot_identity():
    system = platform.system().lower()
    try:
        if system == 'linux':
            return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        command = (['powershell', '-NoProfile', '-NonInteractive', '-Command',
                    '(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString("o")']
                   if system == 'windows' else ['sysctl', '-n', 'kern.boottime'])
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False,
                                **({'creationflags': subprocess.CREATE_NO_WINDOW} if system == 'windows' else {}))
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


async def _schedule_power_action(action: str):
    if action not in {'restart', 'shutdown', 'cancel'}:
        raise HTTPException(422, 'Unsupported power action')
    system = platform.system().lower()
    if system == 'windows':
        command = ['shutdown', '/a'] if action == 'cancel' else ['shutdown', '/r' if action == 'restart' else '/s', '/t', '10']
    elif system in {'linux', 'darwin'}:
        command = ['sudo', '-n', 'shutdown', '-c'] if action == 'cancel' else ['sudo', '-n', 'shutdown', '-r' if action == 'restart' else '-h', '+1']
    else:
        raise HTTPException(503, 'Power commands are unsupported on this operating system')
    try:
        extra_kwargs = {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)} if system == 'windows' else {}
        result = await run_blocking(subprocess.run, command, capture_output=True, text=True, timeout=5, check=False,
                                    **extra_kwargs)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, 'Power command outcome is unknown; station admission remains closed') from exc
    except OSError as exc:
        raise HTTPException(503, 'Power command could not be started') from exc
    if result.returncode != 0:
        raise HTTPException(503, 'Operating system rejected the power command; check host permissions')


async def schedule_power_action(action):
    """Compatibility entry point for internal command tests; HTTP uses request_power."""
    if station_lock.locked():
        raise HTTPException(409, 'An active hardware operation must finish first')
    async with station_lock:
        await _schedule_power_action(action)


_power_lock = asyncio.Lock()


async def _record(db, action, details, actor_id=None, ip=None):
    """Audit row in the caller's power-state transaction; an unknown account keeps no key."""
    if actor_id is not None:
        actor_id = uuid.UUID(str(actor_id))
        if await db.scalar(select(UserAccount.id).where(UserAccount.id == actor_id)) is None:
            actor_id = None
    await audit.record(db, action, details, actor_id=actor_id, ip=ip)


async def request_power(action, operation_id, actor_id, *, authorize=None, client_ip=None):
    async with _power_lock:
        if authorize:
            await authorize()
        try:
            return await _request_power(action, operation_id, actor_id, authorize=authorize,
                                        client_ip=client_ip)
        finally:
            # A failed dispatch reopens admission; write events kept while it was closed.
            await audit.flush_deferred(sessions=async_session_factory)


async def _request_power(action, operation_id, actor_id, *, authorize=None, client_ip=None):
    async with async_session_factory() as db:
        previous = await operation_result(db, operation_id)
        if previous:
            if previous.get('kind') != action or previous.get('actor_id') != str(actor_id):
                raise HTTPException(409, 'Operation ID already used')
            return previous
    async with coordinator.exclusive(action):
        if authorize:
            await authorize()
        boot = await run_blocking(boot_identity)
        if not boot:
            # The owner writes at once; no row lock is held here.
            await audit.emit(AuditAction.POWER_FAILED,
                             f'Station {action} (operation {operation_id}) not sent: cannot '
                             'establish host boot identity', actor_id=actor_id, ip=client_ip,
                             sessions=async_session_factory)
            raise HTTPException(503, 'Cannot establish host boot identity; no power command was sent')
        result = {'id': operation_id, 'kind': action, 'actor_id': str(actor_id), 'status': 'dispatching',
                  'boot_id': boot, 'requested_at': now_manila().isoformat()}
        async with async_session_factory() as db:
            state = await get_state(db, lock=True)
            state.power = result
            await record_operation(db, operation_id, result)
            await _record(db, f'system_{action}',
                          f'Station {action} requested (operation {operation_id}); '
                          'intent saved before dispatch', actor_id, client_ip)
            await db.commit()
        # A crash after intent persistence is ambiguous, including before dispatch itself.
        coordinator.block('recovery-required')
        try:
            await _schedule_power_action(action)
        except HTTPException as exc:
            result = {**result, 'status': 'unknown' if exc.status_code == 504 else 'failed', 'message': exc.detail}
        else:
            result = {**result, 'status': 'accepted', 'message': f'Operating system accepted the scheduled {action}'}
        async with async_session_factory() as db:
            state = await get_state(db, lock=True)
            state.power = result
            await record_operation(db, operation_id, result)
            if result['status'] != 'accepted':
                outcome = 'outcome unknown' if result['status'] == 'unknown' else 'failed'
                await _record(db, AuditAction.POWER_FAILED,
                              f'Station {action} (operation {operation_id}) {outcome}: '
                              f'{audit.clean(result["message"], 160)}', actor_id, client_ip)
            await db.commit()
        if result['status'] == 'failed':
            coordinator.resume()
        elif result['status'] == 'accepted':
            coordinator.block('power-accepted')
        return result


async def reconcile_power():
    async with async_session_factory() as db:
        state = await get_state(db)
        power = state.power
        if power and power.get('status') in {'dispatching', 'accepted', 'unknown'}:
            boot = await run_blocking(boot_identity)
            if boot and boot != power.get('boot_id'):
                result = {**power, 'status': 'completed', 'message': 'A new host boot was verified'}
                state.power = result
                await record_operation(db, power['id'], result)
                await _record(db, AuditAction.POWER_COMPLETED,
                              f"Station {power['kind']} (operation {power['id']}) completed: "
                              'a new host boot was verified', power.get('actor_id'))
            else:
                coordinator.kind = power['kind']
                coordinator.block('power-accepted' if power['status'] == 'accepted' else 'recovery-required')
        await db.commit()


async def cancel_power(*, authorize=None, actor_id=None, client_ip=None):
    async with _power_lock:
        if authorize:
            await authorize()
        result = await _cancel_power(actor_id, client_ip)
    await audit.flush_deferred(sessions=async_session_factory)
    return result


async def _cancel_power(actor_id=None, client_ip=None):
    """Caller has reauthenticated; only OS-confirmed cancellation reopens admission."""
    async with async_session_factory() as db:
        state = await get_state(db)
        power = state.power
        if power and coordinator.kind not in {None, power.get('kind')}:
            raise HTTPException(409, 'Another maintenance operation owns station admission')
        if power and power.get('status') == 'cancelled':
            if coordinator.state != 'ready':
                await coordinator.finish_recovery()
            return power
        if not power or power.get('status') not in {'dispatching', 'accepted', 'unknown'}:
            raise HTTPException(409, 'There is no pending power operation')
        subject = f"Station {power['kind']} (operation {power['id']})"
        try:
            await _schedule_power_action('cancel')
        except HTTPException as exc:
            # Admission stays closed and no restore can run, so the row is written at once.
            await audit.emit(AuditAction.POWER_FAILED,
                             f'Cancel of {subject} failed: {audit.clean(exc.detail, 160)}',
                             actor_id=actor_id, ip=client_ip, sessions=async_session_factory,
                             owner=True)
            raise
        result = {**power, 'status': 'cancelled', 'message': 'Operating system confirmed cancellation'}
        state.power = result
        await record_operation(db, power['id'], result)
        await _record(db, AuditAction.POWER_CANCELLED,
                      f'{subject} cancelled; operating system confirmed the cancellation',
                      actor_id, client_ip)
        await db.commit()
    await coordinator.finish_recovery()
    return result
