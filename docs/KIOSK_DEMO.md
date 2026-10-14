# Kiosk demo and automatic labels

## Demonstrate without a banana or IoT station

1. Restart the backend through the usual procedure to load the new endpoint.
2. Open **Kiosk** and select the operator using the existing PIN chooser.
3. Turn on **Demo mode**, near the source and Scan Now controls.
4. Select a saved prediction from **Demo prediction**.
5. Press **Run Demo & Print**. The existing progress and result panel display the
   saved prediction, and FastAPI queues **one 40 × 30 mm DEMO label**.
6. Check the queued/submitted/failed status in the result panel. Use **RETRY PRINT**
   after fixing a printer fault. Inspect for partial output before retrying.

The configured TP870 S must be connected to the backend computer to physically
print. Demonstration requires at least one completed scan accessible to the signed-in
operator; it does not require a new intake. An empty history disables the demo button.
The saved prediction's original timestamp and values remain visible. No new camera
capture, banana detection, YOLO inference, or Random Forest prediction is performed.
The existing live-preview UI continues working independently.

The demo does not add a scan, change stock, alter the active intake, change recent
scan totals, or broadcast a real scan completion. **Accept demo** and **Flag demo**
only exercise the kiosk controls locally. The original saved scan is never flagged
or accepted into a different intake by these actions. The only persisted addition
is the printer job receipt. Its QR ends with `TEST=DEMO`, and its text panel says DEMO.

After a lost HTTP response, **Retry demo request** uses the same request UUID and
sample instead of creating another print batch. Retries of failed printer jobs reuse
the same immutable label. If the source is later corrected, replaying that request
still displays the values captured for its original label.

## Switch back to real scanning

Turn **Demo mode off**. The existing **Scan Now** button, operator selection, intake
requirement, camera pipeline, inference, database persistence, Accept, and Flag for
Review flow continue working. No demo code needs to be removed or reimplemented.

When ready to automatically print one label after each real successful scan, set:

```dotenv
BANANAVISION_AUTO_PRINT=true
BANANAVISION_PRINTER_NAME=TP870 S
BANANAVISION_LABEL_WIDTH_MM=40
BANANAVISION_LABEL_HEIGHT_MM=30
```

Restart the backend to load the settings. **Auto print defaults to false** so the
existing real scan behavior stays opt-in while physical printing is being evaluated.
The demo queues its one label independently of that setting.

The existing public tracking QR displayed for real scans is preserved. Physical
prediction labels encode the saved values as described in `PRINTING_INTEGRATION.md`.
The demo preview encodes its exact DEMO label payload.

## Integration and isolation

- `frontend/src/pages/Kiosk.tsx`: explicit mode switch, sample selection and existing
  result/action components. Normal `handleScan` still calls `ScanContext.startScan`.
- `frontend/src/hooks/useKioskDemo.ts`: local demonstration progress/result state;
  no calls to `acceptCompletedScan`, inventory writes, capture or inference. Pending
  requests/results are scoped to the current account and role.
- `POST /api/v1/scans/{scan_id}/kiosk-demo` in `backend/app/api/v1/printing.py`:
  authenticates and applies the existing scan ownership boundary, snapshots the saved
  prediction, commits a one-label DEMO job and schedules the existing background worker.
  Client-supplied prediction values and quantities are rejected.
- `backend/app/api/v1/scans.py::trigger_scan`: optional automatic-label boundary
  **after `execute_scan_pipeline` returns its committed final prediction**. The ML
  pipeline and its websocket completion events do not trigger printing themselves.
- `backend/app/services/print_jobs.py::queue_automatic_label`: deterministic UUIDv5
  from the scan UUID and automatic-label action. Existing print-job primary-key
  uniqueness plus atomic worker claiming prevents duplicate automatic jobs, including
  concurrent requests. Manual Scan Logs batches can still use their own UUIDs.
- `frontend/src/components/KioskPrintStatus.tsx`: reads print status and allows
  deliberate retry. Mounting, Strict Mode, polling, refresh and acceptance do not print.

Existing print records deserialize with `demo=False`; the marker is stored in their
existing JSON snapshot. This stage requires no new database migration. Printing
failure preserves the committed prediction. Queue failures return the prediction
with a visible `print_error` instead of reporting the scan as failed.

## Physical checks still required

Start with one DEMO label. Check 40 × 30 mm alignment, readable summary, phone-decoded
values and the DEMO marker. Test offline failure and explicit retry. Then turn demo
off and verify a real banana scan and its LIVE label when the hardware/banana is ready.
Demonstration verifies the kiosk/printing integration; it does not verify live camera
capture or model accuracy. Windows SUBMITTED confirms spooler acceptance, not paper output.

No physical print, live database, camera capture, or station power operation is used
by automated regressions. Browser tests exercise the real Kiosk component with mocked
APIs, and backend tests replace GDI with a mock and use isolated fixtures.

## Verification (2026-10-14)

- Backend suite: **289 passed, 1 deselected** in 177.63 seconds. The previously
  flaky idle-WebSocket test passed separately (**1 passed** in 4.46 seconds).
  Includes real concurrent automatic-slot tests on disposable PostgreSQL schemas.
- Backend kiosk regressions cover demo isolation, saved-value payloads, one-label
  batches, offline retry, immutable replay after a correction, ownership, opt-in
  automatic printing, duplicate prevention, failed inference/commit and queue failures.
- Frontend kiosk browser suite: **4 passed**, exercising the real Kiosk component
  with mocked authentication/APIs. Covers demo actions without data writes, retry,
  lost acknowledgements, empty history, operator selection and normal intake/Scan Now.
- Full frontend suite retains **five known baseline failures**: two connectivity
  tests, two dashboard review-link expectations and one maintenance camera UI test.
  The four new kiosk tests passed in that full run as well.
- `npm run typecheck` and `npm run build`: **passed** (production build 10.58 seconds).
- Frontend lint: **43 existing errors, 8 existing warnings**; all five new frontend
  files are clean. Changed-file diagnostics match committed HEAD exactly.
- Backend Ruff: **638 existing diagnostics**; new and changed printing files add
  no diagnostics. One old long-line diagnostic was removed by wrapping the trigger signature.
- `git diff --check`: **passed**. The rendered 1600 × 1000 mocked demo was visually inspected.
- Disposable PostgreSQL at `127.0.0.1:56918` was stopped and its generated directory
  removed after tests. No live station database, physical cameras, power, or printer
  was exercised. No deployment, commit or push was performed.

Changed files for this kiosk stage:

- Backend: `.env.example`, `app/config.py`, `app/api/v1/printing.py`,
  `app/api/v1/scans.py`, `app/schemas/printing.py`, `app/schemas/scan.py`,
  `app/services/prediction_label.py`, `app/services/print_jobs.py`,
  `tests/test_kiosk_printing.py`, `tests/test_printing_postgresql.py`.
- Frontend: `src/pages/Kiosk.tsx`, `src/hooks/useKioskDemo.ts`,
  `src/components/KioskPrintStatus.tsx`, `src/context/ScanContext.tsx`,
  `src/lib/api.ts`, `src/lib/scanData.ts`, `src/types/index.ts`,
  `src/types/printing.ts`, `tests/kiosk.auth.tsx`, `tests/kiosk.fixture.tsx`,
  `tests/kiosk.test.mjs`.
- Documentation: `docs/KIOSK_DEMO.md`, `docs/PRINTING_INTEGRATION.md`,
  `TASK_PROGRESS.txt`, `docs/history/2026-10-14-before-kiosk-demo.txt`.
