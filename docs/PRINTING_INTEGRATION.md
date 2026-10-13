# Manual prediction labels from Scan Logs

## Current scope

The first stage prints existing saved predictions from **Scan Logs → QR icon →
Print labels**. Choose **1–10 labels per request**. No IoT station, camera capture,
new scan, or inference is required. The existing scan and inventory are unchanged.
Automatic printing from **Scan Now is deferred**, as requested, until the user
has checked the physical labels.

The modal QR encodes the saved prediction values, not the old tracking-page URL.
The label contains the scan UUID, ripeness, estimated spoilage days, confidence
(the application's existing 0–100 percentage), and available temperature/humidity.
The model predicts days, so the label uses `SPOILAGE_DAYS`; it does not invent a
LOW/HIGH risk category. `TEST=LIVE` means actual saved data, not a new inference.
The short human-readable panel uses the same snapshot. Scan Detail's existing
tracking QR/browser-print action is outside this first-stage change.

## Setup on the Windows backend host

1. Install the official Grozziie TP870+/TP870 S Windows driver and connect USB.
2. Select/create **40 mm wide × 30 mm high** stock in Windows Printing preferences.
   Set driver copies to **one**; requested label quantity is sent as document pages.
3. Install backend dependencies with `python -m pip install -r requirements.txt`
   from the backend virtual environment. `qrcode` already exists; `pywin32` is
   added with a Windows-only marker. No additional Pillow dependency is needed.
4. Configure the following settings in the backend environment and restart through
   the normal application procedure:

   ```dotenv
   BANANAVISION_PRINTER_NAME=TP870 S
   BANANAVISION_LABEL_WIDTH_MM=40
   BANANAVISION_LABEL_HEIGHT_MM=30
   ```

The printer must be attached to the **FastAPI machine**, not just the browser's
computer. The exact configured queue is used; no default-printer fallback exists.
This stage has no auto-print setting or automatic scan hook.

Schema setup follows `backend/README.md`: application startup initializes missing
tables and applies migrations, or the operator can run `python -m app.core.migrations`
as part of an authorized deployment. Revision `0008_windows_label_jobs` follows
the existing `0007_prediction_print_jobs` compatibility placeholder. No live
station migration or restart was performed during development.
Manual batches use the separate `scan_label_print_job` table so any historical
automatic-print table associated with revision 0007 is left intact.

## Flow and implementation map

1. `frontend/src/pages/Logs.tsx` mounts `ScanLabelPrint` inside the existing QR modal.
2. `frontend/src/components/ScanLabelPrint.tsx` reads the label preview. Mounting,
   Strict Mode, polling, and refresh never submit printing.
3. Only its `submit` click handler calls `POST /api/v1/scans/{scan_id}/print` with
   a request UUID and integer quantity. The server independently enforces 1–10.
4. `backend/app/api/v1/printing.py::print_saved_scan` loads the scan through the
   existing Admin/Operator ownership checks. Client prediction values are not accepted.
5. `backend/app/services/print_jobs.py::create_job` snapshots the actual prediction,
   printer, media dimensions, and quantity, and commits the batch receipt.
6. A FastAPI background task calls `print_jobs.submit_job`. An atomic database
   claim prevents duplicate workers; the claim commits before touching Windows.
   Blocking GDI work runs through the existing `run_blocking` helper and station
   coordinator, so maintenance draining recognizes the operation.
7. `backend/app/services/windows_printer.py::print_prediction_label` validates
   installed queue/status and DEVMODE, calls the three-argument
   `win32gui.CreateDC("WINSPOOL", printer_name, devmode)`, and submits one document
   with the requested number of pages using StartDoc/StartPage/EndPage/EndDoc.
   The QR has a four-module quiet zone and integer-pixel black modules on white.
   GDI errors abort the document; font wrappers are deselected and released.
8. The existing modal polls read-only status briefly and shows queued, submitted,
   or failed. `SUBMITTED` confirms Windows accepted the document, **not** physical
   label output. A spooler job ID is stored when Windows returns one.

The Windows implementation was copied and adapted from the verified tester.
There is no runtime dependency on that project, and the tester was not edited.

### Endpoints

- `GET /api/v1/printers`: installed Windows queues and readiness metadata.
- `GET /api/v1/scans/{scan_id}/label`: saved-value QR payload, panel, and media settings.
- `POST /api/v1/scans/{scan_id}/print`: `{ "request_id": "UUID", "quantity": 1 }`.
- `GET /api/v1/scans/{scan_id}/print-jobs/{job_id}`: submission status.
- `POST /api/v1/scans/{scan_id}/print-jobs/{job_id}/retry`:
  `{ "expected_attempt": 1 }`, only for the matching failed attempt.

All require existing authentication and scan authorization. Missing/incomplete
predictions and invalid quantities fail before a print task is scheduled.

## Duplicate protection and retry

The print-job primary key is the explicit action's request UUID. PostgreSQL
`ON CONFLICT` admits only one batch for repeated/concurrent delivery of that UUID;
reusing it for another scan, quantity, or account is rejected. The UI retains the
same UUID and quantity after a network error and suppresses overlapping clicks.
A worker can claim each queued attempt only once. Read endpoints never create jobs.

**Print another batch** is a deliberate new request and can legitimately print
more labels. The 10-label limit is per request, not a lifetime limit per scan.
This stage intentionally does not add a unique constraint on prediction ID:
multiple manual batches are supported. A future automatic-print integration
must add its own unique automatic-job key and post-commit scan hook.

On failure, the complete application error is stored and displayed. **RETRY PRINT**
reuses the same batch, snapshot, printer, dimensions and quantity; an atomic
status/attempt check prevents repeated retry delivery from duplicating it.
Check for partially printed labels before retrying a batch: an error after some
pages or after Windows accepted data cannot prove that nothing was printed.

After a backend crash or database failure during submission, a job can remain
QUEUED with uncertain Windows status. It is deliberately **not automatically
replayed**. Inspect Windows Print Queue and physical output before deliberately
starting a new batch. The UI stops polling after about 30 seconds and offers
read-only status refresh. Keep the modal open while checking/retrying a batch;
closing it does not cancel a background print.

Print receipts are station-local operational records, excluded from the existing
versioned data archive allowlist. They follow scan/account deletion by FK cascade
and are not restored or replayed from an archive. Ordinary database backups include
the table. Archive formats and maintenance behavior are unchanged.

## Troubleshooting and physical acceptance

- Not installed / inaccessible: confirm the exact queue name and driver permissions
  under the Windows account running FastAPI.
- Offline / paused / paper error: check power, USB, loaded media, and Windows queue;
  clear the fault, then explicitly retry the failed batch.
- Driver replaced dimensions: configure 40 × 30 mm stock and driver copies = 1.
- QR too dense / clipped: check media dimensions and printable driver area. The
  renderer rejects fewer than two pixels per module rather than shrinking further.
- Windows accepted but nothing printed: inspect the spooler and device. Do not
  treat the API's SUBMITTED result as physical success.

Start with **one label from a saved scan**. Verify the 40 × 30 mm alignment,
readable side panel, and phone-scanned payload against that scan's prediction.
Then request two labels and check that exactly two print. Test offline failure
and explicit retry. These physical checks remain for the user; development tests
mock Windows printing and a test guard rejects physical GDI submission under pytest.

## Future Scan Now integration (not implemented)

The existing path is `Kiosk.handleScan` → `ScanContext.startScan` →
`backend/app/api/v1/scans.py::trigger_scan` →
`scan_service.execute_scan_pipeline` / `_execute_scan_pipeline`.
The latter calls `camera_manager.capture_all/save_captures`,
`banana_pre_detector.detect`, `banana_classifier.predict`, `fusion_engine.fuse`,
and `spoilage_predictor.predict`; it persists and commits the final prediction
before broadcasting completion. That successful commit boundary is where a
future unique automatic print job belongs. No scan/ML/persistence behavior was
changed in this manual-print stage.

## Changed files for this stage

Backend implementation:

- `backend/app/api/v1/printing.py`
- `backend/app/api/v1/router.py`
- `backend/app/config.py`
- `backend/app/models/print_job.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/printing.py`
- `backend/app/services/prediction_label.py`
- `backend/app/services/print_jobs.py`
- `backend/app/services/windows_printer.py`
- `backend/migrations/versions/0008_windows_label_jobs.py`
- `backend/.env.example`
- `backend/requirements.txt`

Frontend implementation:

- `frontend/src/components/ScanLabelPrint.tsx`
- `frontend/src/types/printing.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/pages/Logs.tsx`

Verification and documentation:

- `backend/tests/test_printing.py`
- `backend/tests/test_printing_postgresql.py`
- `backend/tests/test_migrations.py` (extends the user's pre-existing revision update)
- `backend/tests/test_backup_archive.py`
- `frontend/tests/printing.fixture.tsx`
- `frontend/tests/printing.test.mjs`
- `docs/PRINTING_INTEGRATION.md`
- `TASK_PROGRESS.txt`
- `docs/history/2026-10-13-before-manual-printing.txt`

The user's pre-existing `0007_prediction_print_jobs.py` placeholder is preserved
without edits. The separate printer tester and the Scan Now path are unchanged.

## Verification results (2026-10-13)

- Backend tests used isolated temporary working directories. Final suite:
  **280 passed, 1 deselected** in 170.09 seconds. The deselected
  `test_socket_subscriptions_accept_once_and_idle_revocation` passed separately
  (**1 passed**) after intermittently hanging during a repeat.
- PostgreSQL cases used a disposable cluster on `127.0.0.1:56917` with unique
  schemas. The server was stopped. Automatic approval review blocked deletion
  of its directory with `blocked by policy`; stopped database files remain at
  `C:/Users/Kent/AppData/Local/Temp/bv-print-pg-af9c797c13fc4b72a6103baa27afe942`.
- Printing, concurrent claims, migration, and archive checks passed. GDI was
  mocked throughout. Pywin32 is installed locally; no printer was exercised.
- Full frontend suite (`node --test --test-concurrency=1 tests/*.test.mjs`):
  **82 passed, 5 failed**. All five failures reproduced from untouched HEAD in
  a temporary source copy: two WebSocket expectations in `connectivity.test.mjs`,
  two review-link expectations in `dashboard.test.mjs`, and the camera
  partial-application test in `maintenance.test.mjs`.
- Final focused browser run (`tests/printing.test.mjs tests/scanrecords.test.mjs`):
  **18 passed**. Covers quantity limits, explicit submission, Strict Mode,
  repeated clicks, failed-job retry, lost-response identity, and existing scan UI.
- Browser fixtures used installed Edge (`PLAYWRIGHT_CHANNEL=msedge`); Chrome
  was unavailable. Playwright and Ruff were installed in a temporary tool directory.
- `npm run typecheck` and `npm run build`: **passed**.
- `npm run lint`: **43 errors, 8 warnings**, existing diagnostics only. New
  printing files are clean; changed existing frontend diagnostics match HEAD.
- `ruff check backend/app backend/tests`: **639 existing diagnostics**. All new
  Python files pass the configured rules; changed existing files add no diagnostics.
- `git diff --check`: **passed**. Scoped implementation and pre-existing changes
  reviewed. No commit, push, deployment, live DB migration, camera use, or print.

Physical acceptance remains pending. Mocked submission does not establish that
the TP870 S has printed or that a phone can decode the real 40 × 30 mm label.
