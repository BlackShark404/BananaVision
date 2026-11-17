# Development Decisions

Documented architectural, technical, and operational decisions in BananaVision.

## 2026-11-17: Complete audit logging through one writer

- **Request:** "Make sure also the audit logs properly logs all CRUD operations and other
  things. Do what must be done and best practice."
- **Before:** 25 inline `ActivityLog(...)` writes, no helper.
  - **Lost on rollback:** the failed sign-in that caused a lockout.
  - **Not logged at all:** backups, backup downloads, restores, recovery, exports, refused
    access, failed re-authentication, failed current-password/PIN checks, inactive and
    temporary-credential sign-ins, power cancel and outcomes, printing, retention and
    startup.
  - **Lumped together:** seven credential events were `user_updated`, and kiosk PIN
    sign-in was `login`.
- **Decisions:**
  1. One writer, `backend/app/services/audit.py`, with a fixed vocabulary (`AuditAction`).
     Existing names stay for unchanged events; old rows are not rewritten.
  2. Record changes use `record()` in the same transaction (fail closed). Failures,
     denials and exports use `emit()` or `attach()`. These write after the rollback and
     never turn a 401/403/429 into a 500.
  3. Data that leaves the station (backup download, scan-log export) is not served
     without its audit row (503). It is refused while the station is in recovery or
     maintenance, and written at once while a restart or shutdown is pending. (Review
     finding: it was only held in memory, so a reboot could lose it.)
  4. Refused access (403) is logged centrally, throttled per actor, route and reason.
     401s from expired tabs are not stored. (User decision: "Yes, throttled".)
  5. Change-password, change-PIN and maintenance re-authentication get the same rate
     limit as sign-in.
  6. Maintenance control paths never write into their request session. Non-owners defer
     while the station is not ready; the restore owner writes its outcome in `_finish`
     after `verify_live`, exactly once.
- **Not logged (noise):** ordinary GET reads, notification read receipts, automatic label
  printing, device online/offline changes.
- **Not visible to the server:** exports made in the browser (Activity Log, Quality
  Control and Delivery Intake CSV/XLSX).
- See [[Database]] (Activity log) for the vocabulary and details grammar.

## 2026-11-17: Admins can correct a Sold or Spoiled scan; restoring stock reopens its intake

- **Problem (station report):** Scan Detail showed no status control for a Spoiled scan, so
  an admin who chose Spoiled by mistake (instead of For Processing or Sold) could not fix it
  there. The lock was frontend-only: `VALID_TRANSITIONS` in `ScanDetail.tsx` gave Sold and
  Spoiled no targets and never offered In Stock. The backend never enforced it, and the
  Scan Logs row menu already allowed any change.
- **User decisions:**
  1. Scan Detail offers an admin every status except the current one, the same rule as the
     Scan Logs row menu. A reason is still required and each change is in Scan History.
  2. A single-scan change back to **In Stock** reopens a **Depleted** delivery intake
     (Active). Stock only counts in an Active intake (`inventory_policy.eligible_stock` and
     `inventory_facts`), so without this the restored scan stayed out of Inventory, at-risk,
     dashboard expiring and analytics. Single changes to Sold or Spoiled still do not
     deplete an intake.
  3. Single scans only. Delivery Intake "Mark all …" and the bulk API's skip of Sold and
     Spoiled scans are unchanged, so a bulk action never overwrites a recorded outcome.
- **Operators:** they may still change status on their own scans through the API (no UI).
  Leaving Sold or Spoiled, and any change that would reopen a Depleted intake, now return
  403. This mirrors the rule that only an admin removes a flag; intake status is otherwise
  admin-only.
- **Implementation:** `mutate_scan` in `backend/app/services/scan_records.py`. The reopen
  decision reads `scan.intake` after the existing parent-first intake lock (the scan reload
  with `populate_existing` re-reads it), so no lock is added and the lock order stays the
  same as bulk inventory and scan attachment. The reopen writes `intake_status_changed` to
  the activity log, sets the intake's `updated_at` to the status change time, and after
  commit publishes `intake:changed` with kind `scan-status` (same payload as bulk). A replayed
  request returns its receipt and changes nothing.
- **Dialog wording:** `inventoryStatusChangeNote` (`frontend/src/lib/inventoryStatusChange.ts`)
  replaces "This is a terminal status and cannot be easily undone" on Scan Detail and is also
  used by the Scan Logs dialog. The Delivery Intake bulk dialog keeps its terminal warning,
  which is still true for bulk.
