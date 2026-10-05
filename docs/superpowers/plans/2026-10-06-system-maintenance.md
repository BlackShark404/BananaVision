# System Maintenance Implementation Plan

> **For agentic workers:** Use Superpowers execution and TDD workflows. User approved autonomous execution on 2026-10-06, including planning, implementation, tests, and review. No additional stage approval is required.

**Goal:** Implement the approved configuration, camera/inference, retention, backup/restore, and power-maintenance design without changing the existing visual design.
**Architecture:** Canonical versioned configuration feeds capture/inference. A station coordinator closes admission and drains work; database coordination and durable journals protect maintenance. Strict typed archives stage data and evidence before transactional, recoverable replacement.
**Tech Stack:** FastAPI, SQLAlchemy/asyncpg/PostgreSQL, Python, React/TypeScript/Vite, existing pytest and browser fixtures.
**Spec:** ../specs/2026-10-05-system-maintenance-design.md

## Global constraints
- Preserve existing four System Configuration tabs and visual styles. No live destructive operations.
- Backend business timestamps use Asia/Manila. Archive timestamps preserve original instants.
- Credential hashes remain private; no SQL/pickle/model execution from uploaded archives.
- Use isolated databases/directories, fake hardware and fixed-command mocks for tests.
- Keep changes reviewable in the existing checkout; do not commit/push automatically.
- TASK_PROGRESS.txt is the durable execution ledger. Existing baseline need not be repeated unchanged.

## Review focus
1. Cancellation while thread-based capture/inference runs must retain admission protection (task 2).
2. Legacy config duplicates must not silently delete old values or create ambiguous runtime mapping (task 1).
3. Windows filesystem renames/reparse points and import-time directory creation must not undermine recovery (tasks 3/4).
4. A database commit exception can mean committed; determine outcome via an independent marker (task 4).
5. A backend restart is not proof that an accepted OS reboot/shutdown happened (task 2).

## Task 1 — Canonical configuration and real capture/inference
Files: models/system_config.py, schemas/common.py, services/configuration.py (new), API config/cameras/devices, camera_manager.py, classification.py, scan_service.py, startup.py; migration 0003; tests/test_configuration.py.
Interfaces: `get_config(db) -> SystemConfig`; `config_response(config) -> dict`; `update_config(db, changes, expected_revision, admin_id) -> SystemConfig`; `apply_camera_config(config) -> None` after commit. Saved fields: camera_ids, camera_device_ids, confidence_threshold (integer 1–100), data_retention_enabled, revision. Response also includes applied camera values, application status/error, restart_required, retention_days/policy.
- [ ] Add failing tests for revision conflicts, validation, canonical selection, saved threshold reaching real classifier arguments, stable renamed/reordered mapping, failed frame initialization, and failed persistence.
- [ ] Implement canonical marker/revision migration preserving legacy rows, shared config reader, strict validation/CAS, snapshot threshold passed to classifier. Keep runtime application after persistence.
- [ ] Add handle synchronization and one health rule, preserve UUID identities, stop parsing logical names, report partial mapping failures.
- [ ] Run new tests and existing config/camera/scan-persistence regressions; expect all pass. Root integrates startup/coordinator changes sequentially after worker edits.

## Task 2 — Admission, draining, maintenance state and power
Files: services/runtime_operations.py, services/maintenance_state.py (new), models/maintenance_state.py (new), migration 0004, core/database.py, startup.py, main.py, API config, services/power_control.py, scan_service.py; tests/test_maintenance.py.
Interfaces: `coordinator.operation()` async context for admitted work; `coordinator.exclusive(kind)` closes admission/drains; `run_blocking(callable, *args, **kwargs)` awaits threaded work even when caller cancels; durable singleton `MaintenanceState` stores authentication generation, power state/boot identity, and committed restore marker. `get_status()` is safe while blocked.
- [ ] Prove rejection of new/queued scans during draining, timeout with active scan intact, and cancellation protection with event-based tests (no sleep-based assumptions).
- [ ] Add station process ownership and PostgreSQL shared/exclusive advisory coordination. Cover HTTP requests including streaming reads, background writes, previews, retention, application shutdown.
- [ ] Persist audited power intent before fixed OS invocation; idempotent operation ID, accepted/failed/unknown states. Keep admission blocked after acceptance/unknown, reconcile boot identity, support authenticated recovery/cancellation.
- [ ] Run injected command/commit/timeout/restart tests. Never invoke real power commands.

