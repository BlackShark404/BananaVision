# Kent RG A. Baguio — Assigned Features Review and Panel Preparation

> **Status update — October 5, 2026:** This report's source findings describe the October 4 review revision and are preserved as historical evidence. The [changelog](CHANGELOG.md) tracks subsequent fixes. The six remaining implementation issues—CREATE-02, PROFILE-03, CONFIG-03, SCANNER-03, RETENTION-02 and RETENTION-03—have now been addressed, together with a follow-up correction requiring actual authentication proof for password/PIN setup. Current deployment instructions are in [backend/README.md](../backend/README.md).
>
> **Still required:** Physical camera/reboot checks, host permissions/autostart, offline asset provisioning, model identity/performance/latency evidence, deployed schema validation, legacy credential rotation, full live-session/role acceptance checks, and landing/contact/claim verification. Do not infer deployment readiness from the historical report or checked implementation items.


**Project:** BananaVision  
**Reviewed:** October 4, 2026  
**Repository:** `C:\Users\Kent\Documents\GitHub\BananaVision`  
**Source revision:** `96bcd5c`  
**Review mode:** Documentation and source inspection. No application code, settings, database records, dependencies, or hardware configuration were changed.

This report covers Kent's 13 assigned features. Related camera, scan, session, and startup code was traced where it affects those features. Findings below are supported by source inspection; they have **not** been reproduced against a running application. Browser layout, physical hardware, trained model performance, and the deployed database remain unverified. Existing tests were inspected for coverage, but no tests, build, server, scan, reset, shutdown, or cleanup operation was executed.

Priority: **Critical** = account takeover path; **High** = access-control failure or a core assigned workflow that does not deliver its promised behavior; **Medium** = validation, consistency, observability, or usability gap. Recommendations describe future work only.

## Project Goal

BananaVision combines camera images and environmental measurements to classify banana cultivar and ripeness, count fingers, estimate spoilage, and support inventory and quality review. A Mini PC hosts the backend, database connection, camera services, sensor connection, and browser interface. Operators scan and inspect results; administrators manage accounts and system settings.

## Current State

The repository contains real React pages, REST handlers, SQLAlchemy models, authentication services, a multi-camera capture pipeline, YOLO inference, fusion, and spoilage estimation. This is more than an interface prototype. However, several assigned workflows are incomplete or inconsistent between UI and backend. A success message does not always mean that data was saved.

Useful existing controls include bcrypt password/PIN hashing, JWT signature and expiry verification, backend administrator checks on user creation/update/reset and configuration writes, inactive-account checks on ordinary authenticated REST requests, unique usernames, some activity recording, and camera frame validation.

Model files are **present locally** under `backend/app/ml/weights/`: two banana YOLO weight files and the RFR model. The allowlisted model-path setting in the local environment selects `banana_yolo26m.pt`. This establishes the configured filename, **not independently verified model architecture or accuracy**. Model binaries were not loaded. The weights are ignored by Git and need a separate deployment handoff.

## Project Structure

```text
BananaVision/
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py, config.py
│   │   ├── api/deps.py, api/v1/
│   │   ├── core/               authentication utilities, database, startup
│   │   ├── models/, schemas/   persistence and API contracts
│   │   ├── services/           authentication, camera, YOLO, fusion, scans, sensors, RFR
│   │   ├── ws/                 live-event connections and broadcasting
│   │   └── ml/weights/         local model assets
│   ├── tests/                 dashboard and scan-log tests
│   ├── requirements.txt, pyproject.toml
│   └── seed.py
├── frontend/
│   ├── src/App.tsx
│   ├── src/context/            AuthContext, AdminContext, ScanContext, InventoryContext
│   ├── src/lib/                API client and browser authentication storage
│   ├── src/pages/              Landing, Login, Profile, operational pages
│   ├── src/pages/admin/        UserManagement, ActivityLog, SystemConfig, other admin pages
│   ├── src/components/         camera calibration and shared UI
│   ├── tests/                 dashboard browser tests
│   └── package.json, vite.config.ts
├── arduino/                   DHT22 integration
├── docs/                      context, plans, schema, workflow and deployment notes
└── setup / dev / start / seed scripts for Windows and Linux
```

## Important Files

| File | Responsibility |
| --- | --- |
| [App.tsx](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/App.tsx:41) | Public, authenticated, and admin page routing. |
| [AuthContext.tsx](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AuthContext.tsx:39) | Login, PIN swap, logout, credential-change flows, and cached user state. |
| [AdminContext.tsx](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:62) | Account, device, audit-log, and configuration loading and updates. |
| [api.ts](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/lib/api.ts:16) | REST requests, bearer token attachment, and error handling. |
| [auth.py](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:66) | Login, PIN swap, password/PIN changes, and logout endpoints. |
| [users.py](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:35) | User listing, account creation/editing, and dedicated reset endpoints. |
| [deps.py](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/deps.py:21) | Current-user validation, active status, and administrator authorization. |
| [config.py API](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:31) | Persisted settings, device-record synchronization, CSV export, and power commands. |
| [cameras.py](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:23) | Camera inventory, preview feeds, and hardware-position mapping. |
| [startup.py](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/core/startup.py:51) | Database initialization, initial admin, model and hardware startup, and background tasks. |
| [classification.py](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/classification.py:120) | Loads configured weights and performs per-image YOLO inference. |
| [scan_service.py](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/scan_service.py:38) | Capture, pre-detection, classification, fusion, sensor context, spoilage prediction, and persistence. |