- **Kiosk resume (review finding, user decision "Resume today only"):** this change adds the
  first page action that reopens a Depleted intake (Delivery Intake never offers "Mark all
  In Stock"). The kiosk used to resume the newest Active intake on load, so a reopened older
  intake could have captured today's scans. `InventoryContext.loadData` now resumes only an
  Active intake whose `intake_date` is today in Asia/Manila (`isManilaToday`). An intake
  already open in the kiosk stays open across midnight; after a reload or operator swap the
  operator picks the source again.

## 2026-11-16: Review queue is the flagged scans; Scan Logs opens on today

- **Revised 2026-11-17 (user request after testing on the station laptop):** Scan Logs
  opens on **All dates**, not today. The sidebar Logs button showed an empty table whenever
  nothing had been scanned that day. A plain `/logs`, the sidebar, **Reset** and the Total
  Scans card now all show every date. The today redirect and the midnight roll are removed.
  A single day is still one pick away in the date box, and the Dashboard "Scans Today" card
  still opens `?date=<day>`. The review chip and the Expiring-stock chip are unchanged.

- **User request:** the Dashboard "Pending quality reviews" link should select **Flagged** in the
  Scan Logs Status menu, not leave it on "All Statuses". Today's date should be the Scan Logs
  default. The user asked for the situation to be analysed first.
- **Analysis:**
  - The old review rule was `flagged OR confidence < threshold`, all-time.
  - New low-confidence scans are already flagged when saved: `fusion_engine.py` sets
    `auto_flagged` when the final confidence is below the same SystemConfig threshold. So the
    only unflagged members were scans whose flag a person removed after checking them, or old
    scans after the threshold was raised. Those could never leave the queue.
  - The Dashboard alert counts (pending reviews, expiring stock) are all-time backlogs. A
    today-only date on those lists would hide most of them (all 15 expiring scans on the
    station were from 21 October).
- **User decisions:**
  1. **Review = flagged.** `dashboard._review` is `flagged = true`, used by the Dashboard
     count, the `/dashboard/scans` review view and Scan Logs `attention=review` with its
     counts. The queue is reached with **Status: Flagged** (`/logs?status=Flagged`), and
     **Remove Flag** takes a scan out of it.
     - `_successful` is "not flagged, with a recorded confidence": unknown confidence is still
       never auto-approved.
     - The legacy `attention=review` link becomes `status=Flagged` in the browser, unless
       another status is already selected.
     - This supersedes "Review Queue Scope" (2026-10-16 §3) and the "Dashboard Review Link
       Predicate Truncation" fix, which were written for the old rule.
  2. **Today for plain Scan Logs only.**
     - A plain `/logs` (the sidebar; only paging or sorting) is replaced before the first
       request with `?date=<today in Asia/Manila>`.
     - Any filter link (the Dashboard chips, Inventory, intakes, sources) keeps all dates, and
       the date box reads **All dates**.
     - `date=all` means all dates explicitly. Clearing the date sets it, and removing the last
       filter keeps it, so a backlog view never jumps to today.
     - **Reset** and the Total Scans card go to the default view: today, no filters.
     - Dashboard "View All Logs" and Recent Scans rows open `?date=all`.
     - An explicit date in the URL does not roll over at midnight.
- **Follow-ups from the independent review (same day):**
  - Only an admin may remove a flag: `PATCH /scans/{id}/flag` with `flagged=false` returns 403
    for operators, who can still raise flags (Kiosk "Flag for Review").
  - Quality Control (badges and CSV/XLSX Status) and Scan Detail no longer call an unflagged
    low-confidence scan "Review" or "Needs Review". They show a neutral **Low confidence**,
    and Scan Detail keeps "Needs Review" for a camera cultivar conflict.
  - The at-risk subset of a browse snapshot counts review as flagged.
  - The sidebar Logs link goes straight to `?date=<today>`, so an open default view is not
    reloaded.
  - An open default view moves to the new day at Manila midnight; a chosen day or a
    filtered view does not.
- **Not changed:**
  - The Expiring-stock rule and all count definitions other than review and success.
  - The backend default (no `business_date` = all history) and the API fields.
  - Scans already stored: no migration. An old unflagged low-confidence scan now counts as
    checked. Flag it again if it still needs review.
- **Tests:** `backend/tests/test_dashboard.py`, `test_scan_logs.py`;
  `frontend/tests/scanlogfilters.test.mjs`, `dashboard.test.mjs`, `scanrecords.test.mjs`.

## 2026-11-16: Horizontal radial wings in `_count_top_second_tier`, side/Rear collapse recovery, and bottom-left Top trim scoping

- **Orientation check in `_count_top_second_tier` (`fusion_engine.py`):** Kept `d.w <= d.h` on `< TOP_OVERLAP_CONFIDENCE` (`0.50`) Top detections rather than adding an area cutoff (`< 0.70 * med_area`), preserving the synthetic equal-area overlap test (`test_two_tier_hand_fusion_reconstructs_occluded_lower_tier_fingers`) while keeping splayed radial upper wings (`w > h`) in `u_primary`.
- **Two-tier recovery bounds (`fusion_engine.py`):** Added single-side collapse recovery (`min(l_cnt, r_cnt) <= 4`) and partial-Rear collapse recovery (`re_cnt < 8 or re_cnt < max(l_cnt, r_cnt)`) instead of lowering `OCCLUDED_FINGER_MIN_PRIMARY` below `4` (`minp2` regressed `v13/valid` `effab854` `3 -> 4`).
- **Compact `Rear` vs `11`-Rear separation (`fusion_engine.py`):** Capped compact-Rear single lower-tier substitution (`re_lower > max(l_lower, r_lower)` with `top_second_tier == 0`) at `re_cnt <= 10 and re_cnt <= t_cnt`, so `9–10`-Rear hands recover `14` while `11`-Rear `15`-finger hands (`10-lakatan-unripe`, `01-latundan-unripe`) remain on the median lower tier.
- **Bottom-left platform scope (`classification.py`):** Scoped `_is_top_platform_edge_box` `at_bottom` check to `x1 <= 0.15 * iw and cx <= 0.50 * iw` so bottom-right smooth ripe yellow peel boxes are never misclassified as tan tray trim.

## 2026-11-15: Trim-overhang sibling suppression, horizontal-parent sub-box dedup, and Pass-3 / fusion bounds

- **Sub-box dedup symmetry across backend and frontend (`classification.py`, `detectionBoxes.ts`):** Extended `_is_axially_aligned_or_enclosed` (and TS `deduplicateDisplayBoxes`) to suppress vertically centered portrait/square fragments (`0.50 <= h/H < 0.80`) inside elongated horizontal parents (`w >= 1.6 * h`, `w >= 2.0 * sub_w`), rather than lowering generic IoU thresholds or merging off-axis stacked fingers.
- **Sibling-relative Top trim overhang suppression instead of spatial platform masking (`classification.py`):** `_suppress_trim_overhang_duplicates` drops bottom-left `Top` boxes only when their outer left/bottom overhangs (`>= 18%` box area) match pale-tan tray trim / dark gap pixels (`>= 72%`) AND the trimmed interior overlaps a clean horizontal sibling (`>= 72%`). Single genuine bottom-left fingers touching trim with no inner duplicate sibling remain intact.
- **Calibrated Pass-3 recovery bounds (`classification.py`):** Set `OCCLUDED_FINGER_MIN_PRIMARY = 4` so 4-box Cardaba Rear captures invoke recovery; admitted `>= 0.50` Pass-3 tips down to `0.10 * median_area` while keeping `0.22 * median_area` for `< 0.50` boxes; allowed `0.75 * med_w` lateral span for horizontal side views (`not upright`) while blocking low-conf `>= 2`-stage ripeness outliers and `within_hand` upper-margin peripheral grazing.
- **Fusion 12-Rear guard (`fusion_engine.py`):** Required `re_cnt >= 12` before lower-tier flank summation or `wide_bilateral` reconstruction so 11-Rear captures cannot inflate to `22`.

## 2026-11-14: Colour check for crown and background boxes

- **User request:** 16 station screenshots (newest code) still showed non-finger boxes: the
  crown (cut stalk end) in Top views ("Lakatan Unripe 68 %", "76 %") and a dark curtain in a
  Left view ("Cardaba Unripe 61 %"). These come from the main pass, carry the hand's own
  label and sit inside the banana evidence, so no geometric or ripeness rule could tell them
  apart. A crown box in Top raised a stored count by one (e.g. 14 instead of 13).
- **User decision:** add a colour check now (drop and flag, switchable), retrain with
  station photos later.
- **Design:** judge a box on its own pixels before the OOD gate (gate contract unchanged):
  share of dark or bluish/violet pixels in the box centre; drop at >= 0.55; Overripe exempt;
  scan flagged with an activity note. Thresholds measured on the screenshots ([[AI Models]]);
  the dark cut is value < 40, not 60, because shaded fingers under the hand reach ~45-55
  (found by the independent review). A box the pass would drop anyway as a fragment or
  repeat is skipped without counting, so it cannot flag a scan.
- **Rejected:** a "peel fraction" minimum (pale overexposed Cardaba fingers scored as low as
  the crowns); position rules for the crown (fitted to two examples, would drop real fingers).
- **Next:** `backend/scripts/export_station_training_set.py` turns an admin backup into a
  draft training set (station photos, stored boxes as draft labels) so the model can learn
  crowns and backgrounds properly.

## 2026-11-13: Finger-count accuracy without new training data

- **User request:** make the YOLO26 finger count more accurate, and stop non-banana
  objects being counted (two station screenshots: brown wood boxed "Cardaba Ripe 64 %"
  beside an unripe hand; a window frame (29 %) and the wooden plate (26 %) boxed on the
  Left camera). The user is phone-only, so no laptop, Colab, weights or dataset were
  reachable; work was limited to code verifiable here plus tooling for later.
- **Decisions:**
  - Pin the YOLO26 head explicitly (`YOLO_INFERENCE_HEAD=one_to_many_nms`): the pinned
    Ultralytics 8.4.40 otherwise runs the NMS-free head on files that do not store the
    choice, which silently disables every IoU calibration. See [[AI Models]].
  - Fix undercounts that contradict documented intent: the rotated-pass "same column"
    rule now follows the finger's long axis; a whole-hand box gives way to the
    side-by-side fingers it hid.
  - Non-banana boxes: a ripeness-outlier rule (one hand ripens together), and the
    low-threshold second pass only admits boxes within the hand and filters the platter
    lip on every side camera. Both screenshots' false boxes came from rules that are now
    covered; the wood box is only caught if it is not the most confident box or does not
    touch the hand.
  - Every rule has a setting that restores the earlier behaviour; the adjacent-ripeness
    second pass stays off (measurement only).
- **Rejected again (see earlier entries):** summing views, fixed bonuses, a stricter gate
  overlap rule, an HSV peel-colour check (no data; brown wood resembles overripe peel), a
  Top background filter (no position prior overhead), "train longer".
- **Still needed:** station weights + dataset + background photos (as a GitHub release)
  to measure every change with `scripts/evaluate_finger_count.py` and retrain with
  negatives (`scripts/train_finger_model.py`).

## 2026-11-13: The QR page shows only the scanned data

- **User request:** a phone that scans a BananaVision QR code sees only the scanned banana
  data in a clean, read-only page: no "Log in", "Sign in", website or navigation buttons,
  and no redirect to the login page.
- **User decisions on 2026-11-13:** (1) every QR scan shows the data-only page, signed in
  or not; the redirect of signed-in viewers to the staff Scan Detail page was removed.
  (2) The public API stops sending photo references: `GET /api/v1/scans/{id}/track`
  always returns `images: []`. The field stays in `PublicScanResponse`, so the response
  shape does not change; staff endpoints still return images.
- **Why the API change:** anyone with the link could read internal capture paths and
  camera IDs. The page had already stopped showing photos, and `/captures` needs a staff
  session.
- **Provider boundary (found in review):** `/track/:scanId` is mounted outside the staff
  data providers in `App.tsx`. Inside them, a phone holding an old staff session loaded
  staff data on the QR page and was sent to `/login` when the token had expired or been
  revoked. Removing the in-page redirect alone did not stop that.
- **Public page hierarchy (2026-11-13 follow-up):** the first screen keeps ripeness,
  cultivar, the shelf-life countdown, the scan date and the review notice. Confidence,
  `Est. Fingers`, sensor readings, source, treatment and the scan ID are collapsed under
  "Scan details"; `inventory_status` is staff-only and no longer renders publicly. The API
  response shape is unchanged.
- **Kept:** the error screen's "Retry" button (it only reloads the same data), the
  `/track/:scanId` route and URL, printed label formats, and the landing and login pages.
- **Capstone storyboard:** Figure 92's text in
  `docs/bananavision-docs/docs/STORYBOARD_CAPSTONE1.md` was updated on the user's
  instruction; its screenshot still shows the old page and needs a new capture.

## 2026-11-13: AI-estimated numbers say "Est."

- **User request:** label finger counts and other AI-estimated numbers "Est." everywhere so nobody reads a computer-vision estimate as an exact measurement. Raw values, API fields, database types, sorting, filters and thresholds stay numeric.
- **User decisions on 2026-11-13:** (1) one term on every page: labels `Est. Fingers`, values `Est. 13 fingers`; tooltips keep the full word "Estimated". This supersedes the `Estimated Fingers` wording in the Cardaba entry below. (2) A count a person corrected is not an estimate: it reads `Fingers` / `13 fingers`, and the correction inputs are labelled `Fingers`. (3) Numbers only: finger counts and shelf-life estimates; cultivar, ripeness and confidence keep their labels. (4) Exports, the scan-completed notification and new activity entries use the same wording; cells stay plain numbers.
- **When a count is corrected:** `is_overridden` is scan-level (set when any of cultivar, ripeness, finger count or spoilage changes), so the rule is per field: corrected only when the scan is overridden, an AI baseline (`original_ai_result`) exists and the current count differs from it. Scan Logs rows and the public QR response carry no baseline, so those pages always say "Est.".
- **Spoilage stays an estimate** even after a correction: its edit field is read-only and is recomputed from cultivar and ripeness.
- **Live updates keep the baseline.** `scan:changed` events omit `original_ai_result`, so `ScanContext` keeps the one it already read; otherwise a corrected count turned back into an estimate on other open screens (found in review).
- **One implementation:** `frontend/src/lib/estimates.ts` (`fingersLabel`, `fingerCountText`, `fingerCountIsEstimate`, `estimateText`) and `estimated_fingers` in `backend/app/services/scan_service.py`.

## 2026-11-13: Asia/Manila for every timezone-related behaviour

- **User rule:** "Always make sure the system uses Asia/Manila timezone in all timezone related functionalities."
- **State found.** Business data already followed it: `backend/app/core/time.py`, `ManilaDateTime` columns (every timestamp loads as +08:00), the PostgreSQL session zone, analytics grouping and dashboard business days. What did not: 21 frontend places that used the browser's zone or the UTC date (Kiosk header clock, Scan Detail footer and notes, QC list, Profile activity, user/supplier/device dates, backup expiry, the printed QR tag date, export file names, the date picker's "today", the footer year), backend log timestamps, and the zip member times inside XLSX exports and the backup manifest.
- **Decision.** One frontend helper, `frontend/src/lib/manilaTime.ts`, next to the backend's `app/core/time.py`. Call sites keep their locale and format and only gain the zone, so nothing looks different. Log lines use a Manila clock and end in `+08:00`; zip members are stamped from `now_manila()`.
- **Guards.** `frontend/tests/manilaTime.test.mjs` and `backend/tests/test_manila_time_guard.py` scan the sources and fail on any new clock read outside the two helpers; browser tests run in Los Angeles and New York browsers; backend tests run with the process clock in Los Angeles.
- **Not changed:** stored data and API contracts (already correct); `YYYY-MM-DD` values sent to the API (already Manila business days); the profile's "last 7 days" (a rolling 168-hour window that does not depend on a zone).

