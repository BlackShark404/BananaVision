# Panel Defense Interrogation & Q&A Guide (Parts 01–07)

> **Scope:** [01_AUTH_LOGIN_LOGOUT_SECURITY.md](./01_AUTH_LOGIN_LOGOUT_SECURITY.md) through [07_LANDING_PAGE.md](./07_LANDING_PAGE.md)  
> **Excluded:** `08_YOLO_DETECTION_AND_AI_PIPELINE.md`  
> **Note:** Every code reference, constant, and behavior below was verified directly against the BananaVision codebase.

---

## 1. The Core Blind Spot

Your presentation pitch claims **zero-trust security** and **automated SSD disk protection** on an offline Mini PC, yet two core mechanisms contradict those claims in the codebase:

1. **The Storage Paradox ([06_DATA_RETENTION_AND_EXPORT.md](./06_DATA_RETENTION_AND_EXPORT.md) vs [data_retention.py](../../backend/app/services/data_retention.py)):**  
   Guide 06 opens by stating that 500 scans/day generate ~4 GB/day (~120 GB/month) and will fill a 256–512 GB SSD. However, `remove_expired_orphans()` in `backend/app/services/data_retention.py` skips every directory whose UUID is referenced by `Scan.id`, `ScanImage.file_path`, or `ScanClassification.thumbnail_url`. **Valid scan images are retained indefinitely**—data retention only deletes unreferenced orphan directories.
2. **Closed Offline Identity vs. Single-Admin Lockout ([01_AUTH_LOGIN_LOGOUT_SECURITY.md](./01_AUTH_LOGIN_LOGOUT_SECURITY.md), [02_USER_MANAGEMENT_AND_ACCOUNTS.md](./02_USER_MANAGEMENT_AND_ACCOUNTS.md)):**  
   You removed public self-registration and self-service password recovery, and enforced a Last Active Admin safeguard (`users.py`). If a warehouse runs with only one Administrator account and that person leaves or forgets their password, there is zero UI mechanism to regain administrative access.

---

## 2. System Logic Interrogation

1. **Auth Attack Surface & Lockout DoS ([auth.py](../../backend/app/api/v1/auth.py), [rate_limiter.py](../../backend/app/core/rate_limiter.py), [deps.py](../../backend/app/api/deps.py)):**
   - `GET /api/v1/auth/operators` is intentionally public so the kiosk modal can display operator avatars before login, exposing active operator usernames to anyone on the LAN.
   - `login_limiter` and `pin_limiter` live in Python process memory (`MAX_ATTEMPTS = 5`, `LOCKOUT_SECONDS = 300`, `WINDOW_SECONDS = 300`), keyed per username rather than per IP. An attacker can lock out any operator for 5 minutes via 5 failed guesses, and a server reboot clears lockout state.
   - JWTs are stored in `localStorage` (`frontend/src/lib/auth.ts`), and camera MJPEG feeds pass `?token=` in the URL query string (`get_media_user` in `deps.py`), which increases exposure if XSS occurs or URLs are logged.

2. **Client-Side Bottlenecks Behind "Server-Side" Claims ([AdminContext.tsx](../../frontend/src/context/AdminContext.tsx), [Profile.tsx](../../frontend/src/pages/Profile.tsx), [config.py](../../backend/app/api/v1/config.py)):**
   - `backend/app/api/v1/activity.py` implements SQL pagination and filtering, but `AdminContext.tsx` calls `collectScanPages(...)` to fetch activity pages into React state on mount, and `ActivityLog.tsx` filters and exports in the browser.
   - `Profile.tsx` reads avatar images up to 2 MB (`2 * 1024 * 1024`) as Base64 data URLs and stores them directly in `UserAccount.avatar_url`, while `SelfProfileUpdate` (`users.py`) has no backend size or URI scheme check.
   - `export_database()` (`config.py`) builds the entire CSV inside `io.StringIO()` in RAM before returning `StreamingResponse(iter([output.getvalue()]), ...)` rather than streaming row-by-row from SQL.

3. **Process-Local Hardware Lock & Unattended Power ([cameras.py](../../backend/app/api/v1/cameras.py), [SystemConfig.tsx](../../frontend/src/pages/admin/SystemConfig.tsx)):**
   - `station_lock` is a single-process `asyncio.Lock`. Running multiple Uvicorn workers would break mutual exclusion between active scans and camera remapping.
   - Triggering Shutdown from the web UI powers off the Mini PC completely, requiring physical access to turn the station back on.