## Program Flow

1. The backend loads environment-derived settings and initializes database tables through SQLAlchemy metadata. Startup seeds an initial admin when no accounts exist, loads models, and opens camera/sensor resources.
2. React initializes providers and routes. Authentication state is restored from browser storage.
3. Login submits credentials to `/api/v1/auth/login`; successful authentication returns a JWT and user data. The browser stores both and attaches the JWT to REST requests.
4. Assigned pages call the API through their contexts. Backend dependencies validate identity/status and, on protected mutations, administrator role. Database requests commit through the database dependency.
5. A kiosk scan calls `/api/v1/scans/trigger`. The camera manager captures available feeds, saves images, and the pipeline runs banana pre-detection and custom inference.
6. Fusion combines camera results. The pipeline uses sensor context and treatment to estimate spoilage, writes scan evidence and history, and broadcasts results.
7. The frontend displays account/configuration responses and WebSocket updates. Some context error handlers currently substitute local state changes for successful persistence.

## Component Communication

Browser-to-backend communication uses REST under `/api/v1` and WebSockets at `/api/v1/ws`. The API client defaults to port 8000 on the browser's hostname; Vite serves the frontend on its development port. Backend-to-database communication uses async SQLAlchemy/PostgreSQL configuration. OpenCV accesses host cameras, and pyserial connects the host to the Arduino DHT22 device. Captures are files on the backend host, separate from database metadata.

A remote browser's `localhost` is its own device. LAN/remote deployment must use the Mini PC's reachable backend address or an appropriate proxy. The current API fallback explicitly uses HTTP; a deployment with an HTTPS frontend must configure a compatible backend URL. No network configuration was changed in this review.

## Technologies Used

React 19, TypeScript, React Router, Vite, Tailwind CSS, shared Shadcn/Radix UI components, Python/FastAPI, Pydantic, SQLAlchemy, PostgreSQL/asyncpg, PyJWT, bcrypt, OpenCV, Ultralytics, scikit-learn/joblib, WebSockets, and Arduino/pyserial. The Python project specifies Python 3.11 or newer. Current dependencies use PyJWT and direct bcrypt, although some older documentation describes python-jose/passlib.

## Current Task and Assignment Coverage

The task is to understand and assess Kent's assigned modules, produce this report, and leave implementation unchanged. Supplier management, delivery intake, inventory, analytics, and quality control are other modules; they appear here only where they consume Kent's settings or account permissions.

| # | Assigned feature | What exists | Readiness assessment |
| --- | --- | --- | --- |
| 1 | Login/Logout | Real credential authentication and local logout | Critical credential-change weakness and incomplete session invalidation. |
| 2 | Create Account | Admin-only API, unique usernames, role-specific profiles | Failure handling and creation-field mismatch need correction. |
| 3 | User Management | List, search, filters, UI pagination, role/status controls | Backend listing permissions and role transitions need correction. |
| 4 | Activate/Deactivate User | Persisted status; REST checks inactivity | Admin recovery safeguards and live-session handling incomplete. |
| 5 | Edit User | Admin-only update API | Username is not updated; roles/profiles and failure feedback inconsistent. |
| 6 | Reset Password | Reset UI and dedicated backend endpoint | UI does not call the endpoint that changes the password hash. |
| 7 | Profile Management | Avatar, password/PIN dialogs, theme, activity and statistics | Operator avatar persistence and credential verification broken. |
| 8 | Activity Logs | Real audit records, filters, CSV, backend pagination | Backend access, complete history, and audit coverage incomplete. |
| 9 | System Configuration | Persisted camera IDs, threshold, retention flag, export, power controls | Save results and validation do not reliably match claims. |
| 10 | Scanner Config | Camera-ID editing and physical-position mapping | Mapping is publicly writable; camera identity/status synchronization inconsistent. |
| 11 | AI Settings (YOLO26) | Threshold UI, real inference integration, local weights | Saved threshold does not control inference; version wording inconsistent. |
| 12 | Data Retention Settings | Persisted enable/disable flag and 30-day UI promise | No retention worker or enforcement was found. |
| 13 | Landing Page | Public sections, responsive navigation, login links, FAQs, contact action | Exists; claims and accessibility need validation/refinement. |

## Confirmed Findings by Assigned Feature

### 1. Login / Logout

