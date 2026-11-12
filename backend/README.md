# BananaVision Backend

Python/FastAPI backend for the BananaVision banana classification and spoilage prediction system.

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL + SQLAlchemy (async) + Alembic
- **Auth:** JWT (PyJWT) + bcrypt
- **ML:** YOLO26 (ultralytics) + Random Forest Regression (scikit-learn)
- **Camera:** OpenCV (multi-camera parallel capture)
- **Sensor:** Arduino DHT22 via pyserial
- **Real-time:** WebSocket with room-based pub/sub

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up PostgreSQL
createdb bananavision
# Edit .env with your DB credentials

# 4. Initialize or upgrade the schema (also runs during server startup)
python -m app.core.migrations

# 5. Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Open API docs
open http://localhost:8000/docs
```

## Top-camera overlap refinement

`YOLO_TOP_OVERLAP_REFINEMENT` defaults to `true`. For the calibrated existing
YOLO26m checkpoint, the configured `Top` view uses NMS IoU 0.65 when detection
confidence is 0.50 and the configured baseline IoU is 0.45. Other views keep
their configured IoU. Set `YOLO_TOP_OVERLAP_REFINEMENT=false` before startup
to use the baseline for every view.

The classifier identifies the checkpoint by SHA-256, independently of its filename.
Different weights, custom confidence/IoU thresholds and unidentified checkpoints
use the baseline; the new YOLOv8n candidate did not pass this calibration's guards.
The calibrated checkpoint uses image size 640; custom checkpoints retain their saved
resolution and bypass this profile at other sizes. Inputs remain full-frame BGR,
with original-pixel box coordinates.
Explicit inference options prevent a Top prediction from changing later views.
No database migration or frontend change is needed.

See the [dataset and inference audit](../docs/yolo-dataset-audit-2026-10-16.md)
for the validation results and limits. These offline measurements do not establish
an exact physical bunch count or accuracy on the live camera scene.

## Classification and count review

Exact coincident boxes with competing class labels count once but retain their
original boxes and scores for review. The raw box total can exceed the finger
estimate. Fully contained same-class fragments are filtered after NMS; partial
overlap between neighboring fingers is preserved in the first pass. A conflicting
class suppressed during Top rotation also requires review.

`MULTI_CAMERA_FINGER_FUSION` retains the existing peripheral count estimate.
Rear's boxes are not added again when Rear supplies the anchor count, and any
estimate above all individual view counts is flagged for operator confirmation.
Camera-edge positions do not establish unique physical identities. Setting this
option to `false` uses the largest per-camera count, which can undercount occluded
fingers. The kiosk shows **Scan Complete - Review Needed** for flagged results.

Confidence is the mean winning-pair detection score, not measured accuracy or
confidence in the count. The [integrity audit](../docs/audits/yolo-scan-integrity-2026-10-17.json)
records offline validation and the unresolved station cultivar/count limits.

For competing cultivars, a weighted candidate without a strict majority of valid
unique-camera summaries requires conflict review, including a high-score 2–2
split. The kiosk shows **Uncertain**, the opposing camera predictions, and hides
the main confidence/spoilage estimate pending cultivar verification. Raw model
candidates and scores remain stored. Count-only overrides do not resolve cultivar
uncertainty; cultivar corrections require original-result or change-history evidence.
This guard does not change model recognition accuracy. See the
[station validation protocol](../docs/knowledge/Testing%20and%20Validation.md#station-cultivar-recognition-protocol)
for representative data collection, bunch-level splitting and offline evaluation.

## Out-of-distribution rejection

The cultivar model is closed-set: every box it emits is one of the twelve
Lakatan/Latundan/Cardaba ripeness labels. The out-of-distribution (OOD) gate in
`app/services/ood_gate.py` therefore requires independent banana evidence from the
COCO pre-detector before a cultivar box is trusted:

1. **Scan gate.** At least `OOD_MIN_BANANA_VIEWS` camera views must show a banana at
   `OOD_BANANA_CONFIDENCE`. Otherwise the scan is rejected before classification.
2. **Box support.** In each view a cultivar box is kept only when banana evidence
   (confidence `OOD_SUPPORT_CONFIDENCE` or higher, grown by `OOD_SUPPORT_MARGIN` per
   side) covers its centre. A box without that support is treated as if the model had
   never emitted it; the classifier's own rules are not modified.
3. **No silent change.** A scan that lost any box is saved flagged for review. A scan
   left with no supported cultivar is rejected, nothing is stored, and a
   `scan_rejected` activity row keeps the reason and the per-view banana scores.
4. **Fail closed.** While the banana verifier cannot run, scans are refused with
   HTTP 503 unless `OOD_GATE_FAIL_OPEN=true`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `OOD_BANANA_CONFIDENCE` | `0.30` | Banana confidence that accepts a view |
| `OOD_SUPPORT_CONFIDENCE` | `0.05` | Weaker banana evidence that may support cultivar boxes |
| `OOD_SUPPORT_MARGIN` | `0.25` | Relative growth of each evidence box |
| `OOD_BOX_SUPPORT_FILTER` | `true` | `false` restores the earlier any-box behaviour |
| `OOD_MIN_BANANA_VIEWS` | `1` | Views that must show a banana |
| `OOD_GATE_FAIL_OPEN` | `false` | `true` classifies without the verifier |

A rejected scan answers `POST /api/v1/scans/trigger` with HTTP 422. `detail` stays a
string; `code` (`ood_rejected`), `status` (`rejected`), `is_ood` and `reason`
(`no_banana` or `no_target_cultivar`) are additive. The `scan:failed` WebSocket event
carries the same four fields beside `error`. A fault is not a rejection: an unavailable
verifier (`ood_gate_unavailable`) or a scan with no camera frame (`capture_unavailable`)
answers HTTP 503 with `is_ood: false` and writes no `scan_rejected` row. No database
migration is needed.

Open-source OOD data comes from Open Images V7. No image is stored in Git; the pinned
manifest `scripts/ood/open_images_ood_manifest.json` lists the image IDs of three
disjoint pools (`train_negatives`, `calibration`, `benchmark`). From `backend/`:

```bash
# Download the pools (about 1.1 GB) into the ignored backend/ood-data directory.
python scripts/prepare_ood_dataset.py fetch \
    --manifest scripts/ood/open_images_ood_manifest.json --output ood-data