---

## 3. The Counter-Perspective

If designing strictly for an **offline, single-station warehouse appliance** with 1–10 trusted staff:

- **`HttpOnly; SameSite=Strict` Session Cookies:** Eliminates XSS access to `localStorage` tokens and authenticates `<img src="/api/v1/cameras/preview/...">` natively without passing `?token=` in URLs.
- **PostgreSQL-Backed Rate Limits & File-Based Avatars:** Persists lockouts across server reboots and prevents 2 MB Base64 strings from bloating database rows and `/auth/operators` payloads.
- **Direct Kiosk Entry Route:** Booting the station directly into `/login` or `/scan` instead of landing page `/` removes unnecessary clicks at shift start.

---

## 4. Guide-vs-Code Gotchas (Verify Before Speaking)

> [!WARNING]
> Do not repeat outdated numbers from the study notes if a panelist inspects the actual source code:
> - **Lockout duration:** `rate_limiter.py` sets `LOCKOUT_SECONDS = 300` (**5 minutes**), not 60 seconds (as stated in `00_PRESENTATION_MASTER_SCRIPT.md`).
> - **`setup_token` expiry:** `create_setup_token()` in `auth_service.py` sets `timedelta(minutes=10)` (**10 minutes**), not 15 minutes (as shown in `01_AUTH_LOGIN_LOGOUT_SECURITY.md`).
> - **Export & Backup scope:** `06_DATA_RETENTION_AND_EXPORT.md` only shows CSV, whereas `config.py` supports both **CSV and XLSX** (`format: csv | xlsx`), and `SystemConfig.tsx` / `maintenance.py` also include full station **ZIP backup and restore** (`StationBackupControls`).
> - **Landing logo accessibility:** `07_LANDING_PAGE.md` shows `<div role="button">`, while actual `Landing.tsx` (line 63) uses an even cleaner native `<button>` element.

---

## 5. Panelist Questions & Easy-to-Remember Answers (Parts 01–07)

### Part 01 — Authentication, Login/Logout, PIN Swap & Security

**Q1 (Your Example): Why does your login only consist of Login and Logout (no Sign Up / Register, no Forgot Password), and why does the Admin create all accounts?**
- **Easy Spoken Answer:**
  > "BananaVision is a closed warehouse workstation, not a public website. If anyone on the network could sign up, unauthorized people could access our cameras and inventory data. Also, the Mini PC runs offline on a local network with no email or SMS server for Forgot Password links. So the Admin acts as the central gatekeeper: creates accounts, hands out a temporary password or PIN, and forces a private password setup on first login."
- **Memory Hook:** *Closed station + offline LAN = Admin is the gatekeeper.*
- **Code Ref:** `backend/app/api/v1/auth.py` (`login`), `backend/app/api/v1/users.py` (`create_user`)

**Q2: A 4-digit PIN only has 10,000 combinations, and `/auth/operators` lists usernames without authentication. Couldn't someone brute-force a PIN or lock out operators?**
- **Easy Spoken Answer:**
  > "`/auth/operators` only returns display names, usernames, and avatars—never PIN hashes or Admin accounts—so shift workers can pick their profile on the touchscreen. To stop brute force, `pin_limiter` blocks a username for 5 minutes (`HTTP 429`) after 5 wrong guesses and writes a `pin_failed` audit log with the attacker's IP address. An Admin can review that log and reset credentials anytime."
- **Memory Hook:** *5 tries -> 5-minute lock -> IP logged.*
- **Code Ref:** `backend/app/api/v1/auth.py` (`list_kiosk_operators`, `swap`), `backend/app/core/rate_limiter.py` (`MAX_ATTEMPTS = 5`, `LOCKOUT_SECONDS = 300`)

**Q3: Why claim JWTs are "stateless" if `deps.py` queries PostgreSQL on every single request to verify `token_version`?**
- **Easy Spoken Answer:**
  > "We use signed JWTs for Bearer authentication across React and WebSockets, combined with one fast primary-key check on `token_version` in PostgreSQL. Pure stateless JWTs cannot cancel a stolen token when someone logs out or gets deactivated. On a local station with a handful of staff, that single indexed check guarantees instant session revocation with negligible latency."
- **Memory Hook:** *JWT carries identity; `token_version` is the instant kill-switch.*
- **Code Ref:** `backend/app/api/deps.py` (`_resolve_user`), `backend/app/api/v1/auth.py` (`logout`)