**AUTH-01 — Critical: password and PIN changes do not establish identity.** The password-change handler accepts a username and new password, calls the service, and returns a normal JWT. It has no current-user dependency, old-password verification, or limited reset/setup authorization. The PIN-change path has the same issue. A caller who knows an account username can change its credential without proving ownership; the password path applies to administrator accounts too. The service does not restrict changes to accounts awaiting setup. Evidence: [auth.py:141](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:141), [auth.py:168](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:168), [auth_service.py:90](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/auth_service.py:90), [auth schemas:19](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/schemas/auth.py:19).

**Needed improvement:** Separate an authenticated self-service change from first-login/reset setup. Verify current credentials server-side for normal changes, and require limited, expiring authorization for setup. Derive account ownership from verified identity. Do not treat a prior UI screen as proof of authentication.

**AUTH-02 — High: logout and credential reset do not revoke existing JWTs.** Logout records an event and returns success; the frontend deletes browser storage. Tokens contain identity/role and expiry but no checked session version or revocation state. Ordinary request validation does not inspect `requires_password_change`. An already issued token can remain usable after logout or password reset while the account is active. Evidence: [auth.py:195](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:195), [security.py:47](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/core/security.py:47), [deps.py:21](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/deps.py:21), [AuthContext.tsx:109](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AuthContext.tsx:109).

**Needed improvement:** Define session invalidation for logout, password/PIN reset, and account security changes, and enforce it centrally. Decide explicitly whether password and kiosk sessions are separate security scopes.

**AUTH-03 — High: live-event access can bypass login/status checks.** The WebSocket handler accepts connections when the token is absent. If supplied, it checks the token signature/expiry but never loads the account or verifies active status. Room subscriptions are client selected, including later subscription changes. This is not guarded by an environment check despite the development-mode comment. Scan broadcasts include operator/supplier context and results. Evidence: [handlers.py:28](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/ws/handlers.py:28), [scan_service.py:64](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/scan_service.py:64), [scan_service.py:309](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/scan_service.py:309).

**Needed improvement:** Require identity and active status, authorize subscriptions and delivered events, and handle expiry/deactivation for existing connections. Coordinate this with the scan owner so operator-scoped REST views are not bypassed through live events.

**AUTH-04 — High: no login/PIN attempt throttling was found in the application.** Login and PIN-swap services process each attempt directly. Searches of the inspected source found no application rate limiter, attempt counter, cooldown, or lockout handling. Infrastructure controls were not inspected. Evidence: [auth.py:66](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:66), [auth.py:104](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:104), [auth_service.py:26](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/auth_service.py:26).

**Panel may ask:** Can someone change an admin password without logging in? Does a copied token still work after logout? Can an inactive account receive live updates? What prevents repeated guesses of the kiosk PIN?

### 2. Create Account

**SAVE-01 — High: failed account creation can produce a fake local account.** `addUser` catches any failed create request and appends a local record with a random ID. The page announces creation and closes the dialog before the request completes. A duplicate username, denied request, or disconnected backend can therefore appear to succeed. Evidence: [AdminContext.tsx:134](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:134), [UserManagement.tsx:77](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/UserManagement.tsx:77).

**Needed improvement:** Return an awaitable result, show success only after a committed operation, preserve failed input, and display the backend error. Avoid substituting a local account for persisted data.

**CREATE-01 — Medium: the creation form's status selection is ignored.** The form includes Active/Inactive, but `addUser` omits status, `UserCreate` has no status field, and the account model defaults to Active. Selecting Inactive does not create an inactive account. Evidence: [UserManagement.tsx:316](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/UserManagement.tsx:316), [AdminContext.tsx:135](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:135), [user schema:21](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/schemas/user.py:21), [user_account.py:32](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/models/user_account.py:32).

**CREATE-02 — High: shared temporary credentials and initial admin bootstrapping need a defined handoff.** The UI creates accounts with fixed temporary credentials. Startup creates a fixed initial admin when the database has no users, without an environment restriction or explicit forced password-change flag, and writes its credential pair to the log. This report deliberately does not repeat the credential values. Evidence: [UserManagement.tsx:83](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/UserManagement.tsx:83), [startup.py:249](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/core/startup.py:249), [user_account.py:39](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/models/user_account.py:39).

**Needed improvement:** Use a controlled bootstrap/setup process, remove credential logging, and establish secure temporary-credential issuance and replacement. Administrator-created registration is the current design; public signup is not automatically a missing requirement.

**Panel may ask:** What happens with duplicate usernames? Can an account be created as inactive? How are first-time credentials delivered? How is the initial administrator secured?

### 3. User Management