## 2026-11-13: Public HTTPS access uses one origin behind Tailscale Funnel and Caddy

- **Topology.** `Internet -> Tailscale Funnel (TLS on 443) -> Caddy 127.0.0.1:8080 -> uvicorn 127.0.0.1:8000`. Caddy serves the built `frontend/dist`, forwards `/api`, `/captures` and `/health`, and adds HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and hides `Server`. Funnel exposes one HTTPS port and no LAN listener, so no router port forwarding is involved.
- **Same origin is the contract.** An HTTPS page calls its own origin for HTTP and WebSocket traffic. This avoids mixed content, makes CORS irrelevant in production and keeps one URL for the SPA, API, evidence images and socket. Plain-HTTP station pages keep the existing `http://<host>:8000` backend. `VITE_API_URL` and `VITE_WS_URL` remain explicit overrides.
- **Camera previews now require a session.** Live feeds were unauthenticated. Since users asked for login-only access, `<img>` previews pass the session as `?token=` (media elements cannot set headers), while the backend accepts a bearer header or query token through `get_media_user`. Evidence images under `/captures` remain bearer-only and are fetched as blobs; public QR tracking no longer shows camera images.
- **Production fails closed on weak secrets.** With `APP_ENV=production`, `APP_SECRET_KEY` and `JWT_SECRET_KEY` must each be unique values of at least 32 UTF-8 bytes and must not contain the shipped placeholder markers, otherwise the app refuses to start. `/docs`, `/redoc` and `/openapi.json` are disabled in production and Caddy also returns 404 for them.
- **CORS stays LAN-compatible.** The built-in default is `http://localhost:5173` and `http://127.0.0.1:5173`; the shipped example keeps `["*"]` because plain-HTTP LAN and Tailscale pages call the station hostname. Production traffic is same-origin and uses no CORS entry, and port `8000` is never exposed publicly.
- **Printed labels need a public base.** `VITE_PUBLIC_BASE_URL` sets the origin embedded in QR codes so labels resolve off-station. Without it, labels keep the kiosk origin and only work on the station network.
- **Socket keepalive.** Tailscale Funnel drops idle WebSockets, so the client sends a `ping` event every 25 seconds. If Funnel still breaks long-lived sockets, the documented fallback is a Cloudflare Tunnel; the chosen setup keeps Caddy, so the fallback changes only the outer tunnel.
- **Not performed here:** installing Caddy or Tailscale, enabling Funnel, rebuilding `frontend/dist`, or changing a live station. Those steps remain in [remote-access.md](../remote-access.md) and need explicit authorization.

## 2026-11-13: Shelf-life countdown counts Asia/Manila calendar days; nothing is rewritten