# Gate only: no cultivar weights needed.
python scripts/evaluate_ood_gate.py gate --ood ood-data --pool benchmark

# Full pipeline with the trained weights and a labeled split: per-cultivar
# precision/recall/F1 and the false-cultivar rate without a gate, with the earlier
# gate and with the OOD gate.
python scripts/evaluate_ood_gate.py pipeline \
    --weights <file named by YOLO_MODEL_PATH> --id-split <prepared dataset>/test \
    --ood ood-data --pool benchmark --output ood-pipeline-report.json

# Retraining: copy a prepared dataset and add background images to train only.
python scripts/prepare_ood_dataset.py merge-negatives \
    --dataset <prepared dataset> --ood ood-data --output <new directory> --ratio 0.10
```

Pipeline mode reads the camera view (Top, Left, Right, Rear) from each prepared file
name and passes it to the classifier, as the station does, and reports each view. Use
the weights the station runs: `top_calibrated_checkpoint` in the report must be true,
otherwise the Top refinement, the rotated pass and the finger recovery do not run.

`merge-negatives` never changes the source dataset, the validation split or the test
split. It refuses a dataset that contains symbolic links, and a `data.yaml` whose `train`
entry is not the relative path `train/images`, because either could make the copy write
to or train on the source. Never train or tune on the `benchmark` pool. Measured results and limits are in
the [gate evaluation](../docs/audits/ood-gate-evaluation-2026-11-13.json) and
[AI Models](../docs/knowledge/AI%20Models.md). The gate does not recognise unsupported
banana cultivars: any banana passes the COCO verifier.

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app entry + lifespan
│   ├── config.py             # Pydantic settings (.env loader)
│   ├── api/                  # Route layer
│   │   ├── deps.py           # Shared dependencies (auth, DB)
│   │   └── v1/               # Versioned routes
│   ├── models/               # SQLAlchemy ORM models
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/             # Business logic
│   │   ├── camera_manager.py # Multi-camera capture pipeline
│   │   ├── classification.py # YOLO26 inference
│   │   ├── spoilage.py       # RFR spoilage prediction
│   │   ├── fusion_engine.py  # Multi-camera result merging
│   │   ├── sensor_reader.py  # DHT22 serial reader
│   │   └── scan_service.py   # Scan pipeline orchestrator
│   ├── ws/                   # WebSocket layer
│   ├── core/                 # Security, DB, startup, exceptions
│   └── ml/                   # Model weights
├── captures/                 # Runtime captured images
├── tests/                    # Test suite
├── .env                      # Environment variables
└── requirements.txt          # Python dependencies
```