**Q4: Why store JWTs in `localStorage` and accept `?token=` in camera stream URLs instead of `HttpOnly` cookies?**
- **Easy Spoken Answer:**
  > "Our frontend is a decoupled React SPA calling FastAPI over Bearer headers, and standard HTML `<img>` tags for MJPEG streams cannot send custom `Authorization` headers. So `get_media_user` accepts `?token=` as a practical trade-off for live calibration previews, mitigated by 8-hour token lifetimes and instant `token_version` revocation."
- **Memory Hook:** *`<img>` tags can't send headers, so `MediaUser` uses short-lived revocable tokens.*
- **Code Ref:** `frontend/src/lib/auth.ts`, `backend/app/api/deps.py` (`get_media_user`)

---

### Part 02 — User Management & Account Governance

**Q5: Why is there no Delete User button—only Active/Inactive—and what happens if the *only* Admin gets locked out?**
- **Easy Spoken Answer:**
  > "We never delete user accounts because historical scans and `ActivityLog` rows link to those user IDs. Deleting a user would break audit history, whereas deactivating them blocks login and bumps `token_version` immediately. To prevent total lockout, our Last Active Admin check (`HTTP 409`) blocks self-deactivation or demotion, and facilities are advised to keep at least two Admin accounts. Because the unit is offline, losing the sole Admin requires physical host access on the Mini PC."
- **Memory Hook:** *Deactivate preserves history; two Admins prevent sole-admin lockout.*
- **Code Ref:** `backend/app/api/v1/users.py` (`update_user`, lines 198–225)

**Q6: Why split `UserAccount`, `AdminProfile`, and `OperatorProfile` into separate tables instead of one `users` table, and what happens on promotion/demotion?**
- **Easy Spoken Answer:**
  > "Only Operators use 4-digit kiosk PINs and own `Scan` records, while Admins manage system configuration. Splitting profiles keeps role-specific columns clean without breaking scan foreign keys. When an Operator is promoted to Admin, we keep their past scan ownership, clear their `pin_hash` so an old 4-digit PIN cannot bypass password login, and bump `token_version` so they must log in again with their new role."
- **Memory Hook:** *Promote = keep scan history, wipe PIN, kill old sessions.*
- **Code Ref:** `backend/app/api/v1/users.py` (`update_user`, lines 250–275)

**Q7: Creating a user or resetting credentials returns the plaintext temporary password/PIN in the API response. Isn't that risky?**
- **Easy Spoken Answer:**
  > "In an offline warehouse without email, the Admin has to see the generated temporary credential once to hand it to the worker in person—so we send it with `Cache-Control: no-store` inside `CredentialHandoffDialog`. That temporary credential cannot open the dashboard; it only issues a 10-minute `setup_token` scoped strictly to `/setup-password` or `/setup-pin` so the worker must set their own private credential immediately."
- **Memory Hook:** *Temp credential only buys a 10-minute `setup_token`, never dashboard access.*
- **Code Ref:** `backend/app/api/v1/users.py` (`create_user`, `reset_user_password`, `reset_user_pin`), `backend/app/services/auth_service.py` (`create_setup_token`)

---

### Part 03 — Profile Management

**Q8: Why can't Operators edit their own username or full name in Profile, and isn't storing 2 MB Base64 avatars in PostgreSQL heavy?**
- **Easy Spoken Answer:**
  > "Operators can only update their avatar and change their own password or PIN after verifying their current one. Locking username and full name stops workers from renaming themselves to confuse audit logs or impersonate someone else. Storing Base64 avatars capped at 2 MB kept the prototype self-contained without an external file bucket, though moving avatars to disk storage and adding backend size checks is a clean production step."
- **Memory Hook:** *Self-service = avatar + verified password/PIN; identity stays Admin-locked.*
- **Code Ref:** `backend/app/api/v1/users.py` (`SelfProfileUpdate`, `update_own_profile`), `frontend/src/pages/Profile.tsx` (`handleAvatarUpload`)

**Q9: How do you guarantee Profile lifetime scan statistics are accurate instead of only averaging the rows currently visible on screen?**
- **Easy Spoken Answer:**
  > "The frontend does not compute lifetime metrics from table state. `/users/me/summary` calculates `COUNT`, `AVG`, and 7-day totals directly in PostgreSQL across all retained scans. Operators are filtered strictly to scans linked to their own `OperatorProfile`, while Admins see whole-station totals."
