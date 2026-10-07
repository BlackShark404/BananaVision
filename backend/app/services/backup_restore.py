"""Private, validated station archives and recoverable in-place replacement.

The journal and control table are deliberately outside replaceable application data.
Every file promotion is recoverable from a freshly queried database commit marker.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select, delete, text, func

from app.core.database import Base
from app.core.time import now_manila
from app.models.maintenance_state import MaintenanceState
from app.services import backup_archive as archive
from app.services import maintenance_state as state_store
from app.services.runtime_operations import coordinator, run_blocking


def _sync_parent(path):
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def sync_tree(root: Path):
    for path in root.rglob('*'):
        archive._no_links(path)
        if path.is_file():
            with path.open('r+b') as output:
                os.fsync(output.fileno())
        elif path.is_dir():
            _sync_parent(path)
    _sync_parent(root)


def atomic_json(path: Path, value):
    archive._no_links(path)
    partial = path.with_suffix('.tmp')
    with partial.open('w', encoding='utf-8') as output:
        os.chmod(partial, 0o600)
        json.dump(value, output, ensure_ascii=False, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)
    _sync_parent(path.parent)


def reconcile_evidence(root: Path, old: Path, new: Path, *, committed: bool):
    """Never delete a competing tree: retain it for diagnosis/compensation."""
    for path in (root, old, new):
        archive._no_links(path)
    if committed:
        if new.exists():
            if root.exists():
                if old.exists():
                    raise archive.ArchiveError('Ambiguous evidence trees; manual recovery required')
                root.rename(old)
            new.rename(root)
        if not root.is_dir():
            raise archive.ArchiveError('Committed evidence tree is missing')
    elif old.exists():
        if root.exists():
            if new.exists():
                raise archive.ArchiveError('Ambiguous rollback evidence trees')
            root.rename(new)
        old.rename(root)
    elif not root.is_dir():
        raise archive.ArchiveError('Original evidence tree is missing')
    _sync_parent(root.parent)


async def reset_sequences(db, dialect):
    if dialect != 'postgresql':
        return
    for table in archive.application_tables():
        for column in table.primary_key:
            if column.type.python_type is not int:
                continue
            # Names originate exclusively in metadata/catalogs, never in uploaded SQL.
            row = (await db.execute(text('''SELECT n.nspname, c.relname FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace=n.oid
                WHERE c.oid=pg_get_serial_sequence(:table, :column)::regclass'''),
                {'table': table.name, 'column': column.name})).first()
            if row:
                value = (await db.execute(select(func.max(column)))).scalar() or 0
                name = '.'.join('"' + part.replace('"', '""') + '"' for part in row)
                await db.execute(text(f'ALTER SEQUENCE {name} RESTART WITH {int(value) + 1}'))


class MaintenanceService:
    def __init__(self, engine, session_factory, capture_root: Path):
        self.engine, self.sessions = engine, session_factory
        self.capture_root = Path(capture_root).absolute()
        self.root = self.capture_root.parent / '.bananavision-maintenance'
        self.journal = self.root / 'restore-journal.json'
        self._lock = asyncio.Lock()
        self.hardware_refresh = None

    def prepare(self):
        archive._no_links(self.root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        if os.name == 'nt':
            identity = subprocess.run(['whoami'], capture_output=True, text=True, timeout=5, check=True,
                                      creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
            subprocess.run(['icacls', str(self.root), '/inheritance:r', '/grant:r',
                            f'{identity}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                           capture_output=True, timeout=10, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

        self.cleanup_temporary()

    def cleanup_temporary(self):
        # Validation tokens last 15 minutes; leave a full day of grace for failures.
        # Completed backups and every rollback/recovery directory are retained.
        protected = set()
        if self.journal.exists():
            journal = json.loads(self.journal.read_text(encoding='utf-8'))
            protected = {journal.get('id'), journal.get('validation_id')}
        for directory in self.root.iterdir():
            if directory.name in protected:
                continue
            try:
                uuid.UUID(directory.name)
            except ValueError:
                continue
            archive._no_links(directory)
            if not directory.is_dir() or (directory / 'station.zip').exists() or (directory / 'rollback.zip').exists():
                continue
            paths = [directory, *directory.rglob('*')]
            for path in paths:
                archive._no_links(path)
            if max(path.stat().st_mtime for path in paths) < time.time() - 86400:
                shutil.rmtree(directory)

    def directory(self, identifier):
        identifier = str(uuid.UUID(str(identifier)))
        path = self.root / identifier
        archive._no_links(path)
        path.mkdir(mode=0o700, exist_ok=True)
        return path

    async def saved_result(self, identifier, actor_id, kind):
        async with self.sessions() as db:
            result = await state_store.operation_result(db, str(identifier))
        if result and (result.get('actor_id') != str(actor_id) or result.get('kind') != kind):
            raise HTTPException(409, 'Operation ID already used')
        return result

    async def save_result(self, result):
        async with self.sessions() as db:
            await state_store.record_operation(db, result['id'], result)
            await db.commit()

    async def backup(self, identifier, actor_id):
        async with self._lock:
            previous = await self.saved_result(identifier, actor_id, 'backup')
            if previous:
                return previous
            async with coordinator.exclusive('backup'):
                await run_blocking(self.cleanup_temporary)
                directory = self.directory(identifier)
                result = {'id': str(identifier), 'kind': 'backup', 'actor_id': str(actor_id), 'status': 'creating'}
                await self.save_result(result)
                try:
                    async with self.sessions() as db:
                        manifest = await archive.create_archive(db, self.capture_root, directory / 'station.zip')
                    result.update(status='completed', filename='station.zip', manifest=self.summary(manifest))
                except Exception:
                    result.update(status='failed', message='Backup creation failed; no complete backup is available')
                    await self.save_result(result)
                    raise
                await self.save_result(result)
                return result

    @staticmethod
    def summary(manifest):
        return {'created_at': manifest['created_at'], 'version': manifest['version'],
                'tables': {name: row['count'] for name, row in manifest['tables'].items()},
                'evidence_files': len(manifest['files']), 'prerequisites': manifest['prerequisites']}

    async def check_database(self, validated):
        """Validate actual DB constraints in a temporary transactional PG schema."""
        if self.engine.dialect.name != 'postgresql':
            # The archive's disk-backed validator covers SQLite test fixtures.
            return
        schema = 'bv_validate_' + uuid.uuid4().hex
        async with self.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(Base.metadata.create_all)
                await archive.restore_rows(connection, validated)
            finally:
                await transaction.rollback()  # Drops staging data, schema, types, sequences together.
                # asyncpg caches prepared statements and enum OIDs per physical connection.
                # A connection that observed now-dropped staging types must not rejoin the pool.
                await connection.invalidate()

    async def validate(self, uploaded: Path, identifier, actor_id, session_digest):
        coordinator.assert_ready()
        validated = await run_blocking(archive.validate_archive, uploaded, self.directory(identifier) / 'staging')
        await self.check_database(validated)
        # Saved configuration must be semantically applicable, not just SQL-valid.
        from app.services.configuration import _validated_values
        from app.config import get_settings
        configs = list(validated.iter_rows('system_config'))
        if not configs:
            raise archive.ArchiveError('Backup is missing saved configuration')
        canonical = [row for row in configs if row['canonical_key'] == 1]
        candidates = canonical or configs
        if not any(self._valid_config(row, _validated_values, get_settings) for row in candidates):
            raise archive.ArchiveError('Backup has no valid configuration')
        async with self.sessions() as db:
            state = await state_store.get_state(db)
            generation = state.auth_generation
            await db.commit()
        token = secrets.token_urlsafe(32)
        expires = now_manila() + timedelta(minutes=15)
        descriptor = {'actor_id': str(actor_id), 'session': session_digest, 'generation': generation,
                      'digest': validated.archive_sha256, 'token': hashlib.sha256(token.encode()).hexdigest(),
                      'expires_at': expires.isoformat(), 'consumed': False}
        atomic_json(self.directory(identifier) / 'validation.json', descriptor)
        await run_blocking(shutil.rmtree, validated.staging_root)
        return {'validation_id': str(identifier), 'token': token, 'expires_at': expires.isoformat(),
                'manifest': self.summary(validated.manifest)}

    @staticmethod
    def _valid_config(row, validate, settings):
        try:
            validate(row['camera_ids'], row['camera_device_ids'] or settings().camera_device_ids,
                     row['confidence_threshold'], row['data_retention_enabled'])
            return row['revision'] >= 1
        except ValueError:
            return False

    async def _replace(self, validated, marker):
        async with self.sessions() as db:
            for table in reversed(archive.application_tables()):
                await db.execute(delete(table))
            await archive.restore_rows(db, validated)
            await reset_sequences(db, self.engine.dialect.name)
            generation = await state_store.advance_generation(db, marker)
            await db.commit()
        state_store.publish_generation(generation)

    async def marker(self):
        # A separate connection distinguishes a failed commit acknowledgement from rollback.
        async with self.sessions() as db:
            return await db.scalar(select(MaintenanceState.restore_marker).where(MaintenanceState.id == 1))

    async def verify_live(self, expected, directory):
        async with self.sessions() as db:
            actual = await archive.create_archive(db, self.capture_root, directory / 'verify.zip')
        for key in ('tables', 'files'):
            if actual[key] != expected[key]:
                raise archive.ArchiveError('Restored data/evidence verification failed')
        (directory / 'verify.zip').unlink()

    async def restore(self, identifier, validation_id, token, actor_id, session_digest):
        async with self._lock:
            previous = await self.saved_result(identifier, actor_id, 'restore')
            if previous:
                return previous
            validation_dir = self.directory(validation_id)
            try:
                descriptor = json.loads((validation_dir / 'validation.json').read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                raise HTTPException(422, 'Backup validation is missing; validate again') from exc
            async with self.sessions() as db:
                generation = (await state_store.get_state(db)).auth_generation
            from datetime import datetime
            if (descriptor['consumed'] or descriptor['actor_id'] != str(actor_id)
                    or descriptor['session'] != session_digest or descriptor['generation'] != generation
                    or datetime.fromisoformat(descriptor['expires_at']) <= now_manila()
                    or not hmac.compare_digest(descriptor['token'], hashlib.sha256(token.encode()).hexdigest())):
                raise HTTPException(409, 'Backup validation expired, changed or was already used; validate again')
            validated = await run_blocking(archive.validate_archive, validation_dir / 'upload.zip', validation_dir / 'execution')
            if validated.archive_sha256 != descriptor['digest']:
                raise HTTPException(422, 'Uploaded archive changed; validate again')
            await self.check_database(validated)
            async with coordinator.exclusive('restore'):
                descriptor['consumed'] = True
                atomic_json(validation_dir / 'validation.json', descriptor)
                directory = self.directory(identifier)
                result = {'id': str(identifier), 'kind': 'restore', 'actor_id': str(actor_id), 'status': 'restoring'}
                await self.save_result(result)
                try:
                    async with self.sessions() as db:
                        await archive.create_archive(db, self.capture_root, directory / 'rollback.zip')
                    rollback = await run_blocking(archive.validate_archive, directory / 'rollback.zip', directory / 'rollback')
                    archive._space(self.root, sum(f['size'] for f in validated.manifest['files'].values()))
                    new, old = directory / 'new-evidence', directory / 'old-evidence'
                    await run_blocking(shutil.copytree, validated.evidence_root, new)
                    await run_blocking(sync_tree, new)
                    journal = {'id': str(identifier), 'validation_id': str(validation_id), 'phase': 'restore',
                               'actor_id': str(actor_id), 'manifest': validated.manifest, 'rollback_manifest': rollback.manifest}
                    atomic_json(self.journal, journal)
                except Exception:
                    result.update(status='failed', message='Restore preparation failed; station data was not replaced')
                    await self.save_result(result)
                    raise
                coordinator.block('recovery-required')
                try:
                    self.capture_root.rename(old)
                    new.rename(self.capture_root)
                    _sync_parent(self.capture_root.parent)
                    try:
                        await self._replace(validated, str(identifier))
                    except Exception:
                        if await self.marker() != str(identifier):
                            raise
                    await self.verify_live(validated.manifest, directory)
                except Exception:
                    # Recovery determines pre/postcommit; never infer commit outcome from an exception.
                    await self.recover()
                    return await self.saved_result(identifier, actor_id, 'restore')
                await self._finish(journal, 'completed', 'Station data restored; sign in again')
                return await self.saved_result(identifier, actor_id, 'restore')

    async def _finish(self, journal, status, message):
        # Hardware refresh may legitimately mutate device/config rows. Publish the verified
        # data boundary first so a process crash cannot turn those writes into a rollback.
        journal = {**journal, 'phase': 'data-verified', 'status': status, 'message': message}
        atomic_json(self.journal, journal)
        async with self.sessions() as db:
            state = await state_store.get_state(db)
            state_store.publish_generation(state.auth_generation)
        result = {'id': journal['id'], 'kind': 'restore', 'actor_id': journal['actor_id'],
                  'status': status, 'message': message}
        if self.hardware_refresh:
            try:
                result['configuration'] = await self.hardware_refresh()
            except Exception:
                result['hardware_error'] = 'Data verified, but camera configuration failed; retry applying saved configuration'
        await self.save_result(result)
        # Keep verified rollback archive/evidence; ordinary retention must never remove them.
        atomic_json(self.journal, {**journal, 'phase': 'finished'})
        await coordinator.finish_recovery()
        from app.ws.manager import ws_manager
        for socket in list(ws_manager._client_rooms):
            ws_manager.disconnect(socket)
            try:
                await socket.close(code=4001, reason='Station data changed; sign in again')
            except Exception:
                pass

    async def recover(self):
        if coordinator.owner_check:
            await coordinator.owner_check()
        if not self.journal.exists():
            return
        journal = json.loads(self.journal.read_text(encoding='utf-8'))
        if journal['phase'] == 'finished':
            return
        coordinator.block('recovery-required')
        coordinator.kind = 'restore'
        if journal['phase'] == 'data-verified':
            await self._finish(journal, journal['status'], journal['message'])
            return
        directory = self.directory(journal['id'])
        old, new = directory / 'old-evidence', directory / 'new-evidence'
        marker = await self.marker()  # Failure leaves admission closed and every tree intact.
        if journal['phase'] == 'restore':
            if marker != journal['id']:
                reconcile_evidence(self.capture_root, old, new, committed=False)
                await self.verify_live(journal['rollback_manifest'], directory)
                await self._finish(journal, 'failed', 'Restore failed before commit; original station verified')
                return
            reconcile_evidence(self.capture_root, old, new, committed=True)
            try:
                await self.verify_live(journal['manifest'], directory)
            except Exception:
                journal = {**journal, 'phase': 'compensate'}
                atomic_json(self.journal, journal)
            else:
                await self._finish(journal, 'completed', 'Station data restored; sign in again')
                return
        # A distinct marker makes compensation restartable even after its COMMIT acknowledgement is lost.
        rollback_marker = 'rollback-' + journal['id']
        failed = directory / 'failed-evidence'
        if marker != rollback_marker:
            rollback = await run_blocking(archive.validate_archive, directory / 'rollback.zip', directory / 'compensation')
            # Restore old files before DB commit; journal records this phase across any crash.
            if old.exists():
                if self.capture_root.exists():
                    if failed.exists():
                        raise archive.ArchiveError('Ambiguous compensation evidence')
                    self.capture_root.rename(failed)
                old.rename(self.capture_root)
            try:
                await self._replace(rollback, rollback_marker)
            except Exception:
                if await self.marker() != rollback_marker:
                    raise
        await self.verify_live(journal['rollback_manifest'], directory)
        await self._finish(journal, 'failed', 'Restore failed; rollback verified. Sign in again')


def get_service():
    global _service
    if _service is None:
        from app.config import get_settings
        from app.core.database import engine, async_session_factory
        _service = MaintenanceService(engine, async_session_factory, get_settings().capture_path)
    return _service


_service = None