**ACCESS-01 — High: user-directory and audit-log access are broader than the admin-only pages.** User listing and activity listing require `CurrentUser`, not `AdminUser`, and return all records without operator scope. The provider requests these resources for every signed-in user. An operator can retrieve the directory and system audit records directly, including user names, account state, and audit IP/details. No password hashes are exposed by `UserResponse`. Evidence: [users.py:35](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:35), [activity.py:19](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/activity.py:19), [AdminContext.tsx:73](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:73), [App.tsx:76](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/App.tsx:76).

**Needed improvement:** Define the account-data access matrix. Keep full administrative listings restricted; expose only the limited self-profile and kiosk-selection information needed by operators. If profile activity is allowed, scope it by authenticated account ID.

**ROLE-01 — High: editing roles does not reconcile role-specific profiles.** Creation builds an AdminProfile or OperatorProfile. Update changes only the role foreign key. Promoting an operator leaves the operator profile/PIN; demoting an admin does not create an operator profile. The scan trigger requires an operator profile, while PIN authentication tests profile presence but not current Operator role. These paths become inconsistent after a role change. Evidence: [users.py:72](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:72), [users.py:111](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:111), [auth_service.py:59](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/auth_service.py:59), [scans.py:42](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/scans.py:42).

**Needed improvement:** Treat role transition as a defined transaction: reconcile profiles, preserve linked history appropriately, require credential setup where needed, and enforce role on PIN/scan routes. Do not blindly delete an operator profile with historical scans.

**Panel may ask:** Are API permissions the same as menu visibility? What happens when an admin becomes an operator? Can a promoted administrator still log in with the old kiosk PIN?

### 4. Activate / Deactivate User

**ADMIN-01 — High: self-deactivation/demotion and loss of the final active admin are not guarded.** The generic update endpoint permits role/status changes for any target, including the requester, without checking whether another active admin remains. Ordinary REST requests correctly reject inactive users, but the WebSocket limitation in AUTH-03 remains. Evidence: [users.py:94](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:94), [deps.py:50](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/deps.py:50).

**SAVE-02 — High: failed deactivation or editing still updates local state.** Account update catches failures and applies the requested values locally. The user page announces success without waiting. This can show Inactive when the backend account is still Active. Evidence: [AdminContext.tsx:147](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:147), [UserManagement.tsx:79](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/UserManagement.tsx:79).

**Needed improvement:** Enforce a recoverable admin policy and accurate persistence feedback. Show confirmation for consequential status changes and demonstrate actual denial of the disabled account on subsequent requests and live channels.

**Panel may ask:** Can you deactivate yourself? What if the final admin is disabled? Is the account actually disabled after a failed save? How does deactivation affect an already open session?

### 5. Edit User

**EDIT-01 — Medium: username editing is offered but unsupported by the update schema.** The dialog keeps its username input editable and submits it, but `UserUpdate` contains no username field. The general update cannot persist that change. Evidence: [UserManagement.tsx:301](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/UserManagement.tsx:301), [user schema:29](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/schemas/user.py:29).

**VALIDATION-01 — Medium: edit and credential rules differ between UI and backend.** Creation validates name length, but the update schema does not constrain full-name length or trim whitespace. Backend password schemas accept a minimum of four characters, while the login/profile setup UI checks six. PIN schemas check only length, without requiring digits. These differences allow values the interface suggests should be rejected. Evidence: [user schema:21](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/schemas/user.py:21), [auth schema:19](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/schemas/auth.py:19), [Login.tsx:34](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Login.tsx:34), [Profile.tsx:137](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Profile.tsx:137).

**Needed improvement:** Either disable username editing or implement it consistently with uniqueness rules. Align chosen policies across server and client; bound and normalize editable values. Also address SAVE-02 and ROLE-01.

**Panel may ask:** Does changing the username actually work after refresh? Can an empty or oversized name be saved? Where are password/PIN rules enforced?

### 6. Reset Password

**RESET-01 — High: the reset buttons call the wrong operation.** The UI passes `password` or `pin` to `updateUser`, which sends PATCH `/users/{id}`. `UserUpdate` does not contain either credential, and that handler never changes their hashes. Dedicated POST reset-password/reset-pin endpoints exist, but the frontend API namespace has no methods for them. The UI can set the required-change flag and announce a reset while the old password/PIN remains stored. Evidence: [UserManagement.tsx:101](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/UserManagement.tsx:101), [AdminContext.tsx:147](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:147), [api.ts:169](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/lib/api.ts:169), [user schema:29](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/schemas/user.py:29), [users.py:131](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:131).

**Needed improvement:** Connect each reset control to the corresponding protected backend endpoint, await its result, and verify old/new credential behavior. Coordinate with AUTH-01/AUTH-02 so setup is authorized and existing sessions follow the reset policy. Administrator-assisted recovery is already the intended workflow; email recovery is not assumed required.

**Panel may ask:** After reset, does the old password stop working? Which endpoint changes the hash? Is replacement required on the next login? Can you prove the same behavior for kiosk PIN reset?

### 7. Profile Management

