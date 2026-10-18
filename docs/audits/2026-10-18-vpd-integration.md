# Historical VPD audit and integration — 2026-10-18

Vapor Pressure Deficit was already calculated, persisted and supported by the
enhanced spoilage predictor. The missing integration was in Scan Logs: its shared
query projection, response model, frontend mapping and CSV omitted the stored
field. Scan Detail already rendered non-null VPD, but hid missing values and used
variable precision. These gaps are now addressed without changing the formula,
database schema, models or existing UI structure.

Reviewed base: `9a1bd6d445e3692857c994d1cb7362377f18414e` on `main`. Recent IDE-ignore
and model-weight removal commits are preserved. Publication status and incoming
main integration are recorded in `TASK_PROGRESS.txt`.

## Existing implementation traced

| Area | Verified path and behavior |
|---|---|
| Sensor source | `backend/app/services/sensor_reader.py` supplies the latest temperature/humidity reading; `scan_service.py` captures both from the same reading during the scan. |
| Calculation | `feature_engineering.calc_vpd` computes saturation pressure `0.61078 * exp(17.27*T/(T+237.3))`, subtracts humidity-adjusted pressure, and rounds to three decimals in kPa. For 33.6°C / 70.1%, the result is 1.555 kPa. |
| Persistence | `scan_service.py` passes that value to prediction and stores it in `ScanClassification.vpd`, nullable `DECIMAL(6,3)`. Without both readings, the recorded value remains null. |
| Migrations | Alembic `0002_feature_engineering.py` adds the nullable field without backfill. The older manual `docs/migrations/001_feature_engineering.sql` includes a backfill from stored temperature/humidity. Neither was run or changed. |
| ML integration | `spoilage.py` supports legacy four-feature models and enhanced six-feature models. Only the enhanced path consumes VPD and treatment. An explicit zero is retained. Its internal missing-input fallback is not persisted as scan VPD. The rule fallback does not use VPD. |
| Existing APIs/UI | Detail, public detail and trigger serialization already expose stored VPD. `ApiScan`, `ScanResult` and `mapApiScan` already preserve it. Kiosk/public views already render it and were left unchanged. |
| Scan Logs | The shared SQL projection, `ScanLogRow`, JSON serialization, frontend mapping, IoT Data cell and CSV now carry the same stored value. |

No live database or deployed model was inspected. Source support for the enhanced
model is verified; this does not establish which model is active on the station
or whether every historical row contains VPD.

## Bounded changes and data integrity

- Logs adds a compact VPD line within the existing **IoT Data** cell, without a new
  column. The existing typography, colors, spacing and table structure remain.
- Details retains the existing environmental metric/grid styling and shows VPD
  alongside the temperature/humidity information. It now shows unavailable data
  explicitly rather than hiding that metric.
- Both modules format finite recorded values to three decimals plus **kPa**.
  `1.25` displays as `1.250 kPa`, zero as `0.000 kPa`, and missing data as `—` with
  an accessible unavailable label. Neither module fetches current sensors to fill it.
- The CSV appends **VPD (kPa)** as its last field, preserving every existing column
  position. Values use three decimals; absent values produce blank cells.
- `ScanLogRow.vpd: float | None = None` allows older stored browse snapshots to
  remain valid when the key is absent. They stay unknown; current database or
  sensor data is not substituted. New snapshots freeze the recorded value.
- No migrations, backfills, dependencies, model inference behavior, authorization
  rules, query filters, business dates or scan writes changed.

Context7's Pydantic documentation confirmed that an explicit nullable default
supports omitted keys and normal serialization includes null. Existing Pydantic
extra-field behavior also supports rollback with snapshots containing the added key.

## Verification

| Check | Observed result |
|---|---|
| New regressions before implementation | Two backend API/snapshot cases failed on missing VPD; representative Logs/Detail browser cases failed before the UI changes. |
| Targeted backend | **94 passed, 2 skipped**, 18.34s: scan logs, spoilage models, time/writes, dashboard and migrations. |
| Targeted VPD browser cases | **10 passed**, 13.44s: stored 1.555/1.25/zero/null/omitted values in Logs and Details, formatting, unavailable labels and current-sensor isolation. |
| Full isolated backend | **491 passed, 38 skipped**, 133.46s. PostgreSQL-dependent cases skipped; no disposable PostgreSQL configured. |
| Full frontend | **159 passed, 2 failed**, 267.79s. The two unchanged connectivity tests expect shared sockets/message authentication, while the existing runtime uses per-hook sockets/query authentication. All VPD tests pass. |
| TypeScript and production build | **PASS** for typecheck and `tsc -b`/Vite; Vite completed in 31.14s. |
| Frontend configured lint | **FAIL: 37 errors, 5 warnings**, existing debt. No diagnostic increases in the three changed source files against the base. |
| Backend configured Ruff | **FAIL: 651 errors**, existing debt. No diagnostic increases in the six changed Python files against the base. |
| Visual review | Mocked Edge desktop Logs/Detail and mobile Detail render VPD readably in existing components. This is component-level visual review, not full-shell pixel comparison. |
| Diff review | Source/test diff matches the frozen reviewed patch; `git diff --check` passes. |
| Graphify AST refresh | **PASS: 3,685 → 3,693 nodes; 11,251 edges; 236 communities**. No graph loss. Two SQL files remain omitted because the SQL parser is unavailable. No paid semantic extraction. |

Backend tests ran from a fresh temporary working directory without the station
`.env` or database URL. Frontend tests used the existing mocked Vite/Edge harness.
No live database, captures, cameras, printer or power operations were accessed.
Relevant test commands and isolation procedures remain in
[the development workflow](../development-workflow.md).

Local ignored logs are under `frontend/node_modules/.tmp/`:
`bv-vpd-backend-targeted.txt`, `bv-vpd-green.txt`, `bv-vpd-full-backend.txt`,
`bv-vpd-full-frontend.txt` and `bv-vpd-ruff-final.txt`.

## Scoped security and regression review

Codex Security's patch-risk workflow reviewed an immutable source/test patch with
SHA-256 `5015caeb353ae538994e720466bf5f1cbac655765872b45a74adae54614ece62`.
The review traced account-scoped queries, snapshot ownership/reuse, typed JSON,
CSV output and React rendering. No new authorization or persistence defect was
established. The assessment is advisory and does not authorize publication.

The added API/CSV field is a consumer contract change, so automatic merge is not
recommended. Existing project failures and skipped PostgreSQL checks remain
visible; no full-codebase security certification or clean global test/lint claim
is made. External consumers requiring an exact CSV column count were not tested.

Related knowledge: [Frontend](../knowledge/Frontend.md) and
[Testing and Validation](../knowledge/Testing%20and%20Validation.md).