- **Memory Hook:** *PostgreSQL `COUNT`/`AVG` across all scans, filtered by role.*
- **Code Ref:** `backend/app/api/v1/users.py` (`own_profile_summary`)

---

### Part 04 — Activity Logs & Auditing

**Q10: Your doc highlights server-side pagination in `/activity`, yet `AdminContext` loops through pages into React state. Won't 50,000 logs slow down the browser?**
- **Easy Spoken Answer:**
  > "The backend `/activity` endpoint enforces true SQL `LIMIT`, `OFFSET`, and indexed filters up to 200 rows per page (`AUDIT-01`). In the current frontend, `AdminContext` pulls pages client-side so table filtering and instant export work together smoothly at prototype scale. When log volume grows into tens of thousands, the frontend can pass `search`, `action`, and `page` straight to those existing backend query parameters."
- **Memory Hook:** *Backend SQL pagination is ready; frontend loads pages for instant filter/export.*
- **Code Ref:** `backend/app/api/v1/activity.py` (`list_activity`), `frontend/src/context/AdminContext.tsx` (`collectScanPages`), `frontend/src/pages/admin/ActivityLog.tsx`

**Q11: What prevents a user-supplied string from breaking CSV columns or injecting malicious Excel formulas (`=CMD(...)`) in Activity Log exports?**
- **Easy Spoken Answer:**
  > "Every CSV cell goes through `formatCsvCell` in `exportUtils.ts`. It wraps values in quotes and doubles internal quotes (`""`) per RFC 4180 so commas never shift columns, and it prefixes leading formula triggers (`=`, `+`, `@`, or non-numeric `-`) with an apostrophe so Excel treats them as plain text. Our XLSX exporter also writes text cells as safe `inlineStr` values."
- **Memory Hook:** *Double quotes stop broken columns; leading `'` stops Excel formulas.*
- **Code Ref:** `frontend/src/lib/exportUtils.ts` (`formatCsvCell`, `downloadCsv`, `downloadXlsx`)

---

### Part 05 — System & Scanner Configuration

**Q12: What happens if Windows or Linux swaps USB camera indices on reboot, or an Admin remaps cameras while an Operator is scanning?**
- **Easy Spoken Answer:**
  > "When USB indices shift after a reboot, the Admin uses Camera Calibration: `/cameras/discovery` lists physical devices without hijacking active handles, and live 15 FPS MJPEG previews let the Admin visually match Top, Left, Right, and Rear views. Both `/config` and `/cameras/mapping` acquire `station_lock`—if a scan is running, the backend rejects remapping with `HTTP 409 Conflict` until the scan finishes."
- **Memory Hook:** *Discovery + 15 FPS preview fixes swapped USBs; `station_lock` blocks mid-scan edits (`409`).*
- **Code Ref:** `backend/app/api/v1/cameras.py` (`discover_cameras`, `update_camera_mapping`), `backend/app/api/v1/config.py` (`update_config`)

**Q13: Why stream MJPEG instead of WebRTC, and how do you stop two Admins from overwriting each other's settings?**
- **Easy Spoken Answer:**
  > "MJPEG works offline with zero signaling servers and renders straight inside a normal `<img>` tag using downscaled frames so the Mini PC CPU stays light. To prevent silent overwrites when two Admins open Settings at once, configuration saves enforce optimistic concurrency via `expected_revision`—stale updates are rejected instead of overwriting newer changes."
- **Memory Hook:** *MJPEG = zero WebRTC complexity; `expected_revision` stops silent overwrites.*
- **Code Ref:** `backend/app/api/v1/cameras.py` (`generate_frames`), `backend/app/api/v1/config.py` (`_update_config`)

**Q14: Isn't a browser Shutdown/Restart button risky if someone clicks it mid-scan or by mistake?**
- **Easy Spoken Answer:**
  > "Power controls require confirmation dialogs in the UI and route through the runtime `coordinator`, which pauses new scans and waits for active scans to finish before dispatching the OS command. When canceling a pending power action or recovering after maintenance (`power-accepted` / `recovery-required`), the backend requires an active Admin's password before reopening normal scanning."
- **Memory Hook:** *Drain scans first -> Admin confirmation -> recovery password gate.*
- **Code Ref:** `frontend/src/pages/admin/SystemConfig.tsx`, `backend/app/api/v1/auth.py` (`recovery_login`), `backend/app/api/v1/maintenance.py`