- **Problem.** An estimate stored as `1-3` still read "1–3 days" a week later. The stored string was shown as it was written on Kiosk recent scans, Quality Control and the Scan Logs main cell. The existing countdown was one number (range midpoint minus elapsed seconds), so it was not a range and did not follow calendar days.
- **Rule.** `elapsed_days` is the Manila calendar date of now minus the Manila calendar date of `scan.date_time`, never below zero. The remaining bounds are the whole-day bounds of the stored estimate minus `elapsed_days`, never below zero. The state is `final_day` when the elapsed days equal the upper bound and `expired` when they exceed it. One implementation: `shelf_life_window` in `backend/app/services/inventory_policy.py`, using the existing `as_manila` helper. No second timezone path was added.
- **Storage stays immutable.** `scan_classification.spoilage_days` and `scan.date_time` are never written by a read, and no job rewrites them. The window is derived on every read, so there is no migration and old records work as they are.
- **Whole-day bounds match the display.** A decimal estimate such as `4.86` is shown as `4–5 days`, so its window starts as 4 to 5. A known zero stays zero and a positive value below one day counts as one day, the same rule as `frontend/src/lib/spoilageDisplay.ts`. Day 0 of the countdown therefore equals the estimate the user saw at the scan. A value that page shows as "Unknown" (a number without a leading digit such as `.5`, or above `Number.MAX_SAFE_INTEGER`) has no window, so a countdown never sits beside an unknown estimate (audit fix, 2026-11-13). The reverse stays: the page can display an en dash `1–3` that the stored-value parser does not read; such a record shows its estimate without a countdown.
- **The risk number did not change.** `remaining_days`, `risk_as_of`, the two-day at-risk rule and all SQL keep their meaning, because sorting, snapshot membership, counts and exports depend on them and tests pin Python and SQL parity. The window is a separate optional object. The two can differ near the end of a range; that is documented in [[Frontend]].
- **Server time is authoritative.** The server computes the window from its own clock and sends the scan's Manila date and its own Manila date (`scan_date`, `as_of_date`). The page counts from the scan date to the later of the server's date and its own Manila date, so a wrong browser clock can change that browser's display and nothing else, and a scan dated after the server's date stays at zero. No request parameter influences the result.
- **Frozen list snapshots do not store the window.** It is derived, so `save_snapshot` drops it before the size check and `slice_snapshot` rebuilds it for the instant the row was frozen (the row's `risk_as_of`, or the snapshot's `generated_at`). A snapshot therefore reads the same at any later time, the 20 MiB limit holds as many rows as before, and snapshots saved before this change get a window too.
- **Rejected:** a background job that rewrites the stored value (destroys the audit value); a SQL-side calendar expression (needs a second timezone path and SQLite shims); parsing the stored string in the browser (rejected before, see the 2026-10-10 audit); changing what `remaining_days` means.
- **User decisions on 2026-11-13:** Scan Logs leads with the countdown and shows the estimate beneath, replacing the earlier estimate-first cell; Sold, Spoiled and For Processing records keep the scan-time estimate on staff pages (the public QR page counts down for every status, as it did before); wording is `N days left`, `Final day`, `Overdue`.
- **Revised 2026-11-17 (user request after station testing):** older Sold rows showed a bare `8–9 days`, which read like a countdown and did not match the In Stock rows. Scan Logs, Scan Detail and the Quality Control dialog now show `Sold · no countdown` (or `Spoiled` / `For processing`) on the top line and `Est. 8–9 days from scan` beneath. The value is still the stored scan-time estimate; no countdown is computed for stock that left inventory, and nothing is rewritten. The public QR page and the Kiosk Recent Scans list are unchanged.

## 2026-11-13: Out-of-distribution rejection uses an independent banana verifier

- The cultivar detector is closed-set, and its weights and dataset are not in the repository, so the rejection mechanism had to work without retraining. The COCO pre-detector became a banana-vs-OOD verifier: a scan needs banana evidence, and a cultivar box is trusted only where that evidence covers it. Details and measurements are in [[AI Models]].
- A cultivar box without banana evidence is treated as if the model had never emitted it. It is skipped in the first pass, the rotated Top pass and the occluded-finger recovery pass before any rule that compares it with other boxes (only filters that judge a box on its own run first: position, and in the recovery pass also size and label), so the gate's result is exactly what the classifier reports for the remaining boxes, and the classifier's own rules are not modified. Two richer variants were tried and withdrawn after review: filtering after the suppression rules let an unsupported box swallow real fingers, and showing the set-aside boxes to the cluster rule let two of them remove the only supported box of a real banana view. The plain contract is pinned by tests on 300 random frames.
- Every scan the gate altered is flagged; there is no silent change. In the first pass and the recovery pass a skipped box counts unless that pass would have dropped it anyway as a repeat of an accepted detection. In the rotated Top pass every skipped box counts: a repeat there still feeds the orientation decision, the sub-box filter and the label-conflict check, so an exemption let the Top cultivar change unflagged (found by a randomized check, about 146,000 cases). The price is that a Top scan can be flagged for a skipped box that changed nothing.
- The gate may not change an accepted scan silently. Any dropped box flags the saved scan for review, and a rejected scan writes a `scan_rejected` activity row with per-view banana scores, because its captures are removed like any failed scan.
- The verifier fails closed (HTTP 503). `OOD_GATE_FAIL_OPEN=true` and `OOD_BOX_SUPPORT_FILTER=false` are the documented ways back to the earlier behaviour.
- Rejected alternatives, both measured on the calibration pool: a veto when another COCO class overlaps the banana box with higher confidence (no gain), and box-overlap support rules instead of the centre rule (no better trade-off). A tighter acceptance threshold was not adopted because green and peeled bananas already score low.
- Open-source data stays out of Git. A pinned manifest of Open Images V7 image IDs defines three disjoint pools, and thresholds were chosen on the calibration pool only. Training negatives that the verifier scores highly must be inspected by eye: one contained an unlabeled banana bunch and is excluded by ID.
- Open risk accepted for now: thresholds come from open-source photos. Recall for the three cultivars, especially unripe fruit, must be checked with `evaluate_ood_gate.py pipeline` on the station's own weights before the gate is relied on. That run uses dataset photos with their camera view; it is still not a live station measurement.
- Partly checked on 2026-11-13 on a team laptop: on 416 labeled test photos the gate kept a cultivar on 408, against 409 for the earlier gate, with no wrong cultivar and the extra loss in the Rear view only (see [[AI Models]]). No threshold was changed. Still open: neither checkpoint used was Top-calibrated, so the Top refinement, rotated pass and finger recovery were not exercised.
## 2026-11-13: Cardaba Canonical Orientation, Radial Flank Deduplication, and Multi-Tier Finger Estimation

- **UI clarity (`Estimated Fingers`):** Replaced `"Est. Fingers"` with `"Estimated Fingers"` across `Kiosk.tsx`, `Logs.tsx`, `QualityControl.tsx`, and `kiosk.test.mjs` so operators immediately understand the metric is an estimate. (Superseded on 2026-11-13: the user chose `Est. Fingers` everywhere; see "AI-estimated numbers say Est." above.)
- **Active V2 checkpoint calibration (`TOP_CALIBRATED_CHECKPOINTS`):** Registered `banana_yolovn26V2.pt` (`dc171845fe353a2147f6c9219b27fa66df88902eb566eb141670cf4ee5d2b204`, `imgsz=640`) and `banana_yolovsV2.pt` (`9e21668e272bae8ea387d836bbc2b087b5fbb3ae90d375353f49105681e2f478`, `imgsz=640`) so the station's configured V2 models activate Top overlap refinement (`iou=0.65`) and 180-degree rotation fallback.
- **Canonical 180-degree orientation selection for Top view:** Because all Roboflow Top-view training images have the crown at the top of the frame, placing a Cardaba (or Latundan) hand with the crown at the bottom of the Top camera frame inverted the longitudinal morphology and caused Pass 1 (`0°`) to misclassify Cardaba as Lakatan (`82.7%`). When Pass 2 (`180°` rotated) produces an unconflicted cultivar consensus (`>= 3` fingers, `>= 60%` weight share) with strictly higher peak confidence than Pass 1, `BananaClassifier.predict` promotes Pass 2 as the canonical primary orientation and merges non-duplicate Pass 1 flank boxes under the canonical cultivar.
- **Axial sub-box deduplication and TTA occluded flank recovery:** `_is_same_class_sub_box`, `_unique_box_detections`, and `_is_duplicate_detection` now require longitudinal axis alignment (`_is_axially_aligned_or_enclosed`) before suppressing contained boxes, and `_is_cluster_box` requires `det_area >= 1.6 * median(other_areas)`. For calibrated multi-finger bunches (`>= 5` primary fingers), a guarded TTA recovery pass (`augment=True, conf=0.25, iou=0.70` with `_is_recovery_duplicate`) recovers partially occluded flank/second-tier fingers matching the primary `(cultivar, ripeness)` without diluting primary confidence votes.
- **Multi-finger Top anchor and genuine max-view finger count in `FusionEngine`:** When `top_camera_result` has `finger_count >= 4` and higher confidence than a competing peripheral cultivar's mean confidence, the overhead Top anchor prevails over foreshortened peripheral tips without flagging a false `cultivar_conflict`. `FusionEngine.fuse` uses `max(finger_counts, default=0)` directly from actual camera bounding-box detections rather than an additive cross-camera offset, preventing artificial clamping to a fixed count (such as `14`).

