# BananaVision functionality and user-role review

Review date: **2026-11-02**. Checkout: `main`, `1848ac0`.

This is a source-based follow-up to the [pre-defense audit](../../Capstone_Pre_Defense_Audit_Report.md), focused on missing functionality, users, and the owner's proposed way to contact the inventors about IoT problems. The user clarified that intended clients are medium businesses that may own many stations in different locations. The product assessment therefore prioritizes multiple companies, each with multiple stations. It proposes priorities; it does not implement features or establish that this architecture is part of the approved capstone scope. The review before this clarification is [archived](../history/2026-11-02-functionality-review-before-multi-station-clarification.md).

## Finding

**The concern is valid: BananaVision lacks an integrated owner-to-provider support workflow. A Super Admin role alone would not provide that workflow.**

Only Admin and Operator are supported account roles. The public landing page's Contact Support Team button opens `mailto:support@bananavision.com`. No implemented ticket submission, provider inbox, support conversation, acknowledgement, assignment or resolution lifecycle was found in the frontend routes/API client or backend route/model registries. The email address's operation and delivery were not verified.

Evidence: `backend/app/schemas/enums.py:18`; `frontend/src/types/index.ts:20`; `frontend/src/pages/Landing.tsx:322`; `frontend/src/App.tsx:63`; `frontend/src/lib/api.ts:124`; `backend/app/api/v1/router.py:9`; `backend/app/models/__init__.py:5`.

**For the clarified product target, company-wide management, station-scoped access and provider support are substantive gaps.** Admin and Operator can cover one local station, but the examined implementation does not establish one company owner overseeing several locations, staff restricted to assigned stations, or the inventor team receiving and managing issues across customers. Adding role names alone cannot establish these capabilities.

No review can guarantee that panelists will have no questions. The useful target is a complete explanation of the approved scope, demonstrable workflows, failure behavior and disclosed limitations. The approved manuscript/objectives and final slides remain unavailable, so full requirements coverage cannot yet be certified.

## Functionality already present

These capabilities should not be presented as missing. Source presence does not certify their live deployment or research accuracy.