## API Documentation

Once running, visit:
- **Swagger:** http://localhost:8000/docs  
- **ReDoc:** http://localhost:8000/redoc  
- **Health:** http://localhost:8000/health  

## Initial administrator and temporary credentials

On an empty database, startup requires `BOOTSTRAP_ADMIN_PASSWORD` in the backend environment. Choose a unique password of 12–72 UTF-8 bytes and set `BOOTSTRAP_ADMIN_USERNAME` if the default username `admin` is unsuitable. No password is logged. Sign in with those credentials, replace the password, then remove the bootstrap secret from the environment. Existing accounts are unchanged; rotate any old shared credentials through User Management.

Account creation and administrator resets generate unique temporary credentials. The authenticated administrator sees them once in a handoff dialog and shares them privately with the owner. They are not stored in browser storage or audit logs. Owners must replace them on first use; setup authorization expires after ten minutes and cannot access normal APIs or WebSockets. An expired setup requires signing in again.

`setup.bat` / `setup.sh` retain the familiar environment, dependency installation and
optional demo-seeding sequence. **Choosing Yes at the reset-and-seed prompt deletes existing
application database records, including accounts, scans and history, and recreates the demo
dataset.** Choosing No or pressing Enter keeps the database unchanged. `seed.bat` / `seed.sh`
offer the same prompt. Use a development database and stop the application before resetting.

The wrappers invoke `python seed.py --reset-demo` only after Yes. The command requires a
non-production environment and `BOOTSTRAP_ADMIN_PASSWORD`. Reset, maintained migrations
and generated records share one PostgreSQL transaction/advisory lock; failure rolls back
the reset. Only ORM-managed application tables and the migration marker are recreated;
there is no fallback that cascades into unrelated tables.

Plain `python seed.py` requires an empty database and refuses existing records with a clear
message and exit code 20. Configuration, connection and other failures still fail. `start.bat`
and `dev.bat` retain their previous startup behavior and do not run this demo reset.

The 25 synthetic scans use stored two-decimal temperature/humidity readings and the existing
`calc_vpd` function (kPa, three decimals), intake treatment, fallback spoilage estimates,
original-result snapshots and linked history events. These are demo predictions, not model
validation or training measurements. History explicitly names **Demo Seeder**, with no
invented human actor. This generates new demo records; it does not backfill historical fields.
The fixture operator is inactive with no usable PIN; an administrator must reset credentials
and activate it for use. Camera images/detections and print jobs are not fabricated or executed.

Role and active-status changes revoke existing sessions. Promoting an operator clears their PIN while preserving the profile and scan-history links. Demotion requires an administrator to issue a new temporary PIN through **Reset PIN**; old PINs are never restored. PIN login, PIN setup/change and administrator PIN reset require the current Operator role. Account updates serialize the last-active-admin check inside the database transaction; a waiting request also rechecks its administrator's status, role and session version.

## Existing database upgrades

From `backend/`, run `python -m app.core.migrations` with the deployment environment configured. This initializes missing tables and applies the versioned revisions in `migrations/versions/`. Startup runs the same upgrade before reading users or seeding accounts, and fails if an upgrade cannot complete. PostgreSQL uses a transaction advisory lock so simultaneous starts serialize schema changes.

For a current ERD/data-dictionary view, see [the schema reference](../docs/bananavision_schema_current.sql) and [the table dictionary](../docs/schema_tables.md). They describe the application schema at head `0010_notification_read_receipts`; they are documentation references, not an upgrade path.