## 2026-10-28: Workflow diagrams use icon + caption nodes with no shapes

- All four workflow figures (`workflow_kiosk`, `workflow_operator`, `workflow_admin`, `workflow_iot`) draw each step as a free-standing emoji icon plus caption instead of an ellipse or rectangle. Shape fills and outlines were removed because filled nodes shrink the text available at the fixed 16 cm insertion width; the icons and stand-alone arrows follow the reference capstone layout.
- A node is one text cell: a 30 px emoji line, an 18 px bold title, then 14 px metadata (route path, role qualifier, login credential). Nothing else was added, so existing wording and topology are unchanged.
- Subsystem colour coding moved from the shape stroke to the caption text: the previous `strokeColor` becomes `fontColor` (red admin, blue kiosk UI, green pipeline, amber intake, indigo shared views, orange decision). Emoji keep their native colours.
- Zone containers stay as dashed rectangles but are `fillColor=none`, and their headings sit above the box rather than inside it, so a caption is never mistaken for a container.
- Node boxes are still fitted from Chrome-measured text (longest line + 6 px, sum of 1.2 x line height + 2 px), so no caption wraps at any zoom. Current page sizes: kiosk 923x619, operator 925x487, admin 1071x532, iot 1132x486. At a 16 cm insertion width the 18 px caption renders at 8.8 / 8.8 / 7.6 / 7.2 pt.
- The IoT figure is laid out as two rows, not three stacked bands: row 1 carries the trigger (operator, Mini PC), the hardware zone and the persistence zone; row 2 carries the edge AI pipeline. The pipeline therefore reads left to right (Banana Present? -> YOLO26 -> Fusion -> Spoilage Model) instead of right to left, which places Spoilage Model directly under the persistence zone. That removed about half the page height (784 -> 486 px) at the cost of extra width, because a three-band stack is inherently ~200 px per zone.
- Draw.io's SVG/PNG siblings in `docs/bananavision-docs/docs/workflows/` are hand-exported, so they stay out of date until the `.drawio` files are re-exported from the desktop app.

## 2026-10-28: Workflow diagram typography for embedded documentation

- The four draw.io figures (`workflow_admin`, `workflow_operator`, `workflow_kiosk`, `workflow_iot`) use 18 px bold titles, 14 px secondary lines (route, role, credentials) and 14 px edge labels. Figures are inserted at a fixed width, so these are the values that keep the labels readable at document scale.
- Nodes carry an icon, a title and structural metadata only (route path, role qualifier, login credentials). Capability descriptions were removed because node width is driven by the longest line and the prose already exists in `WORKFLOW_DOCUMENTATION.md`.
- Node sizes are fitted from real rendered text widths; shapes are sized so every label line stays unwrapped. Edge exit/entry points are pinned (`exitX/exitY`, `entryX/entryY`) alongside waypoints so the orthogonal router keeps the planned corridors.
- Page size is trimmed to the drawing plus a 20 px margin, since extra whitespace shrinks the labels when the figure is scaled to the page width.

## 2026-10-24: Notification integration and socket ownership

- Keep revision 0010's per-user receipts and existing private/broadcast visibility. Single and read-all operations insert visible receipts using ordered `INSERT ... SELECT ... ON CONFLICT DO NOTHING`, so concurrent requests retain one receipt and its original `read_at` without a check/insert race.
- Scan completion invalidates notifications after scan-ID deduplication for both WebSocket and HTTP delivery. Expired Logs snapshots also discard cached risk membership before fetching the replacement snapshot.
- Each WebSocket hook owns its connection. Cleanup/reconnect invalidates ownership before closing; late open/message callbacks from the previous socket cannot update the current session. The existing authenticated query-token protocol is unchanged.
- Incoming archive v4 remains the approved pre-release format: v4 archives created before revision 0010 must be recreated. Migration/archive tests use disposable databases; no station migration or restore was performed.

## 2026-10-23: Live-data synchronization and stock eligibility

- Scan Logs keeps its immutable browse snapshot for pagination and export consistency. New scan completions and accepted status/flag corrections invalidate the snapshot and trigger a debounced refresh; an expired or superseded `409`/`410` snapshot is retried once without the snapshot instead of surfacing a failed poll. No continuous full-snapshot polling was added.
- `ScanProvider` remains the source of truth for scan records on the client. A completed scan can arrive from both the Kiosk and dashboard WebSocket rooms plus the HTTP response, so completions are deduplicated by scan ID while allowing later HTTP `print_job`/`print_error` fields to merge into the stored record.
- Inventory stock, cultivar and ripeness links now pass the selected source, `In Stock` status and `stock=eligible` to Scan Logs. Intake-linked spoilage rows retain their full intake scope. The backend applies the existing `eligible_stock` predicate through a new `stock_eligible` query flag so stock-link totals match the Inventory counts without duplicating stock policy in the UI.
- A Kiosk reload restores the newest active intake from the server rather than creating another intake. The backend also rejects new scans against a Depleted intake under the existing row lock, and bulk intake updates derive `Active`/`Depleted` from the resulting scan states instead of the requested bulk status.
- Notification single-read requires the notification to belong to the caller or be a broadcast. Integration with revision 0010 retains the incoming per-user read receipts; broadcast read state is now isolated by account.
- Authentication no longer eager-loads an operator's entire scan graph or an account's activity history. Those relationships are `lazy="raise"`; endpoints that need scans must load them explicitly.
- No QR label format, sensor-staleness behavior, camera-apply ordering or Asia/Manila date-boundary behavior was changed. The configuration save-before-camera-apply behavior remains a known product decision.

## 2026-10-22: Per-User Notification Read Receipts

- Chose a normalized read-receipt table over application-level fan-out. `app_notification` stores notification content once; `app_notification_read` stores one `(notification_id, user_id)` row with `read_at` per account that has read it.
- A nullable `app_notification.user_id` is a broadcast visible to every account. `scan_flagged` creates one broadcast row, while `scan_complete` remains private to the scanning operator. The API derives the existing `read` boolean from the current user's receipt, so the frontend contract is unchanged.
- Single mark-read is scoped to a notification the current account can see, and read-all inserts receipts only for that account's visible notifications. Another account's private notification returns 404 and cannot be mutated.
- Migration `0010_notification_read_receipts` creates the receipt table, preserves existing private read flags for their owner and broadcast read flags for active accounts, then drops `app_notification.is_read`. The downgrade is blocked because discarding receipts loses read history.
- Archive format remains v4 because this schema is pre-release. Local v4 archives created before this revision must be recreated; v1/v2/v3 adapters drop the removed shared flag while retaining notification content.
- See [[Resolved Bugs]] and [[Testing and Validation]] for the verified behavior and tests.

