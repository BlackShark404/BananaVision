# Seed and mock-data compatibility audit — 2026-10-19

Base: `4e7bcb1`, branch `main`. All validation used disposable data and copied scripts.

Current seeding behavior is described in the **Requested legacy setup flow** follow-up
below. The initial empty-database-only setup policy and intermediate skip behavior are
historical; the latest requested wrapper flow resets demo data after an explicit Yes.

## Findings and changes

| Area | Confirmed issue | Result |
| --- | --- | --- |
| `backend/seed.py` | New demo scans had temperature/humidity but no VPD | Use existing `calc_vpd` on inputs rounded to stored two-decimal precision; persist three-decimal kPa |
| Scan model compatibility | Missing treatment, original-result and account/source snapshots | Copy the intake treatment and classification values into current model fields; preserve immutable snapshots |
| Scan History | Initial statuses had no event evidence | Add explicit synthetic `Demo Seeder` creation events; depleted-intake scans also have later sale events/revisions linked to status evidence |
| Demo spoilage | Random days unrelated to cultivar/ripeness/environment | Use existing `SpoilagePredictor` fallback rules without loading trained weights |
| Demo chronology | Intake creation could postdate its scans | Generate intake timestamps before scans, including across Manila midnight |
| Data safety | Seeder dropped all existing tables | Refuse any populated table before DDL; initialize current schema/migrations and seed in one transaction, sharing startup's PostgreSQL advisory lock |
| `setup.bat` | Disabled delayed expansion silently skipped DB prompts; installer failures did not stop setup | Use a prompt subroutine without delayed expansion, environment-based/URL-encoded credentials, and checked dependency commands |
| `seed.bat`, `seed.sh` | Failed seeding could print success | Propagate failure and stop before success output |
| SQL reference docs | Old schema claimed to be current; manual migration advised historical backfill | Mark both historical and point to maintained ORM/versioned migration entry points; SQL behavior unchanged |

`setup.sh` already stopped on failures; its seeding guidance now matches the empty-database
requirement. No dependency versions, application configuration files, API contracts, UI,
permissions, models, printer paths or live records were changed.

## Audit coverage and intentional exceptions

- Setup/seed entry points: both Windows and Bash scripts, their environment/bootstrap
  requirements, schema initialization and the single current demo generator.
- Current models, versioned migrations, scan creation, historical serialization, Scan Logs
  projection/CSV, frontend mappings, analytics confidence populations and inventory policy.
- Backend test factories and frontend fixtures: omitted/null environmental data and actor
  evidence deliberately cover legacy/unavailable records. VPD values deliberately different
  from temperature/humidity in stored-value regressions prove history is not recalculated.
  They were preserved, not normalized into new synthetic readings.
- `SensorReading` has temperature/humidity only; it does not require a VPD field. Production
  persists VPD on `ScanClassification`, while dew point and heat index currently remain null.
  Those optional fields were not populated merely because columns exist.
- Startup's administrator bootstrap creates no scans and retains its existing permissions
  and credential lifecycle. The demo operator remains inactive with no PIN.
- Existing training/dataset utilities are separate from setup and do not generate this seed
  database. No dataset, trained weights, historical schema migration or production formula
  was rewritten. Missing images/detections remain unavailable, not fabricated.

The new history actor is the generator, not a claim that an operator performed a live scan.
Synthetic predictions are for development displays and workflows, not measured AI accuracy.
Existing data cannot be upgraded by rerunning the seeder; use normal migrations for schemas
and preserve missing historical values.

## Verification

- New PostgreSQL seed tests cover stored VPD precision/zero, treatment/fallback consistency,
  immutable original values, Manila chronology, detail/history/list/CSV/analytics consumers,
  populated-database refusal, rollback, concurrent attempts and production/bootstrap guards.