**PROFILE-01 — High: an operator's avatar change cannot use the selected backend route.** Profile uploads call `updateUser`, but PATCH `/users/{id}` is administrator only, including when an operator edits their own account. The fallback changes local state and the page shows success. It does not establish durable profile persistence. Evidence: [Profile.tsx:38](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Profile.tsx:38), [AdminContext.tsx:159](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:159), [users.py:94](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:94).

**PROFILE-02 — High: the displayed current-password field is not verified.** The profile handler sends only username/new password through `changePasswordAndLogin`; that context passes an empty current password. The backend request schema does not declare current_password, and the service never verifies it. This is another visible manifestation of AUTH-01. Evidence: [Profile.tsx:131](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Profile.tsx:131), [AuthContext.tsx:117](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AuthContext.tsx:117), [api.ts:104](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/lib/api.ts:104).

**PROFILE-03 — Medium: lifetime statistics are computed from a partial scan page.** Profile counts/averages use ScanContext data, which requests `per_page: 100`, while the legacy backend list expects `page_size` and defaults to 20. It does not fetch every page. Profile activity is matched by full name rather than immutable user ID. The UI also labels confidence as detection accuracy, although it is averaging model confidence scores. Evidence: [Profile.tsx:70](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Profile.tsx:70), [Profile.tsx:107](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Profile.tsx:107), [Profile.tsx:258](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Profile.tsx:258), [ScanContext.tsx:87](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/ScanContext.tsx:87), [scans.py:87](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/scans.py:87).

**Needed improvement:** Add an ownership-scoped profile operation with restricted fields and server validation. Fix current-credential verification; use server-scoped aggregates and user IDs for statistics/activity; label confidence accurately. Full name and username are currently read-only on Profile; changing that is a requirements decision, not automatically a defect.

**Panel may ask:** Can an operator's avatar survive a new login? What happens with an incorrect current password? Are lifetime counts based on all records? Is confidence the same as measured accuracy?

### 8. Activity Logs

**AUDIT-01 — Medium: filtering, pagination, statistics, and export operate on only the initially loaded logs.** The provider requests `per_page: 100`; the endpoint expects `page_size` and defaults to 50. It receives total/page metadata, but the provider discards it. The page then filters, paginates, counts, and exports that local subset. Older matching actions can disappear and a CSV can look complete while omitting history. Evidence: [AdminContext.tsx:78](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:78), [activity.py:20](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/activity.py:20), [ActivityLog.tsx:39](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/ActivityLog.tsx:39), [ActivityLog.tsx:69](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/ActivityLog.tsx:69).

**AUDIT-02 — Medium: important security operations lack dedicated audit coverage.** Successful login/logout and general account/configuration changes add activity records. Dedicated admin password/PIN resets do not, and failed login/PIN attempts return before activity recording. General updates record field names, not old/new role or status values. Evidence: [users.py:120](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:120), [users.py:131](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/users.py:131), [auth.py:71](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:71), [auth.py:109](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/auth.py:109).

**AUDIT-03 — Medium: CSV quoting does not escape embedded quotation marks.** The export wraps each cell in quotes but does not double quotes inside values. Names/details containing quotation marks can produce malformed CSV. Evidence: [ActivityLog.tsx:79](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/ActivityLog.tsx:79).

**Needed improvement:** Fix ACCESS-01, preserve server paging/filter contracts, export the defined complete or filtered scope, and record actor/target/outcome for resets and consequential account changes without recording secrets. Escape CSV correctly and make the displayed timestamp timezone explicit.

**Panel may ask:** Can operators retrieve admin activity directly? Can search find a log older than the first 50 entries? Who reset a password? Does CSV export include the full filtered history?

### 9. System Configuration

**CONFIG-01 — High: save completion is simulated rather than tied to the request.** The page waits 800 ms, calls a void context update, and announces success. The context updates configuration locally regardless of request outcome and only logs a warning on failure. Retention toggling has the same feedback problem. Evidence: [SystemConfig.tsx:82](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:82), [SystemConfig.tsx:110](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:110), [AdminContext.tsx:178](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:178).

**CONFIG-02 — Medium: configuration lacks backend range and camera-ID validation.** The update schema accepts any float threshold and unrestricted camera-ID text. The handler truncates the threshold to an integer. The UI prevents some duplicate renames, but the backend does not enforce uniqueness/nonempty IDs or hardware mapping rules. Default camera lists also differ between initial frontend state, GET creation, and PATCH creation. Evidence: [common.py:209](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/schemas/common.py:209), [config.py:59](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:59), [config.py:68](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:68), [AdminContext.tsx:69](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/context/AdminContext.tsx:69).

**CONFIG-03 — Medium: power-command responses do not verify execution success.** Shutdown/restart launch OS commands with Popen. Exceptions are printed, after which the endpoint still returns an initiated message; a spawned command's failure is not checked. Frontend confirmation dialogs exist, but service autostart after reboot depends on host setup. These actions were not invoked. Evidence: [config.py:131](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:131), [config.py:157](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:157), [SystemConfig.tsx:397](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:397).