## 2026-10-22: Normalized Camera Slots and Derived Counter Removal

- Saved camera configuration now lives on `device.slot_index` and `device.device_index` instead of repeated `system_config.camera_ids` and `system_config.camera_device_ids`. Slot ownership and physical indices are unique, validated ranges; unassigned operational device rows may keep both columns null.
- `system_config` remains the singleton revision/arbitration row for confidence threshold and retention. The API still exposes `camera_ids` as a comma-separated string and `camera_device_ids` as an ordered list, derived from normalized slots, so the frontend contract is unchanged.
- `operator_profile.total_scans` and `flagged_scans` were removed because analytics already derives those totals from scan rows. Existing counts were not authoritative history and are not backfilled.
- Migration `0009_camera_slots` maps the newest valid legacy camera array into slot rows, preserves existing device UUIDs and statuses, and drops the repeated/counter columns. Automatic downgrade is blocked because it would discard operator-chosen mappings.
- Archive format v4 stores the normalized schema. Strict v1/v2/v3 adapters validate the old recorded schema, convert saved camera arrays into slots, remove the dropped fields, and keep the original archive hash authoritative. Restore validation now requires one contiguous 1–4 slot set before accepting a backup.
- See [[Testing and Validation]] for the isolated migration and archive regressions.

## 2026-10-21: Conservative Finger Count Across Overlapping Views

- Confirmed the old peripheral-addition heuristic can turn Top 7 / Left 9 / Right 10 / Rear 13 into 21: Rear supplies 13 and each side adds four presumed unseen fingers. The user reports about 15 physically present; the per-camera counts do not prove which detections are distinct across views.
- `FusionEngine.fuse` now uses the maximum reported count from unique camera IDs, with no peripheral additions. The example returns an **estimated 13**, not a verified physical total. Differing positive camera counts set the existing review flag; empty/missing-camera and classification checks remain in place.
- Removed the unsupported peripheral-count helpers. `multi_camera_finger_fusion` remains accepted for configuration compatibility but cannot enable additive counting. Per-camera detections, classifier behavior, model weights, schemas, corrections, and existing stored scans are unchanged.
- This supersedes the spatial-complementarity count policy below. It fixes artificial inflation, not detector misses or occlusion; physical confirmation is still needed when the actual bunch has more fingers than any view detects. See [[Testing and Validation]] for the isolated regressions.

## 2026-10-17: Detection Box Cropping and Duplicate Suppression Resolution

- In `classification.py`: Pass-1 nested duplicate box suppression was previously miscoded as `_box_containment == 1.0`, which prevented real-world floating-point bounding boxes from being deduplicated. Implemented `_is_same_class_sub_box(det, existing)` to cleanly suppress nested sub-boxes (substantially smaller area ratio <= 0.85 and containment >= 0.80) and near-identical same-class duplicates (IoU >= 0.80), while preserving distinct neighboring fingers of equal size.
- In `_unique_box_detections`: Clustered detections with IoU >= 0.70 or containment >= 0.85 to avoid floating-point coordinate jitter on coincident hypotheses inflating the finger count.
- In `BoundingBoxOverlay.tsx` and `Kiosk.tsx`: Replaced rigid `aspect-[4/3]` with natural image aspect ratio (`aspectRatio: imgNaturalSize.w / imgNaturalSize.h`), preventing 16:9 camera captures from having the ends of banana bunches and edge boxes sliced off. Implemented visual display deduplication `deduplicateDisplayBoxes` to prevent overlapping clashing boxes from rendering over the same finger.

## 2026-10-17: Split Camera Cultivars Require Verification

- User evidence shows the same known Lakatan bunch predicted as Lakatan from Top/Right and Latundan from Left/Rear. Higher wrong-view scores can win weighted fusion; the mean winning score is not cross-view agreement. This is a real unresolved recognition failure, not a cultivar name-map swap.
- Fusion now flags a weighted cultivar candidate that lacks a strict majority of complete, valid, unique-camera summaries, even when its scores dominate. The stored candidate, original confidence and box labels remain intact. Existing weighted conflict thresholds still apply when a camera majority exists.
- The kiosk derives the same support check from existing detection summaries. It displays `Uncertain`, names the opposing camera groups, and withholds the main confidence and cultivar-dependent spoilage estimate. No API enum, persistence schema or layout redesign is involved.
- A cultivar-specific human correction remains visible when established by `originalAiResult.cultivar` or explicit cultivar-change history. The general `isOverridden` flag also covers count/ripeness/spoilage changes and therefore cannot, by itself, resolve cultivar disagreement.
- Prepared validation has 137 images but only three inferred filename groups (one per cultivar), not 137 independently identified bunches. Group identities remain uncertain. Neither earlier dataset agreement nor training mAP establishes accuracy on the station screenshots. Follow the station protocol in [[Testing and Validation]] before claiming a model recognition fix.
- The supplied `v26n_run5_khen27_1024` run contains YOLO26n weights matching local `banana_yolov26.pt` (SHA-256 `96808fa8ed706909237197e8db2510dccabfaeceed85a4d1ab5182cd28c95f7b`); the saved input resolution is 800, despite the folder name. On the same prepared VALID inputs its app count MAE is 0.942 versus the default's 0.934; combined-class recall is 88.50% versus 90.36%, with exact-count images 58 versus 55. Neither model reproduces the station cultivar error against these labels. This comparison does not justify replacement or a station accuracy claim. See [supplied-run evidence](../audits/yolo26n-supplied-run-validation-2026-10-17.json); no training, threshold tuning, frozen TEST inference or weight/config replacement occurred.

## 2026-10-17: Cultivar Disagreement and Counting Integrity

- Identical `(x, y, w, h)` boxes with competing classes count as one finger. Original class boxes, scores and voting evidence remain available for review; raw box totals can therefore exceed the finger estimate. Peripheral count extraction uses the same exact-geometry deduplication. Near-overlapping boxes do not establish physical identity.
- Pass-1 cleanup now suppresses only fully contained same-class fragments after YOLO NMS. The former extra IoU/alignment filter removed distinct adjacent and horizontally stacked fingers, overriding the calibrated Top suppression policy. Rotation geometry filtering remains heuristic; a suppressed candidate with a different parsed cultivar/ripeness now triggers conflict review.
- Rear cannot contribute its peripheral boxes again when its count supplies the anchor. Existing cross-view count estimates above every individual camera's count require review: edge position does not prove that fingers are unseen in the other views. This supersedes the earlier claim below that spatial complementarity establishes a true physical total.
- The kiosk displays `Scan Complete - Review Needed` for backend-flagged results. Confidence remains the mean winning-pair model score, not measured accuracy, camera agreement or probability that the physical count is correct. No cultivar relabeling rule, confidence increase or model replacement was introduced.
- On 137 prepared VALID images, cached identical model calls replayed through the revised classifier reduce visible-count MAE from 1.518 to 0.934, with exact counts on 55/137 images (previously 30). Localization precision/recall is 92.12%/93.83%; exact cultivar/ripeness precision/recall is 88.71%/90.36%. Counts improve on 59 images, worsen on 16 and tie on 62. See [audit evidence](../audits/yolo-scan-integrity-2026-10-17.json).
- All 137 image cultivar votes agree with the prepared labels, so these images do not reproduce the reported Lakatan-to-Latundan error. Uncertain bunch grouping, dataset labels and plain backgrounds limit generalization. The user's new scan still needs original offline four-view images and verified labels/physical total before its classification or 17-finger count can be established. See [[Testing and Validation]] and the [dataset audit](../yolo-dataset-audit-2026-10-16.md).

## 2026-10-17: Calibrated Top-Camera Overlap Filtering