- Initial seed regressions failed on missing VPD/events and destructive reruns. Corrected
  wrapper harness against committed scripts: **5 failed, 4 passed**; final scripts: **9 passed**
  in 1.93s. These run copies with fake installers and seed commands, preserving existing `.env`
  files and checking normal/special-character credentials and both success/failure exits.
- Full isolated `pytest backend/tests`: **558 passed, 0 skipped**, 146.83s, with PostgreSQL 18
  on a fresh temporary cluster. This includes the first four wrapper cases and all nine seed
  cases. Five additional wrapper cases were subsequently included in the final nine-case run.
- Frontend `node --test --test-concurrency=1` for Scan Records, Analytics, Dashboard, Kiosk
  and Operations Loading: **71 passed**, 120.90s.
- `npm run typecheck`: pass. `npm run build` (`tsc -b` and Vite): pass, 15.39s Vite.
- Configured frontend lint: **37 errors / 5 warnings**, existing baseline. Configured
  backend Ruff (`backend/app backend/tests`): **646 errors**, existing baseline.
  Changed seeder and both new test files: no Ruff diagnostics.
- The Bash harness initially needed UTF-8 decoding and LF input rather than Windows CRLF;
  corrected tests pass. No production script behavior was changed to accommodate the harness.
- Logs: ignored `frontend/node_modules/.tmp/bv-seed-*` files. All temporary database servers
  were stopped. No station DB, captures, cameras, printer or power controls were accessed.

## Boundary review and limits

Reviewed the command entry points and schema/data transaction: populated databases fail
before mutations; failure rolls back generated rows and DDL; concurrent runs cannot both
seed; identifiers are quoted through SQLAlchemy; credentials are passed via environment
and URL-encoded, and existing `.env` files are retained. Context7's SQLAlchemy documentation
confirmed externally managed connection/session transaction behavior. No new authorization
surface was added. This is a scoped source/behavior review, not a repository-wide security scan.

Actual dependency downloads, fresh OS/toolchain installation, native Linux/macOS execution,
live hardware and production datasets were not tested. Shell entry points were exercised
through Git Bash on Windows. Existing full-frontend connectivity test failures remain a
separate historical issue; this task ran the affected suites, not that full suite.

## Resume confirmation — 2026-10-20

The checkpoint, current Git state and saved test logs were reviewed after the interruption.
The approved implementation and scoped verification were already complete; no source edits
or repeated test runs were needed. `git diff --check` passed. All fourteen task files remain
unstaged on `main` at `4e7bcb11f083fa7e184ffc2f336c2cdf87a9822b`.
The local `origin/main` tracking ref is one commit ahead (`8909dc1`), adding only
`docs/development/accuracy-improvement-roadmap.md`; it does not overlap this patch. No fetch, pull, merge,
commit or push was performed during this resume. The verification limits above remain.

## Follow-up — existing database during setup (2026-10-20)

A reported traceback came from the intentional populated-database guard, not a connection
failure. The guard remains in place before DDL. It now raises `DatabaseNotEmptyError`;
the CLI reports preserved data and returns reserved exit code
20 without a traceback. Optional setup handles that code as a skip and completes. Direct
seeding remains nonzero and never claims new records were created. Other exceptions and
script failures still fail, including ordinary Python exit code 2 for a missing script.

The focused isolated PostgreSQL and Windows/Git Bash wrapper run passed **29 tests, no
skips, in 11.63s**. Before implementation, six new CLI/setup expectations failed with
19 passing tests. An additional two-case missing-script regression caught a collision
with Python's exit code 2 during development; using the dedicated code 20 resolved it.
The final run includes both cases, existing seed safeguards and consumer API regressions.
Wrappers use copied scripts/fake installers; no live data, credentials or hardware were
accessed. Prior frontend/type/build results remain applicable because frontend source,
API contracts and dependencies are unchanged. Logs: `frontend/node_modules/.tmp/bv-seed-skip-*`.

