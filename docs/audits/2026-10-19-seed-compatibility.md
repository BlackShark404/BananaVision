# Seed and mock-data compatibility audit — 2026-10-19

Base: `4e7bcb1`, branch `main`. All validation used disposable data and copied scripts.

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
`docs/accuracy-improvement-roadmap.md`; it does not overlap this patch. No fetch, pull, merge,
commit or push was performed during this resume. The verification limits above remain.