| Area | Implemented capability | Source evidence |
|---|---|---|
| Accounts and authorization | Admin/Operator accounts, backend role checks, temporary credentials, password/PIN changes and Admin resets; protection against removing the last active Admin | `backend/app/api/deps.py:66`; `backend/app/api/v1/users.py:62`, `:198`, `:291`, `:321` |
| Inspection | Kiosk operator/PIN selection, active intake selection, scan progress, results and printing | `frontend/src/pages/Kiosk.tsx:70`, `:173`, `:560`, `:790`; `backend/app/api/v1/scans.py:69` |
| Traceable records and QC | Saved scans/evidence, notes, flags, Admin corrections with reasons, original fused AI comparison and event history | `frontend/src/pages/admin/QualityControl.tsx:173`, `:806`, `:863`; `frontend/src/pages/ScanDetail.tsx:1001` |
| Operations and inventory | Suppliers, delivery intakes, stock views, Sold/For Processing/Spoiled transitions, intake bulk changes, filtered logs, analytics and report exports | `frontend/src/App.tsx:72`; `frontend/src/pages/ScanDetail.tsx:76`, `:323`; `frontend/src/pages/admin/DeliveryIntake.tsx:159`; [export notes](../knowledge/Frontend.md#csv-and-xlsx-exports-2026-10-22) |
| Device visibility | Camera monitoring, feed mapping/preview, sensor Live/Stale/Offline display and host CPU/memory/disk/uptime | `backend/app/core/startup.py:239`; `frontend/src/pages/DeviceStatus.tsx:130`, `:369`; `backend/app/api/v1/system.py:130` |
| Printer handling | Discovery, saved job state, failure messages and guarded retries | `backend/app/api/v1/printing.py:36`; `backend/app/services/print_jobs.py:69` |
| Station maintenance | Admin backups, archive validation, restore/recovery, retention and guarded power actions | `backend/app/api/v1/maintenance.py:82`, `:171`; `frontend/src/pages/admin/SystemConfig.tsx:287`, `:412`, `:495` |
| Notifications and connection recovery | Station notifications with per-user read state; browser WebSocket reconnection and refresh | `backend/app/api/v1/notifications.py:44`; `backend/app/services/scan_service.py:345`; `frontend/src/hooks/useWebSocket.ts:68` |
| Public audience | A public scan-summary route without a buyer login | `frontend/src/App.tsx:70`; `backend/app/api/v1/scans.py:178` |

A QC flag concerns a banana inspection. A maintenance ticket concerns a station problem. Existing flags, audit logs, backups and notification read receipts do not replace a support request and resolution history.

## Which users are justified?

The following is a recommended responsibility model, **not the current implemented permission matrix**.

| User/actor | Responsibility | Recommendation |
|---|---|---|
| Operator | Perform inspections, view permitted records, flag uncertain results and report faults at assigned stations | Keep existing own-record restrictions unless broader access is approved; decide whether fault reports go first to the owner or directly to support |
| Company Owner / Company Admin | Manage their company's stations and staff; view company-wide reports and issues | Add company-wide scope for the clarified target; this does not grant access to another customer |
| Station Admin / Manager | Manage operations, QC, staff assignments and permitted maintenance at assigned stations | Make station scope explicit; a separate role is useful when duties differ from the company owner. One manager may cover several assigned stations |
| Provider Support / inventor team | Receive assigned customer issues, inspect approved diagnostics, reply and record resolutions | Add the support responsibility for the intended product; a small inventor team may initially combine it with platform administration |
| Platform / Super Admin | Register companies/stations, manage provider staff and oversee the central management service | Justified for central administration of the clarified product. Keep provider authority distinct from company ownership and restrict customer-data/maintenance access explicitly |
| Buyer / consumer | View the deliberately public produce summary | Existing public access may be enough; an account is unnecessary unless private buyer actions are required |
| Supplier | Be identified as the delivery source | Existing supplier records may be enough; a supplier login needs an actual self-service requirement |

Being the inventor does not itself require unrestricted access to every customer's business data or power/restore controls. Provider access should be explicit, limited and audited. This follows [OWASP's authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) on least privilege, default denial and checking permissions on each request.