## Task 3 — Strict archive format and safe retention
Files: services/backup_archive.py (new), services/data_retention.py, tests/test_backup_archive.py, tests/test_retention.py.
Interfaces: `create_archive(db, capture_root: Path, destination: Path) -> dict`; `validate_archive(archive: Path, staging_root: Path) -> ValidatedBackup`; validated object exposes manifest, staging root, typed row iterator, and normalized evidence. `restore_rows(db, validated)` uses only allowlisted application metadata.
- [ ] First add corruption/traversal/duplicate/version/missing-evidence/full-disk tests and a complete all-table round trip in temporary storage.
- [ ] Implement bounded JSON-lines table serialization, exact schema/table/column validation, file manifest/hashes, capture/thumbnail path normalization, private staging, typed values, constraint validation, complete archive publication only after verification.
- [ ] Replace age-only database deletion with coordinated orphan-only retention; preserve every persisted scan/audit/evidence record. Record attempted/completed/failed cleanup accurately; keep 6-hour cycle and configured grace.
- [ ] Run archive and retention regressions; update old destructive-retention expectation to approved policy.

## Task 4 — Restore orchestration, recovery, authentication and API
Files: services/backup_restore.py (new), services/maintenance_state.py, core/security.py, api/deps.py, auth token issuance, ws authentication, api/v1/maintenance.py (new), router.py, startup.py/main.py; tests/test_backup_restore.py.
Interfaces: authenticated `/config/maintenance` status; `/config/backups` create; `/config/backups/{id}` download; `/config/restores/validate` upload; `/config/restores` execute with validation ID/token/password/confirmation/operation ID; `/config/operations/{id}` status. Operation IDs are UUIDs, validation tokens are one-use, short-lived and account/session/generation/digest-bound.
- [ ] Add tests proving no live mutation on invalid archive, foreign-key/unique validation, active admin requirement, token replay/session denial, and restore failures at each promotion boundary.
- [ ] Create isolated staging schema; validate before requesting confirmation, revalidate before execution. Close admission/drain, create verified rollback archive, stage evidence on destination filesystem, fsync journal, replace rows transactionally and promote evidence under blocked access.
- [ ] Commit restore marker and fresh non-restored auth generation with data. Use transactional sequence restart; determine uncertain commit via fresh connection. Add compensating-restore journal/marker for postcommit verification failure.
- [ ] Reconcile journal before import-time capture creation, seed, camera or retention startup. Verify both data/files before success; preserve recovery material on failure. Reinitialize saved hardware and report hardware failure separately.
- [ ] Add auth generation to all session/setup token issuance and HTTP/WebSocket verification; close old sockets. Require reauthentication for restore and power recovery.
- [ ] Run isolated round-trip, interrupted compensation, failed DB/file commit, non-admin, replay, startup recovery and session invalidation tests. Run PostgreSQL cases if an isolated instance is available; otherwise explicitly record unavailable verification.

## Task 5 — Frontend integration preserving existing design
Files: types/api.ts, types/index.ts, lib/api.ts, context/AdminContext.tsx, pages/admin/SystemConfig.tsx, components/CameraCalibrationModal.tsx; tests/maintenance.fixture.tsx, maintenance.test.mjs.
- [ ] Add failing browser tests for failed initial config load, stale response/revision conflict, pending draft preservation, false camera success, backup/restore validation/failure and duplicate power submits.
- [ ] Synchronize API contracts. Expose readiness/error/revision and applied state; save changed fields only, guard late requests, keep failed drafts, disable mutating controls while pending.
- [ ] Reuse existing descriptions, buttons/badges/dialogs for saved/applied status, effective retention wording, backup creation/download and validate/confirm restore. Do not claim browser disk-save completion.
- [ ] Show operation status for drains, accepted power, restore recovery and partial camera failures. Preserve all four tabs, classes and layout except necessary additional controls.
- [ ] Run browser suite, application TypeScript check, configured lint, and production build. Capture/review fixture screen if useful.

## Task 6 — Integration and independent review
- [ ] Run all isolated backend suites; run opt-in PostgreSQL tests only against a confirmed isolated target.
- [ ] Run relevant frontend suites, type checking, lint/build. Report pre-existing unrelated failures without hiding them.
- [ ] Run Codex Security review of new sensitive boundaries and a fresh independent spec/code review; fix confirmed findings with regression tests.
- [ ] Inspect final Git diff for unrelated/UI changes. Update checkpoint with exact results and verification limitations. No live hardware/power/restore claims from mocks.

Preflight: tasks 1/2 share scan/startup/config API; task 1 worker owns them first, root integrates after handoff. Task 3 archive worker owns a new service/test only. Task 4 consumes archive/coordinator contracts after focused tests. Frontend task starts after response contracts are available. Migration sequence is 0003 configuration then 0004 maintenance. No implicit schema changes from archive metadata.