**Needed improvement:** Await persisted results, expose failure accurately, centralize defaults and validation, and document when each setting takes effect. Define safe power-command behavior, active-scan handling, and deployment autostart evidence.

**Panel may ask:** What proves a save succeeded? Can an API caller submit an invalid threshold? Do services automatically resume after reboot? Does the system detect an OS permission failure?

### 10. Scanner Config

**SCANNER-01 — High: hardware mapping can be changed without authentication.** POST `/cameras/mapping` writes the backend environment file, releases camera handles, and reinitializes the camera manager without an administrator/current-user dependency. The calibration UI also sends no authorization header. Camera preview feeds are public too, so their exposure should be explicitly decided. Evidence: [cameras.py:101](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:101), [cameras.py:117](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:117), [CameraCalibrationModal.tsx:58](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/components/CameraCalibrationModal.tsx:58).

**SCANNER-02 — High: camera-ID edits fabricate status and do not consistently identify captured evidence.** Saving camera IDs deletes all Device rows and recreates them as Online with a fixed resolution and current timestamp without probing hardware. Public camera listing uses the custom IDs for display, but the camera manager and startup health monitor generate `CAM-...` IDs by position. Renames do not update physical device IDs or the capture manager. UI device status, previews, saved evidence, and later health records can therefore disagree. Evidence: [config.py:68](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:68), [cameras.py:29](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:29), [camera_manager.py:213](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/camera_manager.py:213), [startup.py:199](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/core/startup.py:199).

**SCANNER-03 — Medium: remapping leaves some settings snapshots stale.** Mapping clears the settings cache and updates `camera_manager._device_ids`, but cameras.py and startup.py retain their earlier module-level settings objects. Camera listing still iterates the old device list, while capture uses the new list. The backend mapping schema only declares a list of integers; duplicate/empty/invalid hardware mappings are not validated there. Evidence: [cameras.py:14](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:14), [cameras.py:38](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:38), [cameras.py:114](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:114), [cameras.py:141](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/cameras.py:141), [startup.py:48](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/core/startup.py:48).

**Needed improvement:** Protect mapping and define preview permissions, distinguish display ID from physical device index, retain stable identity across services, and use actual probe results. Update dependent runtime settings coherently and validate mapping on the backend. The UI's round-robin wording also conflicts with the implemented parallel capture with sequential fallback: [SystemConfig.tsx:245](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:245), [camera_manager.py:281](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/camera_manager.py:281).

**Panel may ask:** Can someone change camera mapping without logging in? Why does an unplugged camera become Online after save? Is renaming a camera the same as selecting a USB device? Do labels still match physical views after remapping and reboot?

### 11. AI Settings (YOLO26)

**AI-01 — High: the saved threshold is not the YOLO inference threshold.** The slider stores `SystemConfig.confidence_threshold` as a percentage and says lower-confidence detections will be ignored/not recorded. Actual YOLO inference reads `settings.yolo_confidence_threshold`, and fusion uses its own fixed low-confidence constant. The database threshold is consumed by dashboard/review metrics, so it is not wholly unused; its effect differs from the AI settings promise. Evidence: [SystemConfig.tsx:269](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:269), [classification.py:178](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/classification.py:178), [fusion_engine.py:56](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/fusion_engine.py:56), [dashboard.py:184](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/dashboard.py:184).

**Needed improvement:** Define separate detection and review thresholds or connect the control to its intended inference consumer. Make percentage versus 0–1 units explicit and verify the actual runtime value. Coordinate inference behavior with the AI owner rather than changing thresholds blindly.

**AI-02 — Medium: model-version wording and deployment defaults disagree.** The assigned feature is YOLO26; the settings heading says YOLOv8, older READMEs say YOLOv8n, the pre-detector references `yolo26n.pt`, and the environment-selected classifier file is `banana_yolo26m.pt`. The code default points to `banana_yolov26n.pt`, which is not among the locally listed weights. Existing environment configuration may make local loading work; a fresh deployment cannot assume that override/assets exist. Evidence: [SystemConfig.tsx:272](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:272), [Settings:58](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/config.py:58), [banana_detector.py:53](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/banana_detector.py:53), [README](C:/Users/Kent/Documents/GitHub/BananaVision/README.md:1).

**AI-03 — Medium: degraded model readiness can be reported as healthy.** `/health` always returns status healthy. RFR loading sets its loaded flag true even when the model is missing or loading fails and rule-based fallback is used. Pre-detection also assumes a banana is present when its model fails. These fallback decisions are implemented, but the returned scan result does not identify the prediction mode. Evidence: [main.py:112](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/main.py:112), [spoilage.py:76](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/spoilage.py:76), [spoilage.py:99](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/spoilage.py:99), [banana_detector.py:108](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/banana_detector.py:108), [scan_service.py:309](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/scan_service.py:309).

