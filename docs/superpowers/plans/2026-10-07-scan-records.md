# Scan Logs and Detail implementation plan

Goal: preserve existing server browsing/export and direct-link UI while completing auditable,
conflict-safe status/correction flows and resilient detail rendering. No redesign or live data operations.

1. Backend (TDD): add scan revision and immutable history events with server time, snapshot actor,
   previous/new values, reason, request ID and request fingerprint. Enforce CAS and replay semantics;
   changed payload/key reuse and stale revision return409, exact retry returns original result.
   Source-only/no-op edits never mark classification overridden. Scope legacy list/detail/flag/status
   consistently to Admin/all or owning Operator; keep corrections/notes Admin-only. Known deleted
   records use preserved tombstone410, unknown404, forbidden403. Legacy absent audit data is explicit.
   Cover initial scan and bulk intake status writers; preserve original AI values once. Add migration.
2. Frontend (after contract handoff): use revision/request IDs/reasons, per-record pending state and
   conflict refresh without losing draft. Hydrate notes/history with direct detail response. Preserve
   full evidence on writes; show ordered history with existing card styles. Handle403/404/410, missing
   images, renamed camera snapshots, late requests and safe retry. Add only necessary reason fields.
3. Root: extend existing server query/export tests for deterministic equal-key pagination, >200rows,
   all filtered exports independent of page, literal search and CSV quotes/CR/LF/Unicode/formula
   prefixes. Preserve current csv.writer/streaming protection where already correct. Repair inherited
   missing0003 predecessor only because new migration cannot run without it.
4. Verify isolated backend suites and PostgreSQL concurrency/migrations, relevant browser suites,
   application TypeScript, configured lint/build, scoped Codex Security diff scan and independent
   review. Record exact results and inherited unrelated failures; inspect final diff for UI drift.

Ownership: backend worker owns scan models/schemas/routes/history/intake bulk/pipeline/migration0005;
frontend worker owns Logs/Detail/scan-context/API/types/browser regressions; root owns query/export
regressions, missing0003 prerequisite, integration and review. Keep TASK_PROGRESS.txt current.
