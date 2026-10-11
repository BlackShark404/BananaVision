# Audit Corrections Implementation Plan

**Goal:** Resolve authorized F01–F09 findings and agreed G01–G06 gaps without changing the existing UI design.
**Reference:** `docs/system-audit-2026-10-10.md`; user authorization on 2026-10-11 supersedes its audit-only restriction.
**Architecture:** Reuse scoped SQL projections, mutation/history contracts and existing React components. Centralize inventory eligibility and remaining-life values on the backend; do not reconstruct unknown deleted history.
**Execution:** Inline on main, targeted regressions first. TASK_PROGRESS.txt is the single current execution ledger; no extra worktree or per-step approval.

## Constraints and review focus

- Main only; preserve d1e0220 and all maintenance/scan/logout changes.
- No live environment files, databases, captures, hardware or power operations. Test harnesses must disable environment-file loading.
- Maintain Manila timestamps, actor authorization, archive compatibility and existing design components.
- User approved stock policy: exclude deleted-intake and sold/depleted/removed stock; include valid active unlinked stock.
- Verify delayed responses after navigation, local writes and unmount; empty successful snapshots are still snapshots.
- Deleted intake links currently use SET NULL: preserve provenance before treating newly unlinked records as eligible. Do not invent legacy provenance.
- G05 approved: keep shared intake registry, scope scan counts to current Operator (Admin sees all). G01 approved: implement snapshot-stable pagination now. G04 approved: retain no-delete workflow and document historical deletion limits.

## Tasks

1. **Verify and finish F01/F04/F07/F09.** Inspect d1e0220. Add browser regressions in dashboard/persistence/maintenance tests, including stale intake failure and pending maintenance reads after recovery/unmount. Keep historical audit probes unchanged. Fix only observed gaps, then run affected suites and TypeScript. Files: DashboardRecords, Dashboard, InventoryContext, Inventory, SystemConfig and browser fixtures/harness.
2. **F03 then F02.** Add eligibility truth-table and aged/unknown-risk regressions in backend dashboard/analytics/logs tests and Inventory browser tests. Centralize SQL predicate; expose eligibility/remaining-time consistently to Inventory. Trace deleted-parent provenance, migrations and archive compatibility before any persistence change; verify disposable PostgreSQL. Keep historic records/retention intact.
3. **F05/F06/F08 and agreed G gaps.** Add exact successful-scan drilldown predicate, Analytics cultivar/status contract and existing-style filters, consistent metric labels/time labels, and current migration documentation. Regression-test scoped intersections, empty/null populations and delayed reads. Implement only user-selected registry/pagination/deletion policies; document remaining live/scale limits honestly.
4. **Final verification and local commit.** Run relevant full isolated backend/PG/frontend suites, TypeScript, configured lint and production build. Review security-sensitive boundaries and complete diff. Clean only recorded test resources. Update report follow-up and checkpoint with exact results; commit locally on main only after verified checks. No push/merge/deploy.

Existing valid audit evidence is reusable for unchanged behavior. Characterization assertions intentionally documenting old defects are historical evidence, not post-fix acceptance tests. Replace expectations only in active regression suites and document the transition.