- `0001_session_revocation` adds a non-null `user_account.token_version` with default `1` to older schemas, preserving account credentials and existing rows.
- `0002_feature_engineering` adds missing batch lifecycle/treatment and engineered-feature columns from the earlier manual SQL migration. Already-present columns are retained. Historical engineered values remain unchanged; the schema upgrade does not recompute model features.
- `0003_system_configuration` adds canonical configuration, revision checks, applied state, and stable physical camera mappings.
- `0004_maintenance_state` adds durable non-restored maintenance/authentication-generation state.
- `0005_scan_record_history` adds scan revisions, immutable history, mutation receipts and deletion tombstones. The historical v1 adapter preserves legacy values without inventing history.
- `0006_inventory_provenance` preserves known intake origins, marks ambiguous legacy NULL links as unverified, and adds expiring browse snapshots. Administrator provenance review requires evidence/reason and uses revision/idempotency/history controls; it never invents an old intake link.
- `0007_prediction_print_jobs` adds persisted print-job records for prediction labels without replaying label work during restore.
- `0008_windows_label_jobs` adds durable Windows label jobs without changing the compatibility revision.
- `0009_camera_slots` moves saved camera names and physical indices from repeated `system_config` CSV/JSON fields into one normalized `device` row per slot, then drops the unused derived `operator_profile.total_scans` and `flagged_scans`. Camera names stay unique (including on legacy SQLite schemas whose inline constraint is promoted to a named index before table recreation). New archives use v4; strict v1/v2/v3 adapters convert their saved camera arrays into slots and retain available evidence. The downgrade is blocked because dropping saved slots or scan history is destructive.
- `0010_notification_read_receipts` replaces the shared `app_notification.is_read` flag with an `app_notification_read` receipt keyed by `(notification_id, user_id)`. Existing private read flags become one receipt for their owner; existing broadcast read flags become receipts for active accounts. New `scan_flagged` notifications are stored once with a null `user_id`, so every account tracks its own read state. The downgrade is blocked because dropping receipts would lose read history. Because this is a pre-release schema, archive format v4 was revised in place; local v4 archives created before this revision must be recreated.
- `alembic_version` records successful upgrades. Fresh databases and databases already upgraded manually adopt the revision without duplicate columns. Automatic downgrade is intentionally blocked because removing session revocation or historical columns would discard safeguards/data.

Before upgrading the station, take a PostgreSQL backup and rehearse against a disposable copy. Confirm `alembic_version.version_num` matches the current migration head (`0010_notification_read_receipts`), `user_account.token_version` exists, existing accounts can sign in, and pre-reset tokens are rejected. Include revision/history writes and v1/v2/v3/v4 archive restoration and deleted-intake/legacy-stock exclusion in the disposable rehearsal. The scan-summary CSV is insufficient for database recovery.

Regression tests use disposable databases. To include PostgreSQL cases, set `BANANAVISION_TEST_DATABASE_URL` to a test PostgreSQL URL; the tests create unique temporary schemas and remove only those schemas. On Windows, if the default pytest temporary directory is inaccessible, pass `--basetemp` pointing to a writable test directory whose parent exists.

## Power commands and data retention

Power endpoints check the command exit code and report OS acceptance, not proof of completed reboot. They close admission and drain active scans and admitted work before dispatch; a drain timeout rejects the operation. Windows schedules power actions after ten seconds; Linux/macOS use a one-minute delay and noninteractive `sudo -n`. Configure host permissions and service autostart using [the kiosk guide](../docs/kiosk-autostart-guide.md); verify these on the deployed station.

The retention worker checks every six hours and respects the enable flag. It removes only expired, unreferenced UUID capture directories. Persisted scans, active-stock evidence, notes, corrections, audit history, and referenced images are protected; enabling retention does not shorten recorded history. Failed scans clean up their own unpersisted captures. The scan-summary CSV is a report, not a restorable backup. System Configuration provides versioned station backups with application data and referenced evidence, archive validation, and confirmed in-place restore with rollback protection.

## WebSocket

```
ws://localhost:8000/api/v1/ws?token=JWT&rooms=kiosk,dashboard
```

Events: `scan:started`, `scan:capturing`, `scan:captured`, `scan:detecting`, `scan:detected`, `scan:analyzing`, `scan:completed`, `scan:failed`, `sensor:update`, `device:status`, `notification`

Every connection, incoming message and outgoing delivery checks JWT expiry and the account's current role, status and session version. Idle connections recheck every 15 seconds. Invalid sessions close with code `4001`; the frontend clears the matching session and returns to login. A socket from before credential rotation cannot clear the newer token. Operators may subscribe only to `kiosk`; administrators may also subscribe to `dashboard`, `devices` and `admin`.


## Stable browse snapshots

Scan Logs and shared scan-history loading request account/session/filter-bound snapshots.
Pages and a snapshot CSV use the same captured rows/values; Refresh starts a new capture.
Snapshots expire after ten minutes and are invalidated by role/session/station-generation
changes. At most four captures per account are retained; expired entries are removed on
new capture. They are excluded from station backups. A capture is capped at 50,000 rows
and 20 MiB serialized data and rejects overflow without publishing a partial result.
Narrow the filters for browsing; complete filtered streaming CSV remains available without
a snapshot token for larger populations. That CSV reflects the export query time rather
than a previous browse capture. Production-volume tuning still requires deployment testing.
