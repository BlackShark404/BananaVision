# Testing and Validation

## Merge of team main, migration id and saved threshold — 2026-11-18

- **Why PostgreSQL runs matter:** the merged tree failed 23 backend tests with a disposable
  PostgreSQL 16 cluster and only 5 without it. 18 failures came from a migration id longer
  than `alembic_version.version_num` (`VARCHAR(32)`); SQLite does not enforce the length.
  Run the migration and seed tests on PostgreSQL before a release.
- **New tests (each failed before its fix):**
  - `test_migrations.py::test_every_migration_id_fits_the_alembic_version_column`;
  - `test_configuration.py::test_a_saved_threshold_of_85_is_kept`.
- **Tests changed:** `test_invalid_legacy_configuration_is_not_promoted` expects the saved
  85 again; `frontend/tests/maintenance.test.mjs` expects "Reset All Settings" to give 80.
- **Result after the fixes:** the 10 affected backend test files pass on PostgreSQL (269
  passed, 1 skipped), including all 23 tests that failed.
- **Not rerun after the fixes:** the full backend suites, the frontend suite, tsc, ESLint
  and build. Before the fixes: frontend 396 of 397 (the stale reset test), tsc and build
  passed, ESLint 36, Ruff 639.

## Auto-flag only for low confidence — 2026-11-18

- **New backend tests:**
  - `test_auto_flag_reasons.py` (13):
    - the threshold is the only flag (80.0 at an 80% threshold is not flagged, 79.9 is);
    - different finger counts, cultivar and ripeness disagreements, a view conflict and
      missing or unsupported views are observations, not flags;
    - a saved confident 4-camera scan with counts 10/7/7/9 is unflagged;
    - the saved System Config threshold decides;
    - dropped boxes and observations appear after "; noted:" in the activity entry;
    - a flagged scan records "Auto-flagged: …" in history, the activity entry and the
      notification.
  - `test_review_auto_flags.py` (8, one on PostgreSQL):
    - the preview lists every decision and changes nothing;
    - `--apply` needs an active administrator;
    - only flags the rule would not set are removed, each with a history entry and an
      audit row;
    - a second run changes nothing;
    - a scan a person handled meanwhile is left alone;
    - the command line returns 2 without `--admin`.
- **Tests updated on purpose** (they pinned the removed rules): `test_classification_fusion.py`
  (19 tests now assert the observation instead of a flag; 7 renamed), `test_scan_trigger.py`,
  `test_ood_gate.py`, `test_colour_check.py`, `test_finger_count_rules.py`,
  `test_rotation_consensus.py`, `test_evaluate_finger_count.py`.
- **Mutation checks:** flagging again on differing counts, and dropping the "person handled"
  rule in the cleanup command, made 6 of the new tests fail.
- **Review follow-up** (2 lenses with skeptics; 7 of 8 findings confirmed, 5 after merging
  duplicates). Tests added first, each failing before its fix:
  - a confidence equal to the threshold is not flagged at any threshold from 1 to 100
    (7, 14, 28, 55 and 56 failed before);
  - an operator's flag request on an already flagged scan is kept by the cleanup;
  - a status change is not a flag decision;
  - scans from before scan history (corrected, noted, or without a creation entry) are
    kept;
  - a failure on one scan does not stop the others;
  - an administrator deactivated during the run stops it;
  - the command refuses to run outside the backend folder;
  - Scan Detail mentions clearing the flag only on a flagged scan (frontend).
- **Results after the review fixes:** backend 1428 passed, 38 skipped with a disposable
  PostgreSQL 16 cluster; 1352 passed, 114 skipped without it. Frontend 392/392;
  `npx tsc -b` and `npm run build` pass. ESLint 36 and Ruff 644 (baselines). The Manila
  time guard covers the new script.

## Audit logging overhaul — 2026-11-17

- **New backend tests** (89 in total):
  - `test_audit_log.py` (20): writer, text hygiene, vocabulary, the "only through
    `audit.py`" guard, deferral and flush, `access_denied` throttling (including a real
    signed-in user), anonymous cap, no query strings, no secret shapes.
  - `test_audit_auth.py` (14): the lockout row survives the 429, `login_blocked` per
    window, unrecognized usernames never written, inactive and temporary-credential
    sign-ins, `pin_login`, credential actions, change-password/PIN rate limit,
    setup-token rejection; a PostgreSQL deadlock guard.
  - `test_audit_maintenance.py` (22) and `test_audit_maintenance_postgresql.py` (4): backup
    created/failed/downloaded without secrets, re-auth failure and limit, restore outcome
    exactly once and safe when the actor is gone, power and retention events, deferral
    during a restore.
  - `test_audit_records.py` (25): old → new details, no-ops skipped, role/status actions,
    profile avatar without data, scan details without note text, `scan_failed`, exports
    (stream session, fail closed), print requests.
  - `test_audit_read.py` (4): `as_of` paging stays stable while rows are inserted.
- **New frontend tests:** `activityactions.test.mjs` (the action map matches `AuditAction`
  in `audit.py`; labels, critical set) and `activitylog.test.mjs` (badges, critical count,
  the second page reuses `as_of`).
- **Results:**
  - Backend: 1290 passed, 38 skipped with a disposable PostgreSQL 16 cluster; 1215 passed,
    113 skipped without it.
  - Frontend: 389/390. The failing analytics refresh test is the known clock race; it
    passes 9/9 when run alone, twice.
  - `npx tsc -b` and `npm run build` pass. ESLint 36 (down from 40). Ruff 644 (baseline).
- **Test safety:** an autouse fixture refuses connections to the configured station
  database, because audit writes look up the session factory at call time.
- **Review follow-up** (4-lens review with skeptics; 14 of 15 findings confirmed, 9 after
  merging duplicates):
  - Backend tests added:
    - egress refused in recovery and maintenance, written at once while power is pending;
    - the backlog is written once by overlapping writers, and kept after a failed write;
    - a full queue warns;
    - failures against real accounts are not capped;
    - the file log shows only committed `record()` rows;
    - future-stamped rows stay listed;
    - a refused snapshot export writes no `data_exported`.
  - The frontend boundary test now changes only the boundary. A mutant without the
    boundary check fails it.

## Admin status correction and intake reopen — 2026-11-17

- **New backend tests:**
  - `test_scan_records.py`: `test_admin_corrects_sold_and_spoiled_scans_to_any_status`,
    `test_restoring_stock_reopens_a_depleted_intake`,
    `test_leaving_stock_does_not_reopen_a_depleted_intake` (For Processing, Spoiled),
    `test_single_scan_sale_keeps_intake_active`,
    `test_operator_cannot_change_a_sold_or_spoiled_scan` (8 cases) and
    `test_operator_cannot_reopen_a_depleted_intake`.
  - `test_mutation_events.py`: `test_reopened_intake_event_follows_commit_and_replays_once`
    and `test_reopen_is_rolled_back_and_unpublished_when_commit_fails`.
  - `test_scan_records_postgresql.py`: `test_restore_reads_intake_status_after_parent_lock`
    (a mutant that read the intake before the lock failed it) and
    `test_restore_and_bulk_on_one_intake_do_not_deadlock`.
- **New frontend tests:** `scanrecords.test.mjs` (Scan Detail menu for each current status,
  Spoiled → For Processing, Sold → In Stock, In Stock → Sold, and the Logs dialog note) and
  `inventoryStatusChange.test.mjs` (12 note cases). The new-behaviour tests failed before the
  change.
- **Results:** backend 1198 passed, 38 skipped with a disposable PostgreSQL 16 cluster, and
  1130 passed, 106 skipped without it. Frontend 377/377. `npx tsc -b` and `npm run build`
  pass. ESLint 40 and Ruff 644 (baselines).

## Fusion collapse recovery, compact-Rear split, and bottom-left platform trim — 2026-11-16

- **New regression tests:**
  - `backend/tests/test_classification_fusion.py`: `test_compact_rear_recovers_higher_lower_tier_without_inflating_eleven_rear`, `test_side_collapse_and_partial_rear_recovery`, `test_wide_ripe_lakatan_below_twelve_rear_recovers_flank_split`, and `test_top_second_tier_preserves_horizontal_wing_detections`.
  - `backend/tests/test_colour_check.py`: `test_top_platform_edge_drops_bottom_left_trim_only`.
- **Targeted backend suites (10 modules, fresh temp cwd):** `test_classification_fusion.py`, `test_finger_count_rules.py`, `test_colour_check.py`, `test_top_view_inference.py`, `test_evaluate_finger_count.py`, `test_ood_gate.py`, `test_manila_time_guard.py`, `test_scan_trigger.py`, `test_scan_logs.py`, `test_time_and_writes.py` — **383 passed, 3 skipped** in `45.75 s`.
- **Full backend suite (fresh temp cwd, without `BANANAVISION_TEST_DATABASE_URL`):** **1120 passed, 71 skipped, 12 failed, 13 errors** (`392.76 s`); all 12 failures / 13 errors confined to pre-existing Windows path/symlink/quote assertions in `test_export_station_training_set.py` (`1`), `test_fetch_training_assets.py` (`6`), `test_prepare_ood_dataset.py` (`4` failed, `13` errors), and `test_train_finger_model.py` (`1`).
- **Offline single-view benchmark (`run_visible`, `gate=True` on `v13-yolov8-20261016/dataset/valid`, `n=137`, `banana_yolovsV2.pt`):** **`MAE=0.8832`**, **`exact=0.4891`**, **`within1=0.8613`**, **`bias=+0.1971`** (`Top` `n=31 MAE=0.5806 exact=0.6129`; `Left` `n=34 MAE=0.7941 exact=0.4706`; `Right` `n=42 MAE=0.6429 exact=0.5238`; `Rear` `n=30 MAE=1.6333 exact=0.3333`) — preserving pre-edit `curr_working_tree` (`0.8832`) vs `d2d1aa1` (`0.9270 MAE`, `0.4745 exact`, `0.8540 within1`).
- **Frontend & lint:** 10 non-browser test files (`105 tests`) **passed** (`node --test`); `npm run typecheck` and `npm run build` (`3073` modules) **passed**; `npm run lint` retained `40` pre-existing issues (`35` errors, `5` warnings, `0` frontend edits in this round); `uvx ruff check` confirmed `test_colour_check.py` clean and **0 new diagnostics** on edited backend lines (`647` repo baseline untouched).
- **Limits:** `graphify` / `tree-sitter` wheel build and ICM MCP are unavailable in this Windows session; Playwright browser suites and PostgreSQL-only tests did not run.

