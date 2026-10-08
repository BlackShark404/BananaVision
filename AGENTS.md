# BananaVision repository guidance

- When resuming work, read `TASK_PROGRESS.txt` and the current Git status first. Use its
  latest resume point; historical checkpoints are reference material, not pending work.
- Trace the affected API, service, schema and UI before editing. Preserve explicit reverts,
  unrelated user changes, existing architecture and working behavior.
- Preserve the existing UI layout, components, styling, spacing and typography unless the
  user requests a redesign. Keep frontend/backend field names and types synchronized.
- Keep business timestamps and date boundaries consistent with the backend Asia/Manila
  helpers. Reuse existing conversions rather than adding competing timezone logic.
- Never test against the live station database, captures, physical cameras or OS power.
  Use isolated fixtures and disposable PostgreSQL schemas; inspect test setup first.
  Destructive live operations, deployment, history rewrites and shared-branch writes need
  explicit authorization. Do not read or print secrets to diagnose configuration.
- Run targeted regressions while implementing. Before completion, run relevant backend
  and frontend tests, type checks, configured lint and build, then review the scoped diff.
  Report exact results and distinguish existing lint debt from new regressions. Repeat
  passing checks only when changes or new evidence justify it.

## Selective Superpowers workflow

These are the user's repository-specific choices for applying generic skill workflows:

- Use systematic debugging for unexpected behavior; TDD/regression tests when they can
  prove a behavioral fix; concise planning for substantial or architectural work.
- Reuse approved specs and plans. Continue authorized implementation without duplicate
  brainstorming or stage approvals; clarify only genuinely unresolved decisions.
- Review security-sensitive authorization, persistence, archive/file and maintenance
  boundaries. Use Context7 or primary documentation when library behavior is uncertain.
- Prefer the current checkout. Worktrees are for actual isolation needs; subagents are
  for useful independent work or a focused final review, not an automatic per-step ritual.
- Load relevant skills/references on demand. Do not run a full skill chain for small edits
  or copy vendor skill instructions into additional local skills.
- Default to GPT-6 Astra Medium; use High when hard concurrency, recovery or architecture
  reasoning warrants it. Follow explicit task/model overrides.
- Keep `TASK_PROGRESS.txt` limited to current milestones, pending work, verified results,
  constraints and an exact next step. Archive superseded content before replacing it.

Read [the development workflow](docs/development-workflow.md) for verification commands
and tooling details. For maintenance changes, use the approved
[design](docs/superpowers/specs/2026-10-05-system-maintenance-design.md) and
[plan](docs/superpowers/plans/2026-10-06-system-maintenance.md). Consult
[backend documentation](backend/README.md) for deployment/migrations; do not load every
document for unrelated changes.