- The existing checkpoint gains a Top-only NMS IoU 0.65 profile at confidence 0.50 and configured baseline IoU 0.45. Across all 31 prepared validation Top photos, count MAE decreases 1.000 to 0.806 and localization recall increases 93.17% to 97.95%, with unmatched predictions unchanged at 21 and both precision metrics improving. Seven photos improve in count error, three worsen, and 21 tie. See [policy evidence](../audits/yolo-top-overlap-validation-2026-10-17.json).
- Scope is matched by actual checkpoint SHA-256 and normalized configured camera label, independently of filenames and camera IDs. `YOLO_TOP_OVERLAP_REFINEMENT=false` disables the profile. Other checkpoints, custom thresholds and Rear/Left/Right keep configured suppression. The new YOLOv8n candidate, larger input and rotations did not pass validation guards and are not enabled by this change.
- Installed Ultralytics retains predictor arguments between calls. Every classifier call sets the intended IoU, the loaded checkpoint's saved image size, `augment=False`, `agnostic_nms=False` and `max_det=300` explicitly to prevent Top settings leaking into later views. The calibrated profile requires size 640; custom 960/1280 checkpoints retain their saved resolution. No crop, coordinate transform, confidence inflation, model replacement, schema or UI change is involved.
- Verification includes 20 new regressions, 91 passing targeted backend tests after the compatibility fix, and 62 real offline Top-to-Rear predictions matching the frozen 0.65/0.45 references. Test isolation and input/checkpoint hashes are recorded under the training folder's `top-view-experiment-iou065/`; no station hardware or data was used.
- This improves measured per-image visible-instance detection on the prepared validation data; it does not prove recovery of all ten fingers in the user's screenshot or a unique physical bunch count across cameras. Preserve frozen test reports and validate station scenes only with manually supplied offline copies.

## 2026-10-17: Separate YOLOv8 Training on Dataset v13

- The user authorized training YOLOv8 on `D:\Banana_Ripeness.v13i.yolo26`. Training uses a separate CUDA environment and dataset copy under `D:\BananaVision-Training\v13-yolov8-20261016`; application dependencies, weights and station configuration are unchanged.
- Existing checkpoint identity was verified on October 17: `backend/app/ml/banana_yolov8n.pt` and `backend/app/ml/weights/banana_yolo26m.pt` have identical SHA-256 `e6f4e6825a642063dfd80e0b4251920e022ce85649d477ebde75a00a852f8b89`. Internal metadata identifies `yolo26m.yaml`, scale `m`, 21,791,392 parameters and the expected 12 trained classes. Filenames do not establish architecture; the existing-model benchmark applies to both copies. A fresh YOLOv8 run is a comparison candidate, not evidence that the trained checkpoint needs replacement.
- The copy removes two confirmed background-box rows and quarantines one seven-file capture with contradictory cultivar names/labels. Other labels are preserved. Source data remains intact.
- Conservative aliases merge 90 filename prefixes into 19 cultivar/ordinal groups. The user could not confirm physical identities; this grouping can merge unrelated fruit and cannot prove independence if bunches were renumbered. All matching groups remain in one split, and held-out files come only from the original unaugmented export splits.
- The prepared split contains 5,262 training, 137 validation and 137 test images, with all 12 classes represented in each. Some validation classes have few labels; per-class results and the grouping uncertainty must accompany aggregate metrics.
- The existing YOLO26 comparison supports NMS 0.65 as a calibration candidate, with lower average count error but more positive count bias. It is not a live accuracy claim or a production setting change. Calibrate the new model on validation data and reserve test data for the frozen comparison.
- The bounded training launcher completed successfully: 78 total epochs, early stopping after 20 epochs without improvement, best checkpoint at epoch 58. Automatic evaluation finished at 04:58 AM on October 17 (Asia/Manila). Validation retained NMS 0.45; 0.65 exceeded the predeclared precision-loss limits. Settings were frozen before test evaluation.
- On 137 prepared test images, existing YOLO26m versus new YOLOv8n count MAE is 0.832 versus 0.905, combined-class recall 89.46% versus 84.42%, and exact-count images 54 versus 60. The candidate's count MAE is worse in all four views; top-view combined-class recall is 89.05% versus 78.45%. Retain the existing model; no application model or station setting was changed. These offline results do not establish station accuracy, and the old model may have seen related training images.
- Independent review verified checkpoint/manifest and held-out image/label hashes, identical test inputs/configuration/matching, calibration timing and recomputed saved-prediction metrics. The [comparison summary](../audits/yolov8-v13-training-comparison-2026-10-17.json) preserves metrics and artifact hashes. Further accuracy work requires a manually supplied offline copy of four-view station-style photos with verified bunch totals/cultivar/ripeness and per-view visible-finger labels; do not extend training blindly or tune against this test set.
- The candidate remains available for testing. A later isolated smoke test using the existing app Python runtime loaded all 12 classes and ran four validation images successfully; Top/Left/Right/Rear counts 13/10/8/11 match the saved predictions. `candidate-app-runtime-smoke.json` preserves evidence. The training folder also contains `visual_comparison.html`, an offline interactive review of both models on all 137 validation photos, with view/variety/count-error filters and box/label overlays. This provides visible test results without changing the app's active model or treating dataset metrics as live accuracy.
- See [dataset audit](../yolo-dataset-audit-2026-10-16.md) for evidence and counting limitations. Generic COCO weights must be fine-tuned before they can provide the app's 12 cultivar/ripeness labels.

## 2026-10-16: Live Detection and Result Review

- YOLO retains candidates at `min(YOLO_CONFIDENCE_THRESHOLD, saved confidence_threshold / 100)`. The model setting defaults to 0.50; the saved review setting defaults to 85%. Lower saved settings remain supported.
- Fusion uses the saved setting for confidence review, alongside camera support and conflict checks. A confident box score does not establish agreement across camera views.
- Both thresholds are snapshotted before processing the camera views. Original box confidence scores are retained.
- The configuration response reports the effective saved detection cutoff as read-only `detection_confidence_threshold` in percent. The settings slider controls review; its helper identifies the **current** saved detection cutoff.
- Kiosk scan results expose the existing review flag in the result title. No database schema or model weight change is required.
- Finger count currently means the maximum per-camera YOLO box count, assuming one detection per finger. There is no matching of physical fingers across views. Do not sum view counts or infer a correction multiplier from a reported total; validate per-view detection recall and whole-bunch count error separately. Large overlapping rectangles alone do not establish incorrect training annotations.
- See [[Resolved Bugs]] for the filtering and label-pair regressions. Real-world accuracy still requires labeled offline fixtures; synthetic tests establish pipeline behavior only.

## 2026-10-16: Loading States & Data Consistency

### 1. Distinction Between Initial Load, Action, and Background Refresh
- **Decision**: Initial data loads for structured views (KPIs, tables, details) must render skeleton placeholders to match final layouts. Continuous actions (calibration, printing, backup, intake) display spinners/badges while disabling triggers. Background refreshes preserve the previous valid snapshot rather than blanking the screen.
- **Rationale**: Prevents visual flicker, prevents premature "0 records found" flashes, and provides smooth user experience on mobile and kiosk interfaces.

### 2. Snapshot Retention on Failed Refresh
- **Decision**: When a background refresh or polling fails (network dropout or temporary server unavailability), the frontend retains the previous valid data snapshot, displaying an inline `<Alert>` with explicit Retry rather than replacing the entire view with an error screen or zero counts.
- **Rationale**: Operators and supervisors can still reference active scan details and inventory while attempting recovery.

### 3. Review Queue Scope
- **Superseded 2026-11-16:** the review queue is now the flagged scans, reached with `status=Flagged` (see the 2026-11-16 entry).
- **Decision**: Review links must not pre-filter by `status=Flagged`. They must navigate using `attention=review` alone.
- **Rationale**: Low-confidence or unclassified scans require manual inspection even if not yet formally marked as "Flagged". Filtering by `status=Flagged` inadvertently hid scans that needed review.

## 2026-10-17: Analytics & AI Metric Isolation