## Post-screenshot box/filter/fusion fixes — 2026-11-15

- **New regression tests:**
  - `backend/tests/test_finger_count_rules.py`: `test_centered_sub_box_inside_horizontal_parent_deduplicates_both_passes`, `test_pass3_drops_far_ripeness_doorway_box_and_recovers_four_box_rear`, `test_side_view_horizontal_hand_recovers_right_flank_and_high_conf_small_tip`, and `test_top_bottom_left_trim_overhang_duplicate_dropped_but_real_bl_finger_kept`.
  - `backend/tests/test_classification_fusion.py`: `test_eleven_rear_lakatan_unripe_does_not_inflate_by_summing_lower_flanks` and `test_wide_ripe_lakatan_recovers_once_right_flank_lower_tier_is_detected`.
  - `frontend/tests/detectionBoxes.test.mjs`: `centered square or portrait tip inside wide horizontal parent deduplicates cleanly`.
- **Targeted backend suites (temp dir outside repo):** 11 modules (`test_classification_fusion.py`, `test_finger_count_rules.py`, `test_rotation_consensus.py`, `test_top_view_inference.py`, `test_colour_check.py`, `test_evaluate_finger_count.py`, `test_ood_gate.py`, `test_manila_time_guard.py`, `test_scan_trigger.py`, `test_assigned_fixes.py`, `test_detection_sensitivity.py`) — **350 passed, 3 skipped** in `56.83 s`.
- **Full backend suite (without `BANANAVISION_TEST_DATABASE_URL`, temp dir):** **1119 passed, 71 skipped, 12 failed, 9 errors** (`246.15 s`); all 12 failures / 9 errors confined to the pre-existing Windows path/symlink checks in `test_export_station_training_set.py` (1), `test_fetch_training_assets.py` (6), `test_prepare_ood_dataset.py` (4 failed, 9 errors), `test_train_finger_model.py` (1).
- **Offline single-view benchmark (`evaluate_finger_count.py visible --gate` on `v13-yolov8-20261016/dataset/valid`, `n=137`, `banana_yolovsV2.pt`):**
  - Before -> After: `MAE` **`0.9124 -> 0.8832`**, `exact_rate` **`47.45% -> 48.91%`**, `within_one_rate` **`85.40% -> 86.13%`**, `bias` **`+0.2117 -> +0.1971`**, `overcount` **`51 -> 49`**, `undercount` `21 -> 21`; `Right` MAE `0.7381 -> 0.6429` (`45.24% -> 52.38%` exact), `Top` MAE `0.6452 -> 0.5806` (`58.06% -> 61.29%` exact).
  - Stage trace (`trace_valid_stages.py`, `645.2 s`): gated `TP=1142, FP=80, FN=41`, precision `0.932 -> 0.935`, recall `0.964 -> 0.965`.
- **Processing latency:** `FusionEngine.fuse` measured at `523.26 ms` over `1000` calls (`0.52 ms/scan`); `_suppress_trim_overhang_duplicates` measured at `193.14 ms` over `100` `1280x900` frames (`1.93 ms/frame`); zero additional YOLO inference passes.
- **Frontend & lint:** 10 non-browser test files (`105 tests`) **passed** (`node --test`); `npm run typecheck` and `npm run build` **passed**; `npx eslint src/lib/detectionBoxes.ts tests/detectionBoxes.test.mjs` **0 problems** (`40` pre-existing repo lint issues untouched); `uv tool run ruff check` found **0 new diagnostics** on edited files (`28` pre-existing across the 4 backend files; `649` repo baseline untouched).
- **Limits:** `debug-screenshots/2026-11-15/` lacks raw unannotated camera frames and manually verified physical totals; Playwright browser tests and PostgreSQL-only tests did not run in this environment.

## Multi-camera top-tier and wide two-tier fusion fix — 2026-11-15

- **New unit/regression coverage (`backend/tests/test_classification_fusion.py`):**
  - `_radial_top_fan_detections`, `test_top_radial_wings_and_slender_primary_fingers_stay_in_primary_tier`, `test_radial_latundan_ripe_fan_reconstructs_fourteen_not_ten`, `test_wide_two_tier_hand_with_top_wing_fans_and_inner_tips_avoids_collapse`, and `test_rear_capture_collapse_recovers_from_both_stacked_sides`.
- **Targeted backend suites (temp dir outside repo):** `test_classification_fusion.py`, `test_finger_count_rules.py`, `test_rotation_consensus.py`, `test_top_view_inference.py`, `test_colour_check.py`, `test_evaluate_finger_count.py`, `test_ood_gate.py`, `test_manila_time_guard.py`, `test_scan_trigger.py`, `test_assigned_fixes.py`, `test_detection_sensitivity.py` — **344 passed, 3 skipped** in `20.99 s`.
- **Full backend suite (without `BANANAVISION_TEST_DATABASE_URL`):** **1112 passed, 74 skipped, 11 failed, 8 errors** (`134.10 s`); all failures/errors were confined to Windows path/temp-symlink assertions in the four helper-script test suites (`test_export_station_training_set.py`, `test_fetch_training_assets.py`, `test_prepare_ood_dataset.py`, `test_train_finger_model.py`). Targeted suites ran cleanly after the final newline edit.
- **Single-view validation (`evaluate_finger_count.py visible` on `v13-yolov8-20261016/dataset/valid`, `n=137`, `banana_yolovsV2.pt`):** `MAE=0.7664`, `exact=0.4745` (`65/137`), `within1=0.854`, `bias=+0.4015`, `undercount=20`, `overcount=52` (`Top` `n=31 MAE=0.6452 under=2`; `Left` `n=34 MAE=0.7647 under=3`; `Right` `n=42 MAE=0.7381 under=9`; `Rear` `n=30 MAE=0.9333 under=6`; `warnings=[]`).
- **Processing latency:** `FusionEngine.fuse` measured at `731.06 ms` over `1000` calls (`~0.73 ms/scan`), adding no extra inference pass.
- **Frontend & lint:** 10 non-browser test files (`104 tests`) **passed** (`253` browser-based `.test.mjs` cases failed without Playwright installed); `npm run typecheck` and `npm run build` **passed**; `npm run lint` retained `40` pre-existing baseline issues (`35` errors, `5` warnings); `uv tool run ruff check` found `0` new diagnostics in modified lines (`14` pre-existing `E501` lines across both edited files; `644` repo baseline diagnostics).
- **Environment limits:** `graphify` CLI and `graphify-out/` are absent in this checkout; no disposable PostgreSQL cluster was started so PostgreSQL-only tests were skipped.

## Radial-fan geometry, connected outliers, split-cultivar recovery, and two-tier fusion — 2026-11-14

- **Benchmark (`evaluate_finger_count.py visible` on `v13-yolov8-20261016/dataset/valid`, `n=137`, `banana_yolovsV2.pt`):**
  - Baseline: `MAE=0.8540`, `exact=0.4015 (55/137)`, `within1=0.8467`, `bias=+0.2555` (`undercount=34`, `overcount=48`; `Top` `MAE=0.8710`, `undercount=11`).
  - After Round 1 + Round 2 fixes: `MAE=0.7664`, `exact=0.4745 (65/137)`, `within1=0.8540`, `bias=+0.4015` (`undercount=20`, `overcount=52`; `Top` `MAE=0.6452`, `undercount=2`; `Right` `MAE=0.7381`, `undercount=9`; `Rear` `MAE=0.9333`, `undercount=6`; `Left` `MAE=0.7647`, `undercount=3`).
- **Station 4-camera scans and Kiosk crops:**
  - 6 station scans: Scan 1 Green Latundan (`15` actual) `12 -> 15`; Scan 2 Green Lakatan 1-tier (`10` actual) `Top 9 -> 10`, fused `10 -> 10`; Scan 3 Cardaba Unripe (`14` actual) `13 -> 14`; Scan 4 Latundan Ripe (`14` actual) `10 -> 14`; Scan 5 Lakatan Ripe (`21` actual) `13 -> 20–21`; Scan 6 Mixed 15-finger hand (`15` actual) `9 -> 14–15`.
  - Earlier Kiosk main-preview crops (`finger-count-chat-images`, `1280x900`, CPU inference `~305–523 ms`): `036 Top` `10 -> 13`, `052 Rear` `10 -> 11`, `057 Top` `8 -> 10`, `059 Rear` `5 -> 9`, `015 Right` `11 -> 13`.
- **Backend tests:** `test_finger_count_rules.py` (including 8 new regression tests), `test_rotation_consensus.py`, `test_top_view_inference.py`, `test_colour_check.py`, `test_classification_fusion.py` (including two-tier and single-tier multi-camera fusion tests), `test_evaluate_finger_count.py`, `test_ood_gate.py`, and `test_manila_time_guard.py` from a fresh temporary working directory: **293 passed, 3 skipped**.
- **Frontend tests & build:** `node --test` (`detectionBoxes.test.mjs`, `manilaTime.test.mjs`): **14/14 passed**. `npm run typecheck` and `npm run build` passed. `npx eslint src/lib/detectionBoxes.ts` passed with 0 problems (repo-wide lint retains 40 pre-existing problems).

## Cultivar, counting, and RFR corrections — 2026-11-14

- Final affected backend suite: **445 passed, 3 skipped**, run from a fresh temporary
  working directory. Covered classification, rotation, fusion, crown colours, OOD,
  scan trigger/persistence, spoilage, backup archives, count evaluation, and Manila guards.
- A broader run with disposable PostgreSQL 18 on loopback port 53156 produced
  **1159 passed, 6 skipped, 12 failed, 11 errors**. The cluster was stopped and its
  temporary directory removed. Failures concern existing export/training asset/OOD
  preparation tools and Windows paths. Running the four failing modules from a temporary
  copy of unchanged HEAD reproduced **12 failed, 153 passed, 1 skipped, 12 errors**;
  parallel OOD preparation failures vary by case. This is not an all-green full suite.
- Frontend broad run: **323 passed, 2 failed test files**. Both failures were existing
  Windows URL-path conversion errors in `estimates.test.mjs` and
  `shelfLifeWindow.test.mjs`; both now use `fileURLToPath`. The corrected files plus
  counting geometry passed **40 tests**. Kiosk/scan-page browser regressions separately
  passed **40 tests**. The broad frontend suite was not rerun after these focused fixes.