There is currently no verified customer/station ownership boundary for central administration: Admin reads cover this installation, and the account/device models do not identify a customer tenant. Multiple separately installed stations can still each operate locally; that is different from one service safely administering all customers. A central service needs an explicit isolation design, using separate installations or another verified boundary; see [OWASP's multi-tenant guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html).

Evidence: `backend/app/models/user_account.py:21`; `backend/app/models/device.py:21`; `backend/app/models/system_config.py:19`; `backend/app/api/v1/users.py:47`; `backend/app/services/scan_records.py:49`. The existing station-ownership lock in `backend/app/services/maintenance_database.py:25` controls the hardware-owning backend process; it is not customer ownership.

Extending the role model requires coordinated role definitions and seed data, API, record scope, WebSocket and UI permission changes. The role-name column already accepts a string, so a new role does not inherently require a schema migration. Company/station ownership introduces additional persistence requirements. Both the current API Admin dependency and frontend guards compare the exact Admin role: `backend/app/api/deps.py:66`; `frontend/src/App.tsx:47`; `frontend/src/components/AppSidebar.tsx:38`.

## Clarified target: one company, several station locations

The minimum ownership structure is **Company -> Stations (with their locations) -> Devices**. A separate location/branch entity is justified only if one location groups multiple stations or has its own management rules. An account's company membership and station assignments define where its role applies; a new role is not needed for each location.

For example, Company A owns Station A1 in Cebu and Station A2 in Davao. Its owner can compare both stations and manage that company's staff. A manager assigned only to A1 cannot use an identifier or station selector to access A2. Company B's staff cannot access either station. The provider can see registered station health and submitted support cases under explicit permissions; access to detailed scans, captures, account resets or destructive maintenance needs its own authorization.

| Necessary capability for the clarified target | Minimum behavior | Current review result |
|---|---|---|
| Company and station registration | Stable company/station IDs, authenticated registration, location, ownership and registration/deactivation history | No such central ownership model found; existing Device rows represent station hardware |
| Company and station permissions | Company owner sees their stations; managers/operators see assigned stations; company and station scope checked on every protected access path | Current Admin/Operator rules apply within an installation, not a verified central company/station boundary |
| Station context and configuration | Identify the active station and keep camera, sensor, model and maintenance settings within its authorized scope | Configuration currently applies to the local installation; central station selection/configuration was not found |
| Company-wide dashboard | Filter and aggregate stock, activity, quality and status by authorized station; show data age and last synchronization | Current dashboard/analytics cover the installation; central aggregation was not found |
| Central support and station health | Report ties to company, station and affected device; provider and owner see replies/history; last-contact state is explicit | Local health/status and scan notifications exist; central support/heartbeat delivery was not found |
| Local operation and reliable synchronization | Keep inspection at the station; define behavior when the central service is unreachable; retry queued deliveries without duplicate records and label delayed totals | Local processing is already the basis; a durable central synchronization workflow was not found. Actual disconnected operation still needs testing |
| Station-aware audit and recovery | Record actor, company/station and time; prevent restore or recovery actions from crossing station/company boundaries | Local audit and station recovery exist; equivalent central boundaries have not been implemented or verified |

Multiple standalone copies of the present app may each serve a station, but that alone does not provide shared company management, employee assignments or combined reporting. Central management needs a reachable service and an identity/data synchronization contract. That service may be hosted centrally by the customer or provider; public-cloud hosting and a shared database are not selected by this review.

Synchronize only the information required for the approved central functions; uploading every raw capture is not an automatic requirement. Define record identifiers, source station, delivery retry/deduplication, conflict handling, version compatibility and last-sync indicators before implementing aggregation. Continue using the existing backend time helpers; do not introduce a competing timezone policy.

This is a meaningful architecture addition beyond the current local-station implementation. A staged path is: establish company/station ownership and access boundaries; implement central support and station health; then add the required reporting synchronization. Local inspection and approved current behavior should remain stable while each stage is verified. The actual capstone deliverable still depends on the approved objectives and timeline.

## Confirmed gaps and priorities

| Gap | Verified behavior | Priority and practical response |
|---|---|---|
| **G01. Integrated issue reporting** | Only an external email contact; no report/reply/resolution flow or provider receipt | Essential if in-product provider support is promised. Build a complete support flow rather than only a new role |
| **G02. Company/station management and remote delivery** | Local scan notifications exist; no central company/station ownership, assignment, aggregation or provider dispatch boundary was found | A core gap for the clarified target. Define company/station identities, scoped permissions, a reachable central service and reliable delivery; use the multi-station capability table above |
| **G03. Sole-Admin credential recovery** | Reset requires an authenticated Admin; last-Admin protection prevents demotion/deactivation, not forgotten credentials; startup bootstrap stops if accounts already exist | Establish an owner-verified, audited recovery procedure before handover. A verified recovery process may be sufficient; a generic password-reset screen is not the only option |
| **G04. Hardware fault lifecycle and sensor recovery** | Camera changes broadcast locally; sensor warnings appear locally; no provider escalation or persistent maintenance-case workflow was found. Serial connection is attempted at startup, with no reconnect workflow found | Define unplug/startup-failure recovery and which faults become incidents. Do not claim that inventors automatically receive device failures |
| **G05. Trustworthy prediction inputs and mode** | Scans use cached sensor data without freshness/connection checks. Missing inputs become internal defaults; model failure can use rules while the loaded flag remains true | Correct or explicitly disclose before presenting sensor-informed RFR predictions as verified. This is a current core-behavior issue, not a new commercial feature |
| **G06. Physical stock identity and re-inspection** | Stock counts eligible scan rows. Each newly created scan starts In Stock; the request has no existing physical-bunch identity | Define one physical unit/one stock entry and how re-inspection links to it if accurate inventory or repeated monitoring is claimed. An intake groups deliveries but does not identify each physical bunch |
| **G07. Meaning of Accept and Flag** | Accept records local acknowledgement after the scan was already saved In Stock; Flag requests QC | Explain this behavior. If approval-before-stock or quarantine is required, add an explicit persisted workflow under an approved requirement |
| **G08. Printed-label/public-tracking contract** | Printed QR contains saved-value text; a separate screen QR uses a tracking URL. Public summary image URLs point to protected evidence routes | Align implementation or claims and rehearse the actual phone/label flow. A public tracking route alone does not establish physical-label tracking |
| **G09. Research and evidence integrity** | Independent current-pipeline/shelf-life validation is missing; saved camera cultivar labels can be harmonized to consensus | Resolve or disclose the earlier audit's F01/F04 findings. More roles cannot establish model accuracy or recover raw decisions that were not retained |

Additional evidence:

- G03: `backend/app/api/v1/users.py:198`, `:291`; `backend/app/core/startup.py:326`; `frontend/src/pages/Login.tsx:74`.
- G04: `backend/app/core/startup.py:156`, `:301`; `backend/app/services/sensor_reader.py:59`, `:84`, `:130`; `frontend/src/pages/DeviceStatus.tsx:369`.
- G05: `backend/app/services/scan_service.py:263`; `backend/app/services/sensor_reader.py:108`; `backend/app/services/spoilage.py:152`, `:168`, `:191`.
- G06: `backend/app/models/scan.py:20`; `backend/app/services/scan_creation.py:23`; `frontend/src/context/ScanContext.tsx:313`; `frontend/src/pages/Inventory.tsx:38`.
- G07: `frontend/src/pages/Kiosk.tsx:818`, `:836`; `backend/app/services/scan_creation.py:45`.
- G08/G09: [pre-defense audit findings F01, F04, F05 and F15](../../Capstone_Pre_Defense_Audit_Report.md); `backend/app/services/prediction_label.py:34`; `backend/app/api/v1/scans.py:178`; `backend/app/services/scan_service.py:235`.

The existing Camera Calibration screen maps feeds to physical positions. It does not prove measured optical/sensor calibration. A calibration procedure and evidence are needed for measurement claims; a large calibration-management module is not automatically required. Evidence: `frontend/src/components/CameraCalibrationModal.tsx:112`; `backend/app/api/v1/cameras.py:153`.

## Minimum useful in-product support flow

For the intended supported multi-station product, the smallest complete support workflow is:

1. **Report:** Owner or permitted station staff submits category/component, description and impact, with company/station identity, application version, occurrence time and optionally selected diagnostics. The server validates the submitter's company/station permissions.
2. **Save and deliver:** Persist a report ID. Display Saved locally / Pending delivery / Received separately. Retry safely without duplicate tickets when connectivity returns.
3. **Acknowledge:** Provider support sees the issue and acknowledges receipt. Delivery to the service and acknowledgement by a person are different events.
4. **Investigate:** Owner and assigned support exchange updates; show status, assignee and dated history. Share only selected, sanitized diagnostic material, not secrets or unrestricted station backups.
5. **Resolve:** Support records the cause/action and proposed resolution; owner confirms closure or reopens the case. Preserve the history.

Suggested case states: **Submitted -> Acknowledged -> In progress -> Resolved -> Closed**, with reopening. Delivery state remains separate from case state. Use the existing backend Asia/Manila timestamp helpers for business times.

Receiving issues remotely requires a network path and provider-side service. A report saved only in the local station database cannot notify inventors elsewhere. If internet is down, show it as pending. If the station server or power is completely down, that same station application cannot submit anything: a separately reachable BananaVision support portal or an agreed fallback remains necessary. A missed central heartbeat can indicate lost contact, but cannot by itself prove whether the cause was power or network loss.

Reporting a fault and authorizing remote repair are separate decisions. Remote control need not be part of the initial ticket feature. Any later access should have a defined scope, expiry and audit trail, especially for restore, account changes and OS power.

This proposed process is a project recommendation, not a declaration of standards compliance. [NIST IR 8259B](https://csrc.nist.gov/pubs/ir/8259/b/final) supports considering manufacturer/third-party support capabilities for IoT cybersecurity; it does not make a Super Admin title or a full help desk mandatory for every capstone.

## Completion evidence for any future support implementation

These are proposed acceptance scenarios; **they have not been executed and no support feature was built by this review**.

- A permitted owner submits a fault and can find the same report after refresh/restart.
- A provider receives it, replies and changes status; the correct owner sees the update and closure history.
- Another customer cannot access the report, attachments or updates by changing an identifier.
- The company owner can oversee their stations; a manager/operator assigned only to one station cannot access an unassigned station through reports, API calls, files, exports or WebSockets.
- Company-wide totals disclose each station's last synchronization and do not count retried deliveries as new inspections.
- An unauthorized user cannot grant provider access, assign roles or invoke maintenance through the support flow.
- Losing connectivity preserves an honestly marked pending report; recovery delivers once despite retries.
- Diagnostics exclude credentials and follow bounded, authorized file handling; attachments cannot expose unrelated files.
- Station/backend downtime has a demonstrated alternative contact route, with no false claim of successful delivery.
- Separately, exercise sole-Admin recovery and sensor disconnect/recovery using isolated fixtures or an authorized human rehearsal.

## How to defend the current scope

Use answers that describe current behavior, then clearly identify proposed work:

| Likely panel question | Defensible answer today |
|---|---|
| Why are there only two roles? | The current implementation covers a local station with Admin and Operator. Our intended customers may own several stations, so company-level ownership, station assignments and provider support are identified additions; they are not currently implemented |
| Can one owner manage several locations today? | Independent installations can serve separate stations, but verified central company management, consolidated reporting and station assignments are not implemented |
| How does the owner tell the inventors about a fault? | The current interface opens external email. Integrated reporting, replies and resolution tracking are a confirmed gap; we should not claim they already exist |
| Why not give the inventors unlimited Super Admin access? | Support can work from submitted issues and approved diagnostics. Broad customer-data and maintenance access needs a separate, explicit permission boundary |
| Will inventors be informed when internet or station power fails? | Current local alerts do not establish remote delivery. A future service needs pending-delivery handling and a separately reachable fallback; total power loss cannot send a report from the failed station |
| What if the only Admin forgets the password? | Admin-assisted resets and last-Admin protection exist, but an owner-verified recovery procedure still needs to be established |
| Are these all the missing requirements? | This is a verified code/workflow gap review. Final completeness requires comparison with the approved objectives and scope, current model evaluation and a dated hardware/UAT rehearsal |

For the capstone, prioritize existing core defects, honest prediction/stock/QR behavior, a recovery procedure and claim-to-evidence alignment. Compare company/station management and integrated support with the approved deliverables before selecting implementation stages. For the clarified commercial target, these are substantive product needs alongside delivery reliability and maintenance history. Version inventory and a tested update/rollback/support-lifetime policy also need a deployment review; their absence was not established by this focused application review.

## Verification and limits

- Reviewed frontend routes/types/pages/API clients, backend authorization/routes/models/services, relevant local knowledge notes and the earlier audit. Three independent focused reviews covered roles/support, frontend workflows and IoT operations. A follow-up independent role review checked the company/station responsibilities against the user's deployment clarification.
- Initial working tree was clean on `main`. `git diff --name-only 0964ea9 HEAD` listed only prior review/progress/prompt/history documents, confirming that the application source matches the earlier audit's source checkpoint.
- **No new runtime tests, type checks, lint or build were run:** this change adds review documentation only. Earlier audit results remain historical evidence: backend 680 passed / 1 skipped / 1 warning; frontend 266 passed; production build passed. Existing frontend lint had 35 errors / 5 warnings and Ruff had 627 findings. Those suites do not validate the proposed support feature or real-world model accuracy.
- No live station database, captures, physical cameras/sensor/printer, secrets or OS power were accessed. Actual deployment, external mailbox, remote connectivity, calibration and hardware recovery remain unverified.
- Graphify graph/CLI and ICM tools were unavailable. Relevant local Obsidian notes were consulted and checked against source. No tools were installed and no integration configuration was changed. No graph refresh or persistent-memory write is claimed.
- This artifact and the current progress checkpoint are documentation changes. No application/schema changes, staging, commits, pushes, branch/worktree changes, deployment or live maintenance were performed.

**Next decision:** compare the approved manuscript with the clarified multi-company/multi-station target, then choose a bounded implementation stage and central hosting/data model. The deployment target is now clarified; the implementation architecture and capstone scope remain unapproved. Do not treat this report's recommendations as completed functionality.