After correcting the new exception's Ruff naming diagnostic, the final seed/CLI suite
passed **12 tests in 8.91s**; the 17 wrapper cases were unchanged. Changed Python files
pass Ruff; configured backend Ruff remains at **646 existing errors**. Scoped diff and
persistence/error-boundary review found no additional defect; `git diff --check` passes.
Graphify refreshed to 3806 nodes / 11525 edges / 247 communities without graph loss;
the existing optional SQL parser limitation remains. No Git write or deployment performed.

## Requested legacy setup flow — 2026-10-20

The user requested a process close to the original `setup.bat`, `start.bat` and `dev.bat`,
with the additional Scan Logs data during seeding. Comparison against `e6110c9^` confirmed
that the original seeder dropped and recreated application tables; the start/dev launchers
were already unchanged and remain untouched.

Setup retains environment setup, dependencies and optional seeding. Its prompt now explicitly
states that Yes deletes existing application database records (accounts, scans and history)
and creates fresh demo data. No/blank keeps the database. Seed wrappers use the same prompt.
Only Yes supplies `--reset-demo`; plain `python seed.py` retains its non-destructive refusal.
The reset recreates ORM tables and the migration marker, then applies current migrations
and seeds within the existing transaction/advisory lock. No cascading fallback was restored.
The generator still creates 25 scans with stored-precision VPD, treatment, original/name
snapshots and synthetic history. No historical field backfill or real station reset occurred.

RED: 41 failed / 14 passed before the new reset/confirmation contract existed. GREEN:
**55 passed, no skips (26.83s)** across `test_seed.py` and `test_setup_scripts.py`, using
disposable PostgreSQL 18 and copied Windows/Git Bash wrappers. Coverage includes fresh and
reset consumer APIs, VPD, explicit/default behavior, failed-reset rollback, migration revision,
unrelated-table preservation, production/bootstrap guards, Yes/No/blank and real failures.
The temporary PostgreSQL server was stopped. Logs: `frontend/node_modules/.tmp/bv-seed-reset-*`.

## Kiosk/Seed canonical persistence and propagation verification — 2026-10-20

Canonical persistence logic was unified under `backend/app/services/scan_creation.py::create_scan_record`,
shared by both `backend/seed.py` and `backend/app/services/scan_service.py`. The canonical creation builds
the scan record, classification, initial status log (`In Stock`), original AI snapshot, and initial creation
event within the caller's transaction, avoiding implicit relationship I/O.

Distinct attribution is preserved:
- Live Kiosk scans record the authenticated operator (`actor_name=operator_name`, `actor_id=account_id`).
- Demo seed scans record `actor_name="Demo Seeder"` (`actor_id=None`) with explicit synthetic reason text.
- Seeded accounts and suppliers carry mandatory `"Demo "` prefixes (`Demo Kiosk Operator`, `Demo Dole Foods`,
  `Demo Del Monte`, `Demo Local Farm Coop`) preventing any confusion with real operator activity.

Data propagation verified across the entire lifecycle:
`Kiosk → Database → Scan Logs → Scan Detail → Dashboard → Inventory → Analytics → CSV Export → QR Tracking`
with matching persisted values for cultivar, ripeness, confidence, source/intake, operator, timestamps,
temperature, humidity, VPD (formatted to 3 decimal places in UI/CSV), treatment, spoilage estimates,
inventory status, QR tracking, intake provenance, and immutable creation history snapshots.

Scan Detail production build verified: the reported `TS2345` note type mismatch (`ScanNote[]` vs `ApiScanNote[]`)
was resolved in `ScanDetail.tsx` via `acceptScan(saved)`. Both `npm run typecheck` and `npm run build`
execute cleanly with zero errors. All 59 backend tests in `test_seed.py`, `test_setup_scripts.py`, and
`test_seed_kiosk_contract.py` pass in 30.47s on disposable PostgreSQL 18. Frontend browser test suites
`kiosk.test.mjs` (13 tests) and `scanrecords.test.mjs` (35 tests) pass with zero failures.