- Typecheck and production build passed. Build retains the existing large-chunk warning.
  Full frontend lint has **35 errors, 5 warnings** in existing files; changed files pass
  scoped lint. Backend Ruff has **634 diagnostics**, equal to unchanged HEAD, with no
  added diagnostic keys. No broad autofixes were applied.
- New `test_rotation_consensus.py` reproduces both 11-primary-to-14 recovery and the
  14-box-to-11 mixed-ripeness counting bug. `test_scan_trigger.py` verifies that optional
  `counts_as_finger` decisions survive label harmonization through HTTP and WebSocket
  responses while keeping raw hypotheses. Frontend geometry/marker tests mirror this.
- Real packaged RFR loaded successfully from a temporary working directory. Natural
  Unripe outputs at 36.4°C/52.6% RH were 11.046/9.982/14.049 days for
  Lakatan/Latundan/Cardaba; treatment and matrix details are in [[AI Models]].
- Physical station counts, live camera images, the station's selected treatment and
  loaded RFR artifact were not inspected. No deployment or live data changes occurred.
- Graphify CLI/graph and project ICM tools/database are absent in this checkout;
  source inspection and existing Obsidian notes supplied the context. No integrations
  were initialized or replaced.

Comprehensive guide to testing strategies, verification requirements, test runners, and isolation boundaries across BananaVision.

## Colour check — 2026-11-14

- `backend/tests/test_colour_check.py`: synthetic frames painted with the HSV profiles
  measured on the station screenshots (`tests/data/station_colour_profiles_2026-11-14.json`):
  the two crowns and the curtain are dropped; unripe, pale overexposed, washed-out,
  semi-ripe and dark-corner fingers are kept; a spotted finger with a dark-cornered box is
  kept; Overripe is exempt; no frame means no check; the threshold setting acts; the
  second (recovery) and rotated passes are covered; a station scan with a crown box is
  flagged with the activity note; shaded fingers (value ~45-50) are kept; a dark fragment of
  a kept finger is skipped without flagging; a scan whose only boxes are crowns is rejected
  and the rejection note counts the colour drops. `test_evaluate_finger_count.py` covers the
  `colour_check=off` config and the physical-mode review flag.
- `backend/tests/test_export_station_training_set.py`: archives built with the real
  `create_archive` from in-memory SQLite stations; labels, clamping, class index, flagged and
  corrected-only filters, counts.csv, the physical folder read back by the evaluator, refused
  output folders, tampered archives, Manila timestamps, no database access.
- `backend/tests/conftest.py` turns the check off for modules that use blank placeholder
  frames (np.zeros), unless the module sets `COLOUR_CHECK = True`.
- Measurement method (scratch, photos not stored): boxes traced from overlay strokes and
  label tags, the 18 % fill removed, central-region HSV per box.

## Finger-count rules and YOLO26 head — 2026-11-13

Decision: [[Development Decisions]]; rules: [[AI Models]].

- `backend/tests/test_finger_count_rules.py`: stacked lying fingers stay two (axis-aware
  rotated dedup, unit and rotated Top pass); a hand box gives way to 3 upright or 3 lying
  fingers, fragments of one finger stay one; the wood-beside-an-unripe-hand case, ties,
  adjacent stages, weak or mixed-cultivar majorities, two labels on one finger; the
  second pass keeps a hidden and a flank finger but not the window frame or the plate on
  Left/Right/Rear; each rule's setting restores the earlier count; a station scan with a
  ripeness outlier is flagged and its activity entry says so.
- `test_inference_head.py` (fake 8.4.40 head: the head is fixed before warmup, every
  call carries it, `checkpoint` sends nothing, fused/absent heads, settings validation) and
  `test_inference_head_integration.py` (real COCO `yolo26n.pt` + Ultralytics sample
  photo: IoU changes the boxes only on the NMS head).
- `test_ood_gate.py`: the hand-box cases now expect the split (and a flag when the gate
  is the reason it did not happen); the recovery-gate test runs with and without the
  within-hand rule; new `test_random_hands_obey_the_gate_contract`.
- Review follow-ups (independent review, 2026-11-13): restored fingers vs the rotated
  Top pass's repeats, the confident detached outlier, near boxes that do not outnumber
  far ones, a ripening (unripe + semi + ripe) hand, a lying hand's second-pass extent, a
  finger still inside a box that stays, and two gate-contract cases (an off-evidence
  fragment that decides the split is flagged; one that changes nothing is not). The real
  COCO test now proves warmup set up the predictor and runs a full prediction.
- Full backend after these changes: 903 passed / 38 skipped with a throwaway
  PostgreSQL 16 cluster, 837 / 104 without; Ruff `app tests` 634 (baseline 635).
- Tooling tests (synthetic data, fakes, no network): `test_evaluate_finger_count.py`,
  `test_train_finger_model.py`, `test_fetch_training_assets.py` (checksums, zip-slip,
  links, special files, size ratio, token never printed). Each script was also
  smoke-run with real Ultralytics on synthetic images.
- Every count change is unmeasured on banana photos; use
  `scripts/evaluate_finger_count.py` once a teammate uploads the weights and dataset.

## Public QR page shows only scanned data — 2026-11-13

Decision: [[Development Decisions]]; page notes: [[Frontend]].

- `frontend/tests/public-scan.test.mjs` at a 390×844 phone viewport: the first screen
  shows cultivar, ripeness, the countdown with `Est. 5–7 days from scan`, scan date and
  footer time. Scan ID, `Est. Fingers` and temperature stay collapsed under "Scan details"
  until the native disclosure is opened; `In Stock` never renders even when the API sends
  `inventory_status`. The page has no link, `<button>`, `role="button"`, `role="link"` or
  `onclick` element and no "log in", "login", "sign in", "website" or "dashboard" text; no
  sideways scroll; one unauthenticated request. Overflow is checked
  against `document.documentElement.clientWidth` (390): with `isMobile` emulation Chromium
  widens `window.innerWidth` to fit wide content, so `scrollWidth <= innerWidth` cannot
  fail (found in review; a 600 px element read 616/616).
- A signed-in staff viewer (`window.publicScanViewer`) stays on `/track` with the same
  page. Not-found shows no button; a failed load shows only "Retry", which then loads the
  data. The landing page (test-only route `/scans/landing-check`) keeps "Access
  Dashboard", which still opens `/login`.
- `backend/tests/test_public_scan_track.py`: a scan with a `ScanImage` row returns the
  same public field set with `images == []` and no camera ID or file name in the body;
  the staff detail response still lists the image.
- `frontend/tests/public-scan-app.test.mjs` mounts the real `App` (real routes,
  providers, `AuthProvider` through `tests/app.auth.tsx`, 401 handling) with a stored staff
  session whose staff requests all answer 401. On `/track/fixture-scan` the data shows, no
  staff request or app WebSocket is made, the URL and stored session stay unchanged after
  5 minutes and a focus/visibility event, and there are no controls. On `/dashboard` the
  same session still loads staff data and still goes to `/login`. The harness serves
  `/track` paths (`dashboard.browser.mjs`). The real app lazy-loads pages and React reveals
  Suspense content on a timer, so this file lets the test clock run; StrictMode may fetch
  `/track` twice in development (the first is cancelled).
- The four new browser tests and the backend test fail on the previous code (two login
  buttons, the staff redirect, an extra "Log in", a leaked capture path). The real-App QR
  test fails on the previous `App.tsx` (navigated to `/login`).

## "Est." wording on AI-estimated numbers — 2026-11-13

Decision: [[Development Decisions]]; per-page table: [[Frontend]].

- `frontend/tests/estimates.test.mjs`: singular, plural, zero and missing finger counts;
  the per-field correction rule (another field corrected keeps "Est."; an override with no
  AI baseline keeps "Est."); `estimateText` never prefixes `Unknown`/`—` and never doubles.
- Browser tests: Kiosk result card and recent scans (AI, corrected and another-field-
  corrected rows, `Est. 1 finger`), shelf-life values in recent scans; Scan Detail and
  QC labels for AI and corrected counts and the `Fingers` correction inputs; Scan Logs
  column `Est. Fingers`; public QR `Est. Fingers`; Inventory `Est. Total Fingers`,
  `(Est. 7 fingers)`, ripeness rows, `Est.` shelf-life badges, and plain totals when every
  scan was corrected.
- `backend/tests/test_estimate_wording.py`: export headers and the notification/activity
  wording (`Est. 13 fingers`, `Est. 1 finger`).
- Kiosk test: a later `scan:changed` event (live events never carry `original_ai_result`)
  keeps a corrected count plain; before the fix it turned back into `Est.`.
- The new tests were also run against an untouched copy of the previous code, where they fail.

## Asia/Manila time zone guards — 2026-11-13

Decision: [[Development Decisions]]; helper: [[Frontend]].

- `frontend/tests/manilaTime.test.mjs` runs with `TZ=America/Los_Angeles`: helper output
  at 15:59:59Z and 16:00:00Z (Manila midnight), the year boundary, the date-picker day,
  and a source scan of `src/` that rejects any date formatting outside Asia/Manila.
- Browser tests in non-Manila browsers: Kiosk header clock (Los Angeles), Scan Detail
  footer and notes, QC list, Logs date-picker "today" (Los Angeles), and export file names
  of Activity Log, Delivery Intake and Quality Control with the clock at
  2026-10-01T16:30:00Z (New York; expects `…-2026-10-02`).
- `backend/tests/test_manila_time_guard.py` runs with the process clock in Los Angeles:
  log line time and `+08:00` marker, XLSX part and backup manifest zip times, and a
  source scan of `backend/app`, `backend/scripts`, `backend/*.py` and root scripts for
  `datetime.now()` without a zone, `utcnow`, `today()`, `time.localtime`/`strftime`,
  `fromtimestamp` without a zone and `writestr` with a plain name.
- Every new test was run first without the fix and failed.

## Audit of the 2026-11-12/13 commits — 2026-11-13

