"""Drained, durable and idempotent OS power requests; acceptance is not completion."""
import asyncio
import platform
import subprocess
from pathlib import Path

from fastapi import HTTPException

from app.core.database import async_session_factory
from app.core.time import now_manila
from app.models.activity_log import ActivityLog
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
        result = await run_blocking(subprocess.run, command, capture_output=True, text=True, timeout=5, check=False,
                                    **({'creationflags': subprocess.CREATE_NO_WINDOW} if system == 'windows' else {}))
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


async def request_power(action, operation_id, actor_id):
    async with async_session_factory() as db:
        previous = await operation_result(db, operation_id)
        if previous:
            if previous.get('kind') != action or previous.get('actor_id') != str(actor_id):
                raise HTTPException(409, 'Operation ID already used')
            return previous
    async with coordinator.exclusive(action):
        boot = await run_blocking(boot_identity)
        if not boot:
            raise HTTPException(503, 'Cannot establish host boot identity; no power command was sent')
        result = {'id': operation_id, 'kind': action, 'actor_id': str(actor_id), 'status': 'dispatching',
                  'boot_id': boot, 'requested_at': now_manila().isoformat()}
        async with async_session_factory() as db:
            state = await get_state(db, lock=True)
            state.power = result
            await record_operation(db, operation_id, result)
            db.add(ActivityLog(user_id=actor_id, action=f'system_{action}', details=f'Power intent {operation_id} persisted before dispatch'))
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
            else:
                coordinator.block('power-accepted' if power['status'] == 'accepted' else 'recovery-required')
        await db.commit()


async def cancel_power():
    """Caller has reauthenticated; only OS-confirmed cancellation reopens admission."""
    async with async_session_factory() as db:
        state = await get_state(db)
        power = state.power
        if not power or power.get('status') not in {'dispatching', 'accepted', 'unknown'}:
            raise HTTPException(409, 'There is no pending power operation')
        await _schedule_power_action('cancel')
        result = {**power, 'status': 'cancelled', 'message': 'Operating system confirmed cancellation'}
        state.power = result
        await record_operation(db, power['id'], result)
        await db.commit()
    coordinator.resume()
    return result