**Evidence still needed:** Loaded-model metadata/hash, exact training class map, dataset and split provenance, measured classification and regression performance, and latency on the actual station. Presence or naming of a weight file does not establish these. Thesis PDFs and model binaries were not analyzed, so this report does not claim such evidence is absent everywhere.

**Panel may ask:** Is the custom classifier really the stated YOLO26 variant? What does moving this slider change? Can the system distinguish trained-model prediction from a fallback? How were accuracy and spoilage error measured?

### 12. Data Retention Settings

**RETENTION-01 — High: the 30-day cleanup promise is not implemented in the inspected application.** The database stores `data_retention_enabled`, and settings declare a retention-days value. Searches of application and launch-script source found no consumer that removes old scan/log records or capture files. Startup schedules sensor polling and camera monitoring only. Log-file size rotation exists in main.py, but it is a separate mechanism and does not implement the UI's age-based scan/image policy. Evidence: [SystemConfig.tsx:312](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:312), [config.py:85](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:85), [Settings:63](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/config.py:63), [startup.py:134](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/core/startup.py:134), [main.py:39](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/main.py:39). An external host cleanup job was not inspected and cannot be assumed.

**RETENTION-02 — Medium: failed scans can leave capture files without persisted scan records.** Capture files are saved before banana/model validation. The exception path reports failure and rethrows, but does not remove the files. Non-banana or inference-failed attempts can leave storage that a database-only cleanup would miss. Evidence: [scan_service.py:81](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/scan_service.py:81), [scan_service.py:110](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/scan_service.py:110), [scan_service.py:365](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/scan_service.py:365).

**RETENTION-03 — Medium: the advertised database backup is a limited CSV export.** The endpoint emits six scan-summary columns. It excludes accounts, settings, audit history, image files, per-camera evidence, and other relational data, and there is no restore operation in this flow. It cannot serve as a complete database backup. Evidence: [SystemConfig.tsx:333](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/admin/SystemConfig.tsx:333), [config.py:102](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/api/v1/config.py:102).

**Needed improvement:** Define the retained record/file types and cutoff policy, then implement scheduled enforcement with related-data handling, failure reporting, and orphan-file handling. Decide what history must remain for traceability. Clearly distinguish CSV reporting from a restorable backup. Make deletion consequences reviewable before enabling real cleanup.

**Panel may ask:** Which process deletes data after 30 days? Does disabling the setting really stop deletion? Are files and database rows both handled? Can the CSV restore the system? What happens when cleanup fails or the PC is off?

### 13. Landing Page

**LANDING-01 — Medium: the clickable logo container lacks native keyboard-button behavior.** The header logo/home action is an onClick on a div without button semantics or keyboard handling. The mobile-menu button does have an accessible text label, and desktop navigation uses buttons. Evidence: [Landing.tsx:62](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Landing.tsx:62).

**Content claims requiring evidence, not confirmed missing features:** The page calls the product enterprise-grade, promises classification in seconds, describes comprehensive scan history, and says no internet is needed. The runtime may operate offline once dependencies/assets exist, but the pre-detector load path can fetch weights when uncached. Performance, deployment readiness, and contact-mailbox ownership were not verified. The contact action is a mailto link, not an in-app support submission. Evidence: [Landing.tsx:153](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Landing.tsx:153), [Landing.tsx:178](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Landing.tsx:178), [Landing.tsx:211](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Landing.tsx:211), [Landing.tsx:306](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Landing.tsx:306), [Landing.tsx:333](C:/Users/Kent/Documents/GitHub/BananaVision/frontend/src/pages/Landing.tsx:333), [banana_detector.py:64](C:/Users/Kent/Documents/GitHub/BananaVision/backend/app/services/banana_detector.py:64).

**Needed improvement:** Make all navigation keyboard usable, qualify claims to match demonstrated behavior, document offline asset provisioning, verify the contact destination, and inspect the page on phone/tablet/desktop. Do not invent accuracy or performance figures. No visual layout defect is claimed without browser inspection.

**Panel may ask:** Who is the intended user? What evidence supports enterprise readiness or the speed claim? Can a new station start with no internet? Is this a working support address? Can all navigation be used with a keyboard?

## Problems or Inconsistencies in Documentation