### AI Model Confidence Isolation from Mutable Scans
- **Decision**: In `backend/app/services/analytics.py`, confidence metrics use the saved `ScanOriginalAiResult` when available, otherwise the current classification only for scans that have not been overridden. Administrator corrections without an original AI prediction are excluded from model confidence metrics.
- **Rationale**: Prevents human manual overrides or quality control corrections from contaminating AI model metrics. Analytics reflects genuine machine-learning model performance.
- **Role Isolation**: Scoped strictly by role: Operators are isolated to their own scans (`OperatorProfile.account_id == user.id`), whereas Admins view station-wide aggregates.
- **Zero-Count Safety**: Guarded denominators prevent division-by-zero across all metrics when `total_scans == 0`, presenting `"―"` gracefully without NaN or errors.
- **Operator Performance Metrics (superseded 2026-10-19)**: Removed the previously displayed `Flag Rate (%)` and `QC Overrides` columns. These are scan states, not attribution of operator actions: Operators can flag their own scans through Kiosk, automatic flags also exist, and corrections are Administrator-only. API fields remain for compatibility. The table retains Total Scans and Avg Confidence with its valid-sample tooltip; confidence is model output, not operator accuracy. No permissions changed.
- **Stable Operator Aggregation (2026-10-19)**: Analytics groups by operator ID with the current account name. Historical name snapshots remain unchanged and cannot split an operator's totals; distinct users with the same name remain separate. The existing actor scope, Manila date window and source/cultivar/status filters apply to both summary and operator endpoints. See [the operator audit](../audits/2026-10-19-operator-performance.md).

## 2026-10-17: Scan Classification Overrides & Spoilage Recalculation

### Strict Finger Count Validation & Environmental Spoilage
- **Decision**: In `backend/app/schemas/scan.py`, `ScanOverrideRequest.finger_count` enforces `Field(default=None, ge=1)` with a Pydantic field validator rejecting `< 1` or `null`. In `QualityControl.tsx` and `ScanDetail.tsx`, form submission is blocked and the Save Changes button disabled when `fingerCount` is empty or `< 1`. Changing cultivar or ripeness passes ambient `temperature` and `humidity` to `getSpoilageDays()`.
- **Rationale**: Eliminates the previous silent fallback `parseInt(...) || 0`, which caused non-numeric or cleared inputs to persist 0-finger bunches and pollute downstream batch statistics. Dynamically recalculating shelf-life estimates with environmental factors ensures operational spoilage predictions remain accurate after quality control overrides.

## 2026-10-17: Review Notes Validation & Recovery UX

### Review Note Error Layout & Whitespace Stripping
- **Decision**: In `frontend/src/pages/admin/QualityControl.tsx`, note loading failure alerts wrap the error message and inline Retry action in `flex items-center justify-between gap-3 text-sm text-muted-foreground`. In backend Pydantic models, `ScanNoteCreate` inherits `Reason` constraints (`strip_whitespace=True, min_length=1`), strictly rejecting whitespace-only notes with HTTP 422.
- **Rationale**: Prevents text overlapping or colliding against button borders on error displays during network recovery, and guarantees audit trail integrity by preventing empty or whitespace-only administrative notes.

## 2026-10-17: Top Camera 180° Rotation Fallback

### Guarded Two-Pass Detection for Top Camera Finger Recall
- **Decision**: In `backend/app/services/classification.py`, when `is_calibrated_top` is met (camera label "Top", calibrated checkpoint SHA `e6f4e6825...`, 640 input resolution, conf 0.50, and base IoU 0.45) and `yolo_top_rotation_fallback` is enabled (default `True` in `backend/app/config.py`), inference executes a second pass on a 180°-rotated frame (`image[::-1, ::-1].copy()`). Remapped bounding boxes `(W - rx2, H - ry2, W - rx1, H - ry1)` with IoU <= 0.40 against pass-1 detections are retained and appended.
- **Rationale**: Resolves severe undercounting on the Top camera view where orientation-dependent finger cluster geometry caused the detector to miss ~half the prominent foreground fingers. Rotating 180° exposes complementary finger orientations without retraining or modifying weights. The strict guards ensure non-Top camera views, custom models, and uncalibrated thresholds remain completely unaffected with zero behavioral changes.

## 2026-10-17: Multi-Camera Spatial Complementarity Finger Fusion

### Historical Heuristic Multi-Tier Count Estimate (Superseded 2026-10-21)

The 2026-10-21 conservative-count policy replaces this implementation. The earlier counting-integrity audit already superseded any interpretation of this heuristic as verified cross-camera identity matching. The synthetic 19-finger example demonstrates arithmetic on an assumed arrangement; it does not validate a physical total.
- **Decision**: In `backend/app/services/fusion_engine.py`, replaced the naive `max(finger_counts)` bottleneck with a multi-camera spatial complementarity model (`_fuse_finger_counts` and `_extract_novel_peripheral`), enabled via `multi_camera_finger_fusion: bool = True` in `backend/app/config.py`:
  1. **Anchor View:** Takes the Top camera view count ($N_{\text{top}}$) as the primary cluster tier.
  2. **Lateral Outer Flanks:** Inspects Left ($rel_x \le 0.35$) and Right ($rel_x \ge 0.65$) camera detections to identify novel peripheral fingers extending beyond Top's 2D perspective.
  3. **Inner Concavity/Underside Tier:** Inspects the Rear camera ($rel_y \ge 0.55$) to detect fingers situated along the inner lower tier occluded from above.
  4. **Strict Bounding Theorem:** Fused count is strictly bounded: $\max_{k}(c_k) \le N_{\text{fused}} \le \sum_{k} c_k$. If disabled, uncalibrated, or single-camera, it seamlessly falls back to $\max(c_k)$.
- **Rationale**: Different viewpoints can expose occluded fingers. Taking `max()` can undercount, while taking `sum()` can repeat sightings. Peripheral positions provide a heuristic estimate (e.g. 10 Top + 3 Left + 3 Right + 3 Rear = 19), but without cross-camera correspondence those additions may include already counted fingers. Bounds between maximum and sum do not prove accuracy; the current result requires operator review when it exceeds every per-view count.

## 2026-10-17: YOLO Bounding Box Deduplication & Containment Refinement

### Robust Spatial Deduplication for Rotation Fallback and Relaxed Top NMS
- **Decision**: In `backend/app/services/classification.py`, introduced `_box_containment(a, b)` and `_is_duplicate_detection(candidate, existing, iou_thresh)`:
  1. **Containment Filtering (IoM):** Calculates intersection over the smaller box area. If $\text{IoM} \ge 0.75$, the candidate is suppressed as a nested/partial fragment of an already boxed finger.
  2. **Longitudinal Axis Alignment:** If $\text{IoM} \ge 0.45$ and the horizontal center displacement $\Delta x \le 0.25 \cdot \min(w_a, w_b)$, the detection is classified as the same physical finger column and suppressed.
  3. **Multi-Pass & Self-Deduplication:** In pass 2 (rotation fallback), candidates are checked against all accepted detections (both pass 1 and previously accepted pass 2 novel fingers) to prevent cascading duplicates. In pass 1, same-class nested boxes surviving relaxed NMS are suppressed while preserving multi-class conflict detection.
- **Rationale**: Real elongated, curved banana fingers frequently produce partial segment detections in 180°-rotated passes or under relaxed Top NMS ($\text{IoU} = 0.65$). Because the sub-box area is small, standard $\text{IoU}$ often fell to $0.30 - 0.38 \le 0.40$, allowing redundant duplicate boxes to be drawn on the same finger (e.g. Finger 3 having both $76\%$ and $52\%$ boxes, and Finger 4 having both $71\%$ and $64\%$ boxes), inflating Top detections from 9 to 11 and artificially boosting fused estimates from 17 to 20 during progressive fruit removal. Combining containment with longitudinal axis alignment prevents double-counting while preserving distinct side-by-side neighbor fingers.