Scope: Caveman skills and MCP entry, the OOD gate (#3), its doc corrections (#4, #5) and
the shelf-life countdown (#6), plus the merges with teammates' work. Decisions are in
[[Development Decisions]]; model numbers in [[AI Models]].

- **PostgreSQL tests ran for the first time in the cloud session.** A throwaway
  PostgreSQL 16 cluster on a local socket (no TCP), with `BANANAVISION_TEST_DATABASE_URL`
  set; every test creates and drops its own schema. Result: 830 passed, 38 skipped (37
  Windows-only setup scripts, 1 missing RFR artifact). The real COCO verifier test
  (`test_ood_gate_model.py`) ran with `backend/yolo26n.pt`.
- **Contract fix with a parity check.** `prediction_bounds` now gives no window for a
  value `spoilageDisplay.ts` shows as "Unknown". A script compared both rules on 1,396
  generated strings: 218 disagreements before, 0 after.
- **Lint baseline by `git archive`, not a worktree.** ESLint 40 problems repo-wide and
  18 on the touched files, both equal to `0c74c73`; Ruff 634 equal.
- **Screenshots** of every countdown and rejection state in light and dark, with the
  repository's own browser harness (`tests/dashboard.browser.mjs`) and mocked API.
- **Codex Security** scoped scan of the scan API and OOD files: 0 findings.
- **MCP checks:** the Codex CLI 0.167.1 lists both entries of `.codex/config.toml`, and a
  live MCP handshake with the Caveman server returned 4 tools. The Antigravity plugin
  file now uses `serverUrl`, the documented key for remote servers.
- **Known flaky test:** `kiosk-pin.test.mjs` "stalled swap …" pauses the browser clock
  at a Node timestamp and fails under heavy CPU load ("Cannot fast-forward to the
  past"). Idle: 0 failures in 6 runs before #3 and 6 at HEAD.

## Public HTTPS access — 2026-11-13

Decision and topology are in [[Development Decisions]]; client behavior is in [[Frontend]].

- **Backend cases.** `test_camera_preview.py` proves a preview returns `401` without a session, the media dependency accepts a bearer header or a `?token=` query value, and an invalid frame rate still returns `422` before any capture. `test_settings_security.py` proves production rejects missing, placeholder and short signing secrets, accepts two strong 48-byte values, and development keeps its placeholders.
- **Backend results.** Full suite from a fresh temporary working directory: **764 passed, 104 skipped** (PostgreSQL-only cases; no disposable cluster). Targeted camera, settings, connectivity and security tests: **47 passed, 4 skipped**.
- **Production startup.** A fresh process with `APP_ENV=production` and strong secrets reports `docs_url`, `redoc_url` and `openapi_url` as `None`; a placeholder secret raises `ValidationError` before the app starts.
- **Frontend results.** The seven affected browser suites (connectivity, public scan, kiosk, dashboard, maintenance, printing, scan records) passed **142/142**. Connectivity was rerun alone on the final socket file: **6/6**. `npm run typecheck` and `npm run build` pass.
- **Lint baseline.** ESLint reports **40 problems**; the changed frontend files account for **9**, the same count as their `HEAD` versions, so this change adds none. Ruff reports **24** findings on the changed backend set, equal to `HEAD`.
- **QR build wiring.** A temporary `.env.production.local` with `VITE_PUBLIC_BASE_URL` produced the configured origin in the bundle; the file was removed and the normal build restored.
- **Requires Playwright.** These browser tests need `PLAYWRIGHT_MODULE` when Playwright is not installed under `frontend/node_modules`.
- **macOS tailnet smoke test (2026-11-13).** The production `deploy/Caddyfile` validated with Caddy 2.11.9 and served the built SPA on loopback. The backend ran with `APP_ENV=production` on a disposable PostgreSQL database, a temporary capture directory and camera index `99`. Over Tailscale Serve HTTPS (`https://khens-macbook-air.tailae02f0.ts.net/`): `/health` returned `200`; `/`, `/dashboard`, `/docs` and `/openapi.json` returned `200`, `200`, `404` and `404`; the preview endpoint returned `401` without a session; login, first-time password setup and the Admin Dashboard worked in Chromium with a trusted certificate (`window.isSecureContext` true). All 22 API calls stayed same-origin; two `wss` sockets connected; a manual ping received `pong`; `GET /api/v1/cameras` returned `200`; preview returned `401` without a token and `404` with one because index 99 does not exist. HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` were present and `Server` was absent. The Serve config, processes, database and temp secrets were removed afterwards.
- **macOS helper scripts (2026-11-13).** `deploy/start-mac-tailnet.sh` and `deploy/stop-mac-tailnet.sh` were exercised end to end with a disposable database, camera index `99` and no sensor. The start path downloaded Caddy, verified GitHub's asset digest, validated the Caddyfile, built the frontend with the tailnet QR origin, started uvicorn and Caddy, enabled Serve, and reached `/health` over HTTPS. Login through the proxy returned `requires_password_change` for the seeded admin; `/docs` was `404` and preview was `401`. The stop path removed Serve, stopped the matching PIDs, freed ports `8000`/`8080`, and was idempotent on a second run. A second start while running was refused. The test database and temp files were removed.
- **Not verified.** No real Funnel, public URL, Windows Mini PC, camera, sensor, station database or deployment was used. Funnel WebSocket behavior and a browser-to-station run remain untested. The temporary Caddy binary came from the official release because the Homebrew build failed on disk space; Homebrew's Go dependency remains installed.

## Live shelf-life window — 2026-11-13

Rule and reasons are in [[Development Decisions]]; what each page shows is in [[Frontend]].

- **One rule table, two suites.** `backend/tests/data/shelf_life_window_cases.json` holds
  the whole-day bounds, the unreadable values, the day-by-day progression and the
  roll-forward cases. `backend/tests/test_shelf_life_window.py` checks it against
  `inventory_policy.py`, and `frontend/tests/shelfLifeWindow.test.mjs` checks the
  progression, roll-forward and labels against `src/lib/shelfLifeWindow.ts`.
- **Backend cases:** day 0, +1, +2, +3 and +7 for `1-3`; created 23:50 PHT and read
  00:05 PHT counts one day; no change at UTC midnight; zone-less stored instants are UTC;
  single-day and zero estimates; unreadable values and missing timestamps give no window;
  a clock before the scan never goes negative. Detail, public track and list responses at
  five ages leave the stored string, timestamp, revision and `updated_at` unchanged. The
  bulk-status event carries the window. Sold records receive it on every response.
  Frozen snapshots do not store it, read the same two days later, and fit the size limit
  exactly as before. A value too large for a number gives no window instead of an error.
- **Frontend cases:** the unit test runs with `TZ=America/Los_Angeles` to prove the date
  comes from Asia/Manila. Browser tests cover the public page rolling over at Manila
  midnight with no new request, Scan Logs (countdown first, estimate beneath, Sold row
  unchanged, a row saved before the field existed), Scan Detail on day 0 to +7, Sold
  stock, Quality Control and Kiosk recent scans.
- **Results:** backend **759 passed, 104 skipped**, against **685 passed, 104 skipped**
  on `3dd755b`. Frontend **319 of 319** tests passed, 39 of them new. Type check and build
  pass; lint (14) and Ruff (11) show the same existing findings on the changed files as
  before, none new.
- **Review:** four independent lenses, each finding checked by a second reviewer. Nine
  findings were fixed or covered by new tests and two questioned the user-chosen Scan
  Logs layout. Details are in `TASK_PROGRESS.txt`. Ten planted defects on a scratch copy
  each made the backend tests fail.
- **Not covered here:** the 104 PostgreSQL-only tests, and the live station.

## Out-of-distribution rejection — 2026-11-13

Design, thresholds and limits are in [[AI Models]]; the kiosk state is in [[Frontend]].

- **Gate evaluation** (`backend/scripts/evaluate_ood_gate.py gate`, Open Images V7 pools,
  report `docs/audits/ood-gate-evaluation-2026-11-13.json`). Held-out benchmark: near-OOD
  frame rejection **96.72 % → 97.31 %**, far-OOD **99.86 % → 100 %**, generic banana frames
  accepted **90.07 %**, AUROC **0.976**, FPR at 95 % TPR **2.83 %**. Box support keeps
  **94.92 %** of annotated banana boxes and passes **7.3 %** of near-OOD and **0.16 %** of
  far-OOD object boxes. Thresholds were chosen on the calibration pool only.
- **Laptop pipeline run (2026-11-13):** `pipeline` mode with `banana_yolo26s.pt` on the
  benchmark pool. OOD images that end with a cultivar: near-OOD **76.42 % → 3.28 % →
  2.99 %** and far-OOD **61.24 % → 0.14 % → 0.00 %** (no gate → earlier gate → OOD gate).
  That checkpoint is not Top-calibrated (`top_paths.active` false). See [[AI Models]].
- **Laptop labeled-split run (2026-11-13):** `pipeline --id-split` with `best.pt` of run
  `v26s_run2_zick` on 416 labeled test photos (337 scans). Photos that end with a cultivar:
  **416 → 409 → 408** (no gate → earlier gate → OOD gate); finger boxes **3 534 → 3 467 →
  3 453**; no wrong cultivar in any variant. The OOD gate's extra loss (1 photo, 14 boxes)
  is in the Rear view only. Reports: `docs/audits/ood-pipeline-ood-pool-2026-11-13.json`
  and `docs/audits/ood-pipeline-labeled-split-2026-11-13.json`.
- **Not measured:** any result on a registered Top-calibrated checkpoint, the number of real
  scans the gate would flag, and four-camera fusion. No retraining was run.
- **Backend:** full suite **685 passed, 104 skipped** (PostgreSQL-only cases; no disposable
  cluster in this environment), against **582 passed, 104 skipped** on the team's
  `0c74c73`. The 103 new tests cover gate logic, classifier filtering (including cluster-box,
  rotated-pass, canonical-rotation and occluded-finger-recovery cases), the 422/503/WebSocket contract, the audit row, the dataset script (leakage, path
  safety, truncated, incomplete and non-JPEG payloads, merge isolation), evaluation metrics,
  and the real COCO verifier on 12 synthetic frames (blank, noise, blur, yellow/green shapes).
- **Frontend:** 280 browser tests including 5 new kiosk cases. Full run **279 passed,
  1 failed** (397.1 s). The failure was `kiosk-pin.test.mjs` "PIN verification sends
  once…", which stopped in its own setup with `clock.pauseAt: Cannot fast-forward to the
  past`: it installs the page clock and then pauses it at a `new Date()` taken in Node, so
  the two clocks can race. The test, its fixture and the harness are unchanged by this
  work, and the file passed **15/15 on three reruns**. Typecheck and production build
  passed (existing >500 kB chunk warning); lint **40 problems (35 errors, 5 warnings)**,
  unchanged baseline.
- **Ruff:** new files clean. Changed backend files **43 findings, the same as on
  `0c74c73`**; no introduced diagnostic.
- **Review:** an independent design review before the tests, then four separate reviews
  of the finished change (correctness, security, API/UI contract, tests and documentation).
  They raised 20 concrete points; each was addressed, and code defects are pinned by
  regression tests. Seven tests were checked by mutation: replacing the full JPEG decode,
  removing the redirect refusal, removing the image-ID leak check, removing the shared
  notice id, and removing each of the three classifier gate hooks made the matching test
  fail. A further review after merging the team's `0c74c73` raised 8 points (three in the
  classifier gate, one in the evaluation script, four in the notes); all were addressed,
  and the gate was reduced to a plain contract: its result equals the classifier's result
  for the boxes on banana evidence. A randomized confirmation (about 146,000 cases over
  first-pass, rotated Top, canonical-rotation and recovery scenarios) then found no case
  where the gate-off path differs from `0c74c73` and none against that contract, but
  2,044 Top cases where a skipped rotated-pass box changed the result without being
  counted. Every skipped rotated-pass box is now counted; the same campaign rerun
  (about 61,000 cases) shows no violation. The repository tests pin this on 300 random
  first-pass frames and 400 random Top views. The campaign also led to scan-level scoring
  in the evaluation script. No Codex Security service scan was run.
- **Running the new tests:** `test_ood_gate_model.py` needs `ultralytics` and the tracked
  `backend/yolo26n.pt`; it skips where either is missing. No test uses the network, the
  station database, captures, cameras or sensors.
- **Tools:** Graphify CLI/graph, ICM and Context7 were unavailable in this checkout, so
  the graph and project memory were not refreshed. Ultralytics behaviour for empty label
  files was checked in the installed 8.4.40 source.

## Live Logs reconciliation finalization — 2026-10-25

- Reproduced four browser failures before the fix: deferred edits, missed reconnect edits,
  off-page KPI changes, and failed reconciliation recovery. All now have passing coverage.
- Full backend with disposable PostgreSQL 18: **681 passed, 0 failed, 0 skipped**, 55 known
  enum/model fixture warnings (217.32s). Focused integration first passed **53/53**. After
  test-only lint cleanup, reconciliation/mutation cases passed **19/19**, then mutation/time-write
  fixtures **44/44**. All four fresh clusters on loopback port 55449 stopped cleanly and were removed.
- The new PostgreSQL test uses independent Admin, owning Operator and other Operator sessions:
  committed revision/flag updates and exact stored prediction strings reconcile, other-account
  data stays absent, removed rows disappear, and original snapshots remain unchanged.
- Full frontend: **266 passed, 0 failed, 0 skipped** (338.09s). The strengthened focused-control
  case then passed **1/1**, explicitly waiting for a completed live read while focus remains held
  before proving values apply after blur. Cross-session tests use separate browser contexts and
  mock HTTP/WebSocket transport; this is not a browser-to-PostgreSQL hardware station run.
- Typecheck and production build passed (36.19s build; existing >500 kB warning). Frontend lint:
  **35 errors / 5 warnings**, unchanged baseline. Configured backend Ruff: **645 findings**;
  changed files **69 versus 72 at HEAD**, **no introduced diagnostics**. New regression files are
  clean. Test import/fixture lint issues from the interrupted work were corrected.
- Scoped source/security review covered snapshot ownership, role/token/generation binding, filter
  scope, expiry, immutable exports and exact risk decisions; no actionable new finding. No new
  Codex Security service scan was launched; this is source review plus isolated regression evidence.
- Graphify refreshed successfully: **4270 nodes, 12967 edges, 250 communities** after final test cleanup; SQL extraction
  remains unavailable because `tree_sitter_sql` is absent. No paid extraction enabled.
- Earlier PostgreSQL process failures were environment-bound: isolated runs with the necessary
  execution access now succeed. No live station data, camera, sensor, OS power or deployment used.

## Final integration verification — 2026-10-24

- Full isolated PostgreSQL 18.6 suite: **658 passed, 0 failed, 0 skipped** (173.87s). Focused notification/scan-log/write suites: **72 passed** (17.30s). After test-only import/fixture-name lint cleanup, all **7 notification tests passed** again (5.67s), including four simultaneous single/read-all combinations. Disposable clusters used loopback port 55447 were stopped after each run, and their generated cluster directories were removed after verification. No station environment or hardware was used.
- Full frontend command `node --test --test-concurrency=1 tests/*.test.mjs`: **248 tests, 231 passed, 17 failed, 0 skipped** (354.82s). Edge closed during Scan Records after 31 cases; all 17 errors were closed-browser/context errors. The file-only rerun reproduced that browser closure. A fresh-browser tail selection passed **18/18** (30.13s), covering every affected case, and the adjacent CSV-export/zero-count selection passed **3/3** (7.71s). Therefore all **248 distinct cases have passing evidence across partitions**, but a single uninterrupted Edge run remains an environment/harness limitation. No assertions were removed or relaxed to mask it.
- The updated connectivity file passes **5/5**, including late-callback rejection, reconnect and authentication lifecycle. Kiosk passes **18/18** in the full run. New expired-risk and ordinary-completion notification regressions pass **2/2**.
- TypeScript and production build pass (`npm run typecheck`, `npm run build`; build 24.32s). Existing bundle-size warning remains. Frontend ESLint: **36 errors, 5 warnings**, with diagnostic signatures matching HEAD. Configured backend Ruff: **620 baseline findings**; changed files have **67 versus 68 at HEAD**, no new findings, one existing long-line finding removed. Three introduced test-only Ruff findings were corrected and checked.
- Backend warnings: one Pydantic enum fixture warning, two scikit-learn artifact/runtime version warnings and 52 feature-name warnings. No model artifact or prediction logic was changed.
- Codex Security scan `9a6cf9e9-3384-47d0-a86f-7f980d354778` completed: **0 reportable findings**, all **28 inventoried source files** covered. Daybreak entitlement unavailable; supported scoped source review plus isolated regressions used. Scan identity remains the original working-tree target at `2da9d5c`; incoming receipt integration and final corrective edits received supplemental review.
- Graphify AST update: **4128 nodes, 12475 edges, 252 communities**, without graph loss. SQL extraction was unavailable (`tree_sitter_sql` missing); SQL/migration behavior was covered by source review and PostgreSQL tests. No paid semantic extraction was enabled.
- Pre-0010 v4 archives require recreation under the incoming pre-release policy. Historical results below describe earlier checkpoints, not the final integrated tree. Cross-client status/flag edits are now broadcast; see the cross-session sync verification below.

## Cross-session sync verification — 2026-10-24

- Scope: committed scan edits (flag, quality correction, inventory status, provenance, notes),
  intake status/bulk inventory, and supplier create/update now publish post-commit events to
  account-scoped rooms. Reconnect/focus/visibility/online reconciliation and sensor freshness were
  verified together.
- Backend `tests/test_mutation_events.py`: **7 passed**. It proves the event is emitted only after
  commit, carries revision and actor evidence, routes Admin to `dashboard` and the owning Operator to
  its account-scoped `kiosk` room without exposing another Operator's scans, emits one partial scan
  event per bulk-inventory change, and that sensor freshness uses recorded_at plus server time.
- Full backend suite (isolated SQLite fixture): **603 passed, 66 skipped, 1 warning**. The default
  pytest temp directory raises `PermissionError [WinError 5]` on this host, so an explicit
  `--basetemp` is required.
- Frontend `tests/crosssession.test.mjs`: **9 passed**, driving separate browser contexts for Admin,
  Operator A and Operator B against real providers and an account/room-aware WebSocket double. Cases
  cover flag propagation with actor suppression and Operator B isolation; Page 2 row patching with
  event-id dedupe and refresh-only-on-request; deferral of a remote edit while a control is focused
  (notice only, then apply after blur); Page 1 new-scan auto-refresh; Page 2 new-scan
  notice/Later/View Latest Scans; 410+409 snapshot recovery; intake/supplier propagation with
  `updated_at` ordering; reconnect reconciliation of scans, intakes, config, users and notifications
  with frozen rows preserved; and sensor stale/live/out-of-order/age-expiry handling.
- Full frontend browser suite: **263 passed, 0 failed, 0 skipped** (~277s).
- `npm run typecheck` and `npm run build` pass; only the existing >500 kB chunk warning remains.
  Frontend ESLint reports **40 problems (35 errors, 5 warnings)**; every remaining diagnostic is
  pre-existing debt, and this change set introduced none while removing one.
- `git diff --check` is clean. No live station database, captures, physical cameras or OS power was
  used.
- Historical limitation, superseded by the 2026-10-25 verification above: PostgreSQL-backed three-session runs. `BANANAVISION_TEST_DATABASE_URL` was unset and
  PostgreSQL 18 client backends on this host fail with `0xC0000142` followed by shared-memory error
  487. No physical Kiosk pair was exercised.
- The former missed-edit/KPI boundary is resolved by the authorized live reconciliation endpoint
  described above and in [[Frontend]]. Frozen page order and exports remain intentional.

## Live Scan Logs pagination verification — 2026-10-24

- Prior implementation run, full isolated PostgreSQL 18.6: **660 passed, 0 failed, 0 skipped** (216.46s, `127.0.0.1:55440`, `Asia/Manila`). This remains the implementation-time record; the independent re-verification below could not reproduce it because PostgreSQL 18 client backends terminate on this host with `0xC0000142` (followed by shared-memory error 487).
- Independent backend re-verification (SQLite contracts, fresh temporary working directory): full suite **596 passed, 66 skipped** (115.94s); focused `test_scan_logs.py` + `test_scan_snapshots.py` **37 passed** (5.66s). The focused total includes two added cases proving Admin/Operator pending scoping and pending **409** (changed filters) / **410** (expired or unknown snapshot) behavior. PostgreSQL-specific tests remain skipped and were not re-verified in this session.
- Frontend `tests/scanrecords.test.mjs`: **54 passed, 0 failed** (96.47s), including the two final regressions for hidden-tab deferral and a failed pending-count request retaining the frozen page. The full frontend suite before those additions was **252 passed, 0 failed, 0 skipped** (340.60s); both new cases then passed in the focused file.
- `npm run typecheck` and `npm run build` pass (build 15.00s); the existing >500 kB chunk warning remains. Frontend ESLint is unchanged at the **41-problem baseline (36 errors, 5 warnings)**; every diagnostic in a changed file also exists at HEAD.
- Backend Ruff on the five changed files reports **23 findings versus 25 at HEAD**, with no new findings; the change set resolves two pre-existing import-order diagnostics. Repository-wide Ruff with the backend configuration reports 645 findings; the five changed files introduce none.
- `git diff --check` passes. No live station database, captures, physical cameras or deployment was used. Disposable PostgreSQL clusters created during the attempt were stopped and removed.
- Cross-client status/flag edits are now broadcast; missed edits also recover through automatic
  live reconciliation (2026-10-25 follow-up above).

## Live-data and persistence audit — 2026-10-23

- Audited initial loading, refresh/resume, cache and snapshot invalidation, pagination,
  CRUD persistence, false-success prevention, lost updates and concurrent writes across the
  frontend, API, services, models and PostgreSQL behavior. Fixes and remaining boundaries are
  recorded in [[Resolved Bugs]] and [[Development Decisions]].
- Backend regressions cover Depleted-intake rejection under row locking, oversized
  `source_text`, notification ownership, bulk-intake status derivation, Kiosk intake restore,
  Logs snapshot-expiry recovery, dashboard date-preserving links and PostgreSQL seed
  precision. Seed tests use unique schemas and an explicitly disposable database.
- Final isolated SQLite suite: **586 passed, 62 skipped** (117.02s).
- Final disposable PostgreSQL 18.6 suite after the seed-fixture corrections: **648 passed**
  (236.89s, `127.0.0.1:55446`). The seed contract subset passed **24/24** (44.96s). The
  cluster and its temp data directory were stopped and removed.
- Browser coverage for the changed paths passed in focused runs: **70 passed** across
  `kiosk`, `scanrecords` and `scanlogfilters`, followed by the affected Dashboard and
  Analytics reruns. After the final Scan Detail edit, `scanrecords` passed **46/46**,
  including the new in-place refresh case. Full tracked suite runs finished **246 tests,
  243 passed** (about 414s) with the two pre-existing `connectivity.test.mjs`
  socket-isolation failures at lines 34 and 45 plus one intermittent
  `kiosk resets operator selection after ...` timing failure; the Kiosk file passes
  **18/18** in isolation and the flake is unrelated to the audited paths. All
  audit-related browser cases passed.
- `npm run typecheck` and `npm run build` passed. Configured frontend lint remains at the
  **41-problem baseline (36 errors, 5 warnings)**, with no count regression. Backend Ruff
  output remains dominated by pre-existing debt; reviewed changed lines add no >100-column
  violation. `git diff --check` passes.
- The PostgreSQL seed test fixture now supplies `camera_device_ids=[0, 1, 2, 3]`, loads the
  real configured spoilage model before recomputing predictions, and compares full-precision
  model output with a numeric tolerance when storage formatting differs. This corrected
  stale test assumptions; production seed/model behavior was not changed.
- Known boundary: cross-client status/flag edits are not broadcast to Logs. Incoming
  revision 0010 replaces the former shared broadcast read flag with per-user receipts. Sensor staleness, QR label formats, camera-apply ordering
  and intake-status PATCH last-write-wins remain unchanged. No live station database,
  captures, physical cameras, OS power, restore or deployment was used.

## Current schema reference — 2026-10-22

- Updated `docs/bananavision_schema_current.sql` to Alembic revision
  `0010_notification_read_receipts`. The reference omits `alembic_version` and pg_dump
  wrapper artifacts.
- Loaded the DDL into a fresh disposable PostgreSQL 17.10 database with
  `psql -v ON_ERROR_STOP=1`. The loaded schema has **25 application tables**, **198
  columns**, **7 enum types**, **20 foreign keys** and five sequence-backed `SERIAL`
  columns.
- Verified the normalized `device.slot_index`/`device_index` columns, the notification
  receipt composite primary key and foreign keys, the absence of
  `app_notification.is_read`, the absence of `system_config` camera arrays, operator scan
  counters and `alembic_version`.
- Compared the concise and detailed capstone dictionaries: 25/25 tables, 198/198 columns,
  7/7 enum types and 20/20 foreign-key references. Table, column, type, nullability, key and
  reference fields match; default notation differs by design (`—` in the detailed version).
- Backend regressions for the runtime and migration behavior are recorded in the
  per-user notification section below. `git diff --check` passed.
- No live station database, captures, physical cameras, OS power, restore or deployment was
  used. See [[Database]] for the current schema links.

## Per-user notification read receipts — 2026-10-22

- `backend/tests/test_notifications.py` verifies that a broadcast is stored once but its
  `read` state is per account, that marking it read is idempotent, that private
  notifications are visible only to their owner, that an unauthorized mark-read returns
  404 without creating a receipt, and that read-all creates receipts only for the current
  account's visible notifications.
- `backend/tests/test_migrations.py` verifies the `0010_notification_read_receipts`
  upgrade: private read flags become receipts for their owner, broadcast read flags become
  receipts for active accounts, unread rows remain unread, `read_at` is populated and
  `app_notification.is_read` is removed.
- `backend/tests/test_backup_archive.py` includes the new receipt table in the 22 archived
  application tables and verifies v4 round-trip behavior plus strict v1/v2/v3 adaptation.
- Targeted notification, migration and archive suites: **47 passed, 2 skipped**.
- Full backend suite from a fresh temporary working directory: **545 passed, 99 skipped,
  4 failed** (32.28s). The four failures are the pre-existing macOS power-control cases
  referencing `subprocess.CREATE_NO_WINDOW`; they are unrelated to notifications. Running
  from `backend/` loads the local `.env` and adds known CORS assertion failures; the
  fresh-cwd run is the isolated result. No disposable PostgreSQL URL was configured, so
  PostgreSQL-specific cases skipped.
- Ruff is clean on the new receipt model, migration, notification API and notification
  tests. The touched legacy modules retain their pre-existing I001/E501/SIM117 diagnostics;
  no new diagnostics were introduced.
- The frontend `read` boolean contract is unchanged, so no frontend source, test,
  type-check or build was rerun.
- Archive format remains v4 because this schema is pre-release. Local v4 archives created
  before this revision must be recreated.
- No live station database, captures, physical cameras, OS power, restore or deployment was
  used. See [[Resolved Bugs]] and [[Database]].

## CSV and XLSX exports — 2026-10-22

- `backend/tests/test_exports.py` covers 206-row exports beyond pagination, account scope,
  snapshot parity, empty workbooks, exact identifiers/whitespace, DECIMAL confidence,
  formula-like text, wrapping/width contracts, invalid formats, and NULL optional values.
  The NULL regression requires CSV and XLSX to leave missing cultivar, ripeness, confidence
  and shelf-life cells blank; `N/A` remains only when the whole classification/status block
  is absent. `test_scan_logs.py` retains CSV round-trip and numeric-prefix coverage.
- Backend full suites after the audit fix: **575 passed, 62 skipped** (75.72s) on isolated
  SQLite, and **637 passed, 0 skipped** (142.80s) on a disposable PostgreSQL 18.6 cluster
  (`127.0.0.1:55439`). The cluster and its temp data directory were stopped and removed.
  Export route tests still use SQLite fixtures; PostgreSQL coverage includes seed CSV export
  and the surrounding queries, not a PostgreSQL-backed XLSX route.
- Frontend full tracked suite: **241 passed / 3 failed / 0 skipped** (298.42s, 244 tests).
  The two known connectivity failures remain (`connectivity.test.mjs` lines 34 and 45).
  The third was a pre-existing Analytics clock race (`analytics.test.mjs` line 38); that
  file passes **9/9** in isolation (25.14s), and no export code participates. All
  export-related browser cases passed in the full run, including the 9 `clientexports` cases.
- `npm run build` (`tsc -b` + Vite) passed (16.34s). Configured lint reports the baseline
  **41 problems (36 errors, 5 warnings)**; Ruff on changed backend files reports only five
  pre-existing E501 findings and no new diagnostics. `py_compile` and `git diff --check` pass.
- The temporary `frontend/tests/probe-quality-debug.test.mjs` diagnostic was removed after
  approval. It was never tracked, had no assertions and was not referenced by the suite.
- No live station database, captures, physical cameras, OS power or deployment was used.

## Normalized camera slots and archive v4 — 2026-10-22

- `test_migrations.py` upgrades a legacy SQLite schema and verifies saved camera
  arrays become contiguous `device.slot_index`/`device_index` values, existing device
  identity/status is retained, unique indexes and range checks exist, and the dropped
  configuration/operator columns are gone. It also verifies the legacy inline
  `device.camera_id UNIQUE` is promoted to a named unique index before batch table
  recreation, so a duplicate camera name still raises `IntegrityError` after migration.
- `test_configuration.py` covers slot initialization and validation, legacy scalar-row
  selection, invalid-row rejection, rename/remap/expansion behavior, UUID preservation,
  failed-commit rollback, and cleanup of an unassigned row that collides with a reused
  camera name. The API still returns the existing comma-separated `camera_ids` and
  ordered `camera_device_ids` contract.
- `test_backup_archive.py` verifies v4 round trips plus strict v1/v2/v3 upgrades,
  including legacy camera arrays becoming slots, dropped fields disappearing, and
  invalid recorded legacy types being rejected before restore.
- Post-merge targeted export/scan-log/configuration/archive/migration suites:
  **97 passed, 2 skipped**, 1 warning (6.02s).
- Full backend suite from a fresh temporary cwd (documented isolation, so the station
  `.env` is not loaded): **541 passed, 99 skipped, 1 warning** (39.95s); the only 4
  failures are pre-existing macOS power-command tests that reference
  `subprocess.CREATE_NO_WINDOW` while `power_control.py` is unchanged. Running from
  `backend/` instead loads the station `.env` (`APP_CORS_ORIGINS=["*"]`) and adds
  unrelated CORS assertion failures; the CORS middleware and tests are unmodified.
  No disposable PostgreSQL URL was configured, so PostgreSQL-specific migration cases
  skipped; `0009_camera_slots` was exercised on isolated SQLite only.
- `npm run build` (`tsc -b` + Vite) passed in 3.46s. The API contract is unchanged, so no
  frontend source edits were required.
- Ad hoc `uvx ruff check backend` reports **649 findings versus 657 at `5dcbdda`**,
  predominantly existing E501/I001/F401 debt; new migration/archive long lines were
  corrected. No claim is made that every new line is lint-clean beyond the reviewed scope.
- `git diff --check` passed. No live station database, captures, physical cameras, OS
  power, restore, deployment or Git history operation was used.

## Current demo-seed regression coverage

`backend/tests/test_seed.py` runs only with an explicitly disposable
`BANANAVISION_TEST_DATABASE_URL`, using a unique PostgreSQL schema per case. It verifies
VPD from stored-precision readings, zero preservation, treatment/spoilage consistency,
original snapshots, synthetic actor history, consumer APIs, rollback, concurrent seeding
and default refusal of existing data. Explicit `--reset-demo` tests verify replacement of
application records, reapplied migration revision, unrelated-table preservation and rollback
to the previous records/schema on failure. Missing historical VPD and actor fixtures remain
intentional and must not be backfilled.

`test_setup_scripts.py` runs copied Windows/Git Bash scripts with fake installers/seeder,
checks exit statuses and existing `.env` preservation, and never runs workspace setup.
Setup/seed wrappers require Yes at an explicit deletion prompt before passing `--reset-demo`;
No/blank answers never invoke the seeder. Plain Python invocation still refuses existing data
with exit code 20. The wrapper tests verify confirmation, arguments, missing-script errors
and failure propagation; CLI tests verify that unexpected exceptions are not swallowed.
See [the seed audit](../audits/2026-10-19-seed-compatibility.md) and
[backend setup guidance](../../backend/README.md) for scope and limitations.

## Spoilage display and at-risk consistency — 2026-10-20

- `test_scan_logs.py` verifies raw boundaries (1.9999, 2, 2.00001), zero/overdue,
  overlapping ranges, missing/invalid estimates, stock status/provenance, Dashboard
  parity, sorted pagination, snapshot/refresh consistency and full CSV membership.
  The value 2.00001 rounds to 2 in the API's display estimate but remains **not at risk**.
- `test_seed_kiosk_contract.py` compares each generated/demo and mocked Kiosk record's
  risk-filter membership with the canonical detail remaining estimate and stock eligibility.
- Backend selected suites: 56 passed (17.04s); snapshot/predictor/legacy-snapshot
  follow-up: 28 passed (6.43s), including one repeated legacy case after its assertion
  was extended. Total distinct cases: **83**, no skips. Disposable PostgreSQL and
  isolated SQLite only; model tests use disposable synthetic artifacts.
- `node --test --test-concurrency=1 tests/scanrecords.test.mjs tests/dashboard.test.mjs
  tests/analytics.test.mjs tests/scanpages.test.mjs`: **71 passed**, no failures/skips
  (113.68s). New browser coverage verifies single-value cells, server-driven warning,
  KPI filtering, page reset, sorting and refresh. Mocked screenshot reviewed.
- `npm run typecheck` and `npm run build` passed (Vite 18.82s). Configured ESLint:
  37 errors/5 warnings; Ruff: 645 errors. Changed-file diagnostic comparisons match
  HEAD exactly (no new lint debt). Logs: ignored `frontend/node_modules/.tmp/bv-spoilage-*`.
- Focused access/snapshot/export review: existing account/role/filter bindings,
  expiry, CSV escaping and stock policy remain intact. Current response schemas have
  no `at_risk` field; warnings use membership in the existing snapshot risk filter.
  No DB migration, hardware access, model change or historical backfill.

## Numeric spoilage display formatting — 2026-10-21

- Root cause: Kiosk and other consumers interpolated `spoilage_days` directly after
  the predictor began preserving the full-precision model mean. Shared display-only
  whole-day formatting now handles numeric predictions, historical ranges, units,
  unknowns and zero. Sorting, risk predicates, API fields and saved values are unchanged.
- New browser reproductions failed before the fix (4 cases). Final affected coverage:
  **109 distinct cases passed**, including 29 formatter cases and 80 browser cases in
  `scanrecords`, `kiosk`, `persistence` and `public-scan`. The main run was 107 passed/2
  failed (136.90s); both failures were corrected assertions and passed focused reruns:
  the preview now says `3 days`, and the Inventory check must exclude the fixture's
  raw-state probe. No product change was needed for those assertion repairs.
- Browser coverage checks readable Kiosk result/recent cards, Logs, Details/history,
  QC, Inventory and unauthenticated QR tracking; unrelated corrections omit
  `spoilage_days` from writes. Risk warnings use snapshot membership without an
  `at_risk` response field and survive sorting, page changes, KPI filtering and refresh.
- TypeScript and production build pass (Vite 31.53s). Configured ESLint still reports
  37 errors/5 warnings; changed-file diagnostics match HEAD, and new TypeScript files
  have no diagnostics. Logs: ignored `frontend/node_modules/.tmp/bv-spoilage-format-*`.
- Backend/model/schema code was not changed. Prior checkpoint's 119 passing isolated
  backend tests remain applicable; they were not repeated for this display-only fix.
  No live data, physical hardware, model weights or historical predictions were changed.
- Final Codex Security diff scan `3ca86d46-6b2b-4208-a47d-8dc41a825460` completed for
  `0465a7a..a58dccf`: zero findings across eight runtime files and supporting tests/docs.
  Raw correction drafts, numeric risk calculations and public/authenticated boundaries
  were reviewed, including an independent architecture pass. This was not a full repository
  security audit; no live deployment or hardware was exercised.
- After integrating incoming `main` through `f3630e9`, affected Scan Records, Kiosk,
  Dashboard and layout browser suites passed 82/82 (146.98s); ISO-day units passed 3/3.
  Sandboxed Edge initially failed at launch; approved isolated execution outside the
  sandbox passed without source changes. Typecheck/build passed again (Vite 31.43s).
  Lint matches the incoming baseline of 36 errors/5 warnings. Application source matches
  incoming `main` exactly; both sides' checkpoint history and documentation are preserved.

## Testing Philosophy & Safety Rules

As mandated by `AGENTS.md` and `docs/development-workflow.md`:

1. **Isolation from Production Systems:**
   - **Never test against the live station database, captures, physical cameras, printer hardware, or OS power.**
   - All tests run against isolated mock fixtures, in-memory databases, or disposable PostgreSQL schemas.
   - Secrets, credentials, and live `.env` files must never be read or printed during test execution.

2. **Asia/Manila Timezone Requirements:**
   - Business operations and calendar boundaries operate on `Asia/Manila` (`UTC+8`).
   - Tests verify that midnight rollover transitions (`00:00:00` Manila) properly invalidate daily caches and advance the `business_date` without depending on client machine local timezones.

3. **Evidence Before Assertions:**
   - Verification commands must be executed and their output verified before asserting that any bug is resolved or feature is complete.
   - Distinguish existing pre-existing lint debt from newly introduced regressions.

---

## Backend Test Architecture

The backend test suite is built on **pytest** and **pytest-asyncio**, testing FastAPI routes, SQLAlchemy/asyncpg query services, YOLO/RFR model estimators, and business logic.

### Safe Execution Pattern
Backend tests must run from a fresh temporary working directory with the backend directory explicitly added to `sys.path`. This prevents test processes from accidentally loading `backend/.env` or writing SQLite/cache files into production paths.

**PowerShell execution from repository root:**
```powershell
@'
import os, sys, tempfile
from pathlib import Path
backend = Path('backend').resolve()
work = Path(tempfile.mkdtemp(prefix='bv-tests-'))
os.chdir(work)
sys.path.insert(0, str(backend))
import pytest
raise SystemExit(pytest.main([
    '-p', 'no:cacheprovider', '-q', '--basetemp', str(work / 'fixtures'),
    '-c', str(backend / 'pyproject.toml'), str(backend / 'tests'),
]))
'@ | & './backend/venv/Scripts/python.exe' -B -
```

### Disposable PostgreSQL Testing
For tests requiring PostgreSQL-specific constraints, advisory locks or schema migrations:
- Set `BANANAVISION_TEST_DATABASE_URL` to an isolated, disposable cluster.
- Each test run generates and drops a unique schema.
- Once tests conclude, the temporary cluster directory and port are stopped and removed.
- Suites using this isolation include `test_seed.py`, `test_setup_scripts.py`, and `test_seed_kiosk_contract.py` (which verifies end-to-end data propagation across Kiosk, Database, Scan Logs, Scan Detail, Dashboard, Inventory, Analytics, CSV Export, and QR Tracking).

---

## Frontend Test Architecture

The frontend uses Node.js native test runner (`node --test`) driving headless Chromium/Edge via Playwright, backed by isolated Vite dev servers and mocked API/WebSocket fixtures.

### Key Test Suites (`frontend/tests/`)

| Suite | Focus Areas |
|---|---|
| `dashboard.test.mjs` | KPI card loading, skeleton states, stale data detection, WebSocket re-connections, midnight rollover, `/logs` navigation routing |
| `scanrecords.test.mjs` | Scan logs data grid, snapshot token caching, filter criteria, CSV export, QC overrides, audit trails; recorded VPD precision/zero/missing data and isolation from live sensor updates |
| `analytics.test.mjs` | Summary KPI error alerts, model confidence isolation from `ScanOriginalAiResult`, date range aggregations |
| `maintenance.test.mjs` | System config, backup creation/validation/restore, shutdown/restart accessible button labels |
| `kiosk.test.mjs` & `kiosk-pin.test.mjs` | Operator intake workflow, action spinners, PIN verification, demo simulation |
| `printing.test.mjs` | Label printing queues, GDI driver recovery, Windows spooler error handling |
| `persistence.test.mjs` & `assigned.test.mjs` | One-time admin credential setup, role-based view scoping, session persistence |
| `scanlogfilters.test.mjs` | Unit tests for query string builders (`buildScanLogsUrl`) and filter parsing (`scanLogParams`) |
| `isoday.test.mjs` | Unit tests for the local calendar-day helpers (`parseIsoDay`, `formatIsoDay`) behind the Logs date filter `YYYY-MM-DD` values |
| `adminloading.test.mjs`, `loading.test.mjs`, `operationsloading.test.mjs` | First-load vs refresh/empty/error states, delayed reads after writes, read deadlines, notification account scope, operator-list recovery and sensor freshness |
| `crosssession.test.mjs` | Three isolated browser contexts (Admin, Operator A, Operator B): post-commit flag/edit propagation, account-scoped room isolation, event-id dedupe, frozen Page 2 row patching, new-scan notices, reconnect reconciliation, 409/410 snapshot recovery, timestamp-ordered intake/supplier merges and sensor freshness/out-of-order rejection |

### Running Frontend Tests

**From `frontend/` directory:**
```powershell
# When Playwright is not locally resolvable, set PLAYWRIGHT_MODULE to the existing
# installed playwright/index.mjs path. Do not install duplicate runtimes.
$env:PLAYWRIGHT_CHANNEL = 'msedge' # or an installed supported browser

# Run all browser regression suites:
node --test --test-concurrency=1 tests/*.test.mjs

# Run specific suite:
node --test tests/dashboard.test.mjs
node --test tests/scanlogfilters.test.mjs
```

### Static Analysis & Type Checking

```powershell
# TypeScript Typecheck (0 errors required):
npm run typecheck

# Production Vite Build (also checks the referenced TypeScript projects with tsc -b):
npm run build

# Configured Linting:
npm run lint
```

---

## Historical VPD regression coverage

- `backend/tests/test_scan_logs.py` checks authenticated list/export values, operator
  scope, frozen snapshot values and older snapshots without a VPD key. VPD is
  deliberately different from a value derived from the fixture's temperature and
  humidity, so accidental recalculation is detectable.
- `backend/tests/test_spoilage_models.py` checks existing kPa formula reference
  values and explicit VPD (including zero) passed into a synthetic six-feature model.
- `backend/tests/test_time_and_writes.py` checks detail/trigger serialization.
- Ten browser cases in `scanrecords.test.mjs` cover Logs/Details with `1.555`,
  `1.25`, zero, null and omitted VPD, including unchanged output after a newer sensor
  event. Mocked visual checks cover the desktop table/detail and mobile detail grid.

The [2026-10-18 VPD audit](../audits/2026-10-18-vpd-integration.md) records exact
results and separates pre-existing connectivity/lint failures from these passing
regressions. PostgreSQL tests require a disposable cluster; synthetic model tests
do not establish the deployed model's identity or prediction accuracy.

## Station Cultivar Recognition Protocol

The October 17 station case predicts a known Lakatan bunch as Lakatan from
Top/Right and Latundan from Left/Rear, with some wrong-view scores above 90%.
Raising a detection threshold does not establish correct cultivar recognition.
The current split-camera safeguard exposes uncertainty; it is not retraining.

1. Save original, unannotated copies of all four result images into a separate
   offline case folder. Keep the checkpoint hash, saved input resolution,
   inference settings and per-camera predictions. Browser screenshots with drawn
   labels/resizing are useful evidence but are not the original model inputs.
2. Record a trusted cultivar label and a stable physical `bunch_id`. Confirm the
   physical finger total separately, and annotate every visible finger in each
   image. Cultivar ground truth follows the same physical bunch across views;
   model predictions must not become training labels without human verification.
3. Collect additional independently identified Lakatan and Latundan bunches in
   the station setup, including all four angles, lighting/placement variations,
   ripeness coverage and overlapping fingers. Review cultivar labels with a
   knowledgeable person; preserve the source dataset and edit a training copy.
4. Split by physical bunch before augmentation. All views, repeat scans and dates
   of a bunch stay together. Use separate training, validation and untouched
   station test bunches. The already examined failing bunch is diagnostic data,
   not final independent accuracy evidence.
5. Fine-tune candidate weights offline with balanced class coverage; compare with
   the unchanged baseline on validation. Freeze the checkpoint and inference
   policy before evaluating the untouched station test cohort. Do not select a
   model solely because it fixes one bunch, or favor Top/Right without evidence.
6. Report per-view cultivar confusion, per-bunch cultivar decisions, incorrect
   accepted decisions and review/abstention rate. Report box precision/recall,
   visible-count MAE and exact physical-count rate separately. Review routing
   improves disclosure and must not be reported as recognition accuracy gain.

The prepared dataset's 137 VALID images occupy only three inferred filename
groups (`cardaba_1`, `lakatan_7`, `latundan_4`). Its 137 TEST images likewise occupy
three (`cardaba_6`, `lakatan_2`, `latundan_5`). These are grouping proxies with
uncertain physical identities; they do not prove either three or 137 independent
bunches. The existing checkpoint's training provenance is also incomplete.
This limits claims about unseen bananas despite high agreement with those labels.

Ultralytics recommends [representative data and annotation review](https://docs.ultralytics.com/guides/data-collection-and-annotation/)
and [testing in deployment conditions while avoiding leakage](https://docs.ultralytics.com/guides/model-testing/).
See [[Development Decisions]] for the implemented conflict/count safeguards.

## Knowledge & Decision Links

### Scan actor attribution verification (2026-10-19)

- `test_scan_trigger.py` exercises the real trigger/persistence/detail/history path with
  mocked hardware and SQLite: authenticated IDs/names, ignored forged actor fields,
  immutable names after rename, a second operator's scan and missing-profile rejection.
  Both Operator and Admin readers see the stored creation actor without a duplicate
  unattributed initial-status event. Final file run: 11 passed.
- `kiosk.test.mjs` verifies that account switches, same-account role changes and logout
  clear Kiosk selection and disable scanning; final file run: 10 passed. Scan Records
  browser coverage distinguishes saved creation actors from unknown legacy status actors.
- Affected backend suites initially passed 60 tests; after splitting reader roles, the
  final changed-file rerun makes 61 distinct passing cases with unchanged suites retained.
  The four affected browser suites initially passed 61 tests; splitting the three session
  cases makes 63 distinct passing cases across the original run and final Kiosk rerun.
- Typecheck and production build passed. Frontend lint remains 37 errors/5 warnings;
  backend Ruff remains 652 errors after fixing a new test closure warning. No runtime,
  schema, permission, UI or historical data changes were necessary.
- Scoped authorization/persistence review found no new boundary change: identity comes
  from the server session, history reads retain ownership checks, and old actorless status
  rows are not backfilled. This is a focused source/test review, not a repository-wide scan.
  Existing full-suite connectivity failures and unavailable PostgreSQL coverage remain
  separate historical limitations; no live station or hardware was used.

### Operator Performance verification (2026-10-19)

- `backend/tests/test_analytics.py`: 15 passed. Covers historical name changes, namesakes,
  role scope, original model confidence, zero/missing values, date boundaries and combined filters.
- `frontend/tests/analytics.test.mjs`: 9 passed. Covers column removal, retained tooltip,
  sorting, filters, empty selections, both roles and 1440px/390px responsive layout.
- Related Dashboard, Scan Records and Time/Writes backend suites: 59 passed. Browser
  Dashboard, Scan Records and Operation Loading suites: 48 passed. Fixtures are isolated.
- TypeScript and production build passed. Configured frontend lint remains 37 errors/5
  warnings; backend Ruff remains 652 errors. Changed-file diagnostics match HEAD.
- Full-suite connectivity failures and PostgreSQL skips are historical baseline limits,
  not results of these focused runs. See [the operator audit](../audits/2026-10-19-operator-performance.md).

- [[Frontend]] — UI architecture, component patterns, and loading state conventions.
- [[Development Decisions]] — Architectural choices regarding snapshot retention and review queues.
- [[Resolved Bugs]] — Confirmed defect root causes and regression test references.
- [[Home]] — Knowledge base index.
- [2026-10-17 loading recheck](../audits/2026-10-17-loading-recheck.md) — current verification results, baseline failures and coverage limits.

## Finger-count inflation regression (2026-10-21)

- Synthetic Top/Left/Right/Rear counts 7/9/10/13 reproduced the previous fused 21. Regression cases now require an estimate of 13, review on positive-count disagreement, original per-camera counts, and unchanged classification confidence. Legacy fusion settings, camera labels, equal counts, duplicate boxes, and partial views are covered.
- Backend: 171 passed across `test_classification_fusion.py`, `test_scan_trigger.py`, `test_top_view_inference.py`, `test_detection_sensitivity.py`, and `test_time_and_writes.py`. The trigger regression checks the API/detail response, committed SQLite record, original AI result, and completion event. Models, cameras, printing and events use fixtures/mocks; tests run from a fresh temporary directory without loading the station `.env`.
- Kiosk browser: 17/17 passed, including estimated 13, review feedback and unchanged per-camera evidence. Typecheck and production build passed.
- Frontend lint retains 36 errors / 5 warnings; backend Ruff reports 640 findings. Comparison against HEAD confirms no new diagnostics in affected backend files; the modified browser test passes scoped ESLint.
- No station camera test, PostgreSQL run, detector retraining or physical-count accuracy validation performed. The user reports approximately 15 fingers; the fix prevents cross-view additions and does not claim to recover hidden fingers. See [[Development Decisions]].

## System Configuration layout verification (2026-10-21)

- `tests/maintenance.test.mjs`: 20 passing mocked browser cases, including camera mapping,
  revision conflicts, cross-tab save/discard, immediate-cleanup draft preservation, global
  reset, restore dialog confirmation/dismissal guards, backup persistence and power recovery.
- `tests/layout.test.mjs`: 9 passing cases in the full run. SystemConfig covers all four
  tabs, independent app scrolling, a reachable save bar and bounded restore dialog at
  1280×650, 1024×600 and 390×700. The final three-case recheck also verifies the replacement
  button remains reachable after mock archive validation expands the dialog.
- Optional `SYSTEMCONFIG_SCREENSHOT_DIR` writes local QA screenshots; screenshot animations
  are disabled to avoid capturing a faded-out dialog under the fixture's paused clock.
- Full frontend run: 233 passed / 2 failed. Existing, unchanged connectivity tests fail on
  the StrictMode shared-socket count (6 versus 1) and disconnect/retry socket-count timeout.
  The first failure reproduces independently; no SystemConfig component participates in it.
- Typecheck and production build pass. Lint exactly matches the prior 41 findings
  (36 errors, 5 warnings). No live hardware/database/maintenance testing was performed;
  backend tests were not rerun for this frontend-only change. See [[Frontend]].