| Documentation statement | Evidence from current inspection | Recommended correction |
| --- | --- | --- |
| Older root/backend READMEs and workflow summaries describe YOLOv8n. | Code references YOLO26 paths; local environment selects a YOLO26-named custom file; settings UI still says YOLOv8. | Align wording with verified loaded-model metadata and the exact deployed variant. |
| BANANAVISION_CONTEXT says model weights are absent. | Local `.pt` and `.joblib` files exist, but Git ignores them. | Distinguish source checkout contents, local assets, and deployment provisioning. |
| Workflow README describes SQLite and sequential capture. | Backend is configured for PostgreSQL/asyncpg; capture is parallel with sequential fallback. | Update obsolete architecture text. |
| Workflow documents describe isolated kiosk access. | PIN swap issues a normal account JWT, shared auth state stores it, and protected routes do not distinguish a kiosk-only scope. | Define whether kiosk isolation is a UI mode or an enforced authorization boundary; implement/document the chosen boundary. |
| Workflow documents imply working reset, retention, and complete audit features. | Reset UI calls generic PATCH; retention enforcement was not found; audit page displays an initial subset. | Treat these as unfinished until demonstrated end to end. |
| Planning docs show migrations/test modules as planned implementation. | Startup uses `create_all`; available focused suites cover dashboard/scan logs rather than a full account/configuration suite. | Keep proposed files separate from the actual implementation inventory. |

Relevant sources: [project context](C:/Users/Kent/Documents/GitHub/BananaVision/docs/BANANAVISION_CONTEXT.md:1), [backend README](C:/Users/Kent/Documents/GitHub/BananaVision/backend/README.md:1), [workflow README](C:/Users/Kent/Documents/GitHub/BananaVision/docs/bananavision-docs/docs/workflows/README.md:1), [revised workflows](C:/Users/Kent/Documents/GitHub/BananaVision/docs/bananavision-docs/docs/workflows/REVISED_PROGRAM_WORKFLOWS.md:1), [backend plan](C:/Users/Kent/Documents/GitHub/BananaVision/docs/backend_plan.md:1).

## Original Recommended Roadmap — Historical October 4 Review

1. **Close account takeover and public write paths:** AUTH-01 and SCANNER-01; then establish WebSocket access controls and a session invalidation policy.
2. **Make account operations real and reviewable:** fix creation/edit/status failure feedback, use dedicated reset endpoints, provide self-profile ownership, and reconcile role transitions/admin recovery rules.
3. **Make settings match runtime behavior:** connect or relabel AI thresholds; unify camera identity/mapping/status; validate configuration and await successful saves.
4. **Complete storage and audit promises:** define and implement retention, orphan handling, accurate history pagination/export, reset audit records, and an honest backup workflow.
5. **Prepare defense evidence:** correct outdated docs and labels, gather model/hardware results, and verify landing/profile usability and claims.

This ordering addresses security and core assigned workflows before cosmetic work. It does not add unrequested modules, public signup, a QA role, or a cloud deployment.

## Verification Checklist for Future Authorized Work

These checks are proposed only. Use isolated fixtures/test accounts and disposable data; do not demonstrate credential changes or deletion on real accounts/data.

| Area | What the panel should be able to observe after fixes |
| --- | --- |
| Login and credential changes | Wrong credentials rejected; direct unauthenticated change rejected; setup requires limited authorization; repeated guesses controlled. |
| Sessions and access | Logged-out/reset/deactivated sessions follow policy; inactive/anonymous live clients cannot access protected events; operator cannot fetch admin-only lists. |
| Create/Edit/Deactivate | Duplicate and failed requests visibly fail; no phantom account; selected creation status persists; username behavior is explicit; final admin remains recoverable. |
| Role changes | Operator-to-admin and admin-to-operator transitions produce consistent profiles, credentials, access, and historical ownership. |
| Reset Password/PIN | Correct reset endpoint used; old credential rejected; replacement required; audit records actor/target/outcome; existing tokens follow the reset policy. |
| Profile | Operator/avatar changes persist across fresh login; wrong current password rejected; activity matches account ID; lifetime metrics exceed one page correctly. |
| Activity Logs | Older matching entries are searchable; filters and pagination use server data; complete intended export; CSV handles embedded quotes. |
| System Configuration | Invalid values rejected; offline save fails clearly; successful values survive reload; application timing and power-command outcomes are explicit. |
| Scanner | Unauthenticated mapping denied; one physical camera per selected position; disconnected devices stay Offline; IDs match evidence and health after remapping/reboot. |
| AI settings | Measured runtime threshold follows its defined purpose; model variant/assets verified; degraded mode visible; no unsupported accuracy claim. |
| Retention | Fixtures around the cutoff behave correctly; disabling prevents cleanup; linked files/records and orphans handled; failed/missed runs observable. |
| Landing | Navigation and login links work by keyboard and touch; layout checked at common screen sizes; contact and offline/performance claims supported. |

## Defense Notes

Explain each feature as **UI action → API endpoint → authorization/validation → database or hardware effect → displayed result**. Show evidence of the backend effect, not only a toast message. Keep answers honest: source exists does not mean a live workflow has passed; a model filename does not establish architecture/accuracy; storing a retention flag does not establish deletion; and exporting scan summaries does not establish backup/restore.

The strongest panel preparation is to resolve the critical/high findings, demonstrate failed as well as successful requests, and clearly identify any remaining limitation. The original review was delivered without implementation changes. The October 5 status update and changelog supersede this historical implementation status.