---

### Part 06 — Data Retention & Scan Export

**Q15: Guide 06 warns that 500 scans/day will fill the Mini PC SSD, yet `data_retention.py` skips every folder linked to a `Scan` row. Doesn't the disk still fill up?**
- **Easy Spoken Answer:**
  > "Good catch—that boundary is intentional. `data_retention.py` runs every 6 hours and **only** deletes unreferenced orphan capture folders older than the retention window, such as failed or abandoned captures. It never silently erases valid scan evidence so quality audits stay complete. To reclaim disk space from older valid scans, Admins export a full station ZIP backup first and manage retention intentionally."
- **Memory Hook:** *Retention cleans **orphans only**—never deletes valid scan history.*
- **Code Ref:** `backend/app/services/data_retention.py` (`data_retention_worker`, `remove_expired_orphans`)

**Q16: Why label the button "Export Scan Summaries" instead of "Database Backup", and how does it differ from real backups?**
- **Easy Spoken Answer:**
  > "Earlier wording tricked users into thinking a CSV file could restore the entire station (`RETENTION-03`). `/config/export` only exports CSV or XLSX scan summary rows—it excludes user accounts, system settings, audit logs, and captured images, so it cannot restore a database. Actual disaster recovery uses the separate station ZIP backup and restore controls handled in `maintenance.py`."
- **Memory Hook:** *CSV/XLSX = spreadsheet report; ZIP maintenance = real restore backup.*
- **Code Ref:** `backend/app/api/v1/config.py` (`export_database`), `backend/app/api/v1/maintenance.py` (`create_backup`), `frontend/src/pages/admin/SystemConfig.tsx`

---

### Part 07 — Landing Page

**Q17: Why build a public Landing Page on an internal packing-station kiosk instead of opening directly to Login?**
- **Easy Spoken Answer:**
  > "The Landing Page gives supervisors, QA auditors, and evaluators a self-contained offline overview of supported banana cultivars (Lakatan, Latundan, Cardaba), ripeness stages, and hardware specs without needing internet or external CDNs. Daily operators can still go straight to `/login`, while the sticky header puts a one-click `Login to System` button right at the top using accessible native `<button>` controls."
- **Memory Hook:** *Offline stakeholder showcase on `/`; direct `/login` route for operators.*
- **Code Ref:** `frontend/src/pages/Landing.tsx`

---

## 6. 60-Second Rapid Drill Sheet

| # | Topic | 1-Line Memory Hook |
|---|---|---|
| Q1 | Login/Logout only | Closed station + offline LAN = Admin is gatekeeper |
| Q2 | PIN brute force | 5 tries -> 5-minute lock (`429`) -> IP logged |
| Q3 | JWT + DB check | JWT carries identity; `token_version` is instant kill-switch |
| Q4 | `localStorage` & `?token=` | `<img>` tags can't send headers -> short-lived revocable `MediaUser` token |
| Q5 | No Delete & Last Admin | Deactivate keeps history; two Admins prevent sole-admin lockout |
| Q6 | Split Profiles | Promote = keep scan history, wipe PIN, kill old sessions |
| Q7 | Temp Credentials | Temp login only buys 10-min `setup_token`, never dashboard access |
| Q8 | Self-Service Profile | Avatar + verified password/PIN only; identity stays Admin-locked |
| Q9 | Profile Stats | PostgreSQL `COUNT`/`AVG` across all scans, filtered by role |
| Q10 | Activity Pagination | Backend SQL pagination ready; frontend loads pages for fast filter/export |
| Q11 | CSV/XLSX Safety | Double quotes stop broken columns; leading `'` stops Excel formulas |
| Q12 | Camera Swap & Lock | Discovery + 15 FPS preview fixes USBs; `station_lock` blocks mid-scan edits (`409`) |
| Q13 | MJPEG & Config Edits | MJPEG avoids WebRTC overhead; `expected_revision` prevents overwrites |
| Q14 | Station Power | Drain active scans -> Admin confirmation -> recovery password gate |
| Q15 | Retention Scope | Retention cleans orphans only—never deletes valid scan evidence |
| Q16 | Export vs Backup | CSV/XLSX = report; ZIP maintenance = real restore backup |
| Q17 | Landing Page | Offline showcase on `/`; direct `/login` route for operators |
