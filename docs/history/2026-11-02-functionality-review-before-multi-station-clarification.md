# BananaVision functionality and user-role review

Review date: **2026-11-02**. Checkout: `main`, `1848ac0`.

This is a source-based follow-up to the [pre-defense audit](../Capstone_Pre_Defense_Audit_Report.md), focused on missing functionality, users, and the owner's proposed way to contact the inventors about IoT problems. It proposes priorities; it does not implement features or expand the approved research scope. Deployment intent was not confirmed during the review, so the conclusions distinguish a standalone capstone station from a supported multi-customer product.

## Finding

**The concern is valid: BananaVision lacks an integrated owner-to-provider support workflow. A Super Admin role alone would not provide that workflow.**

Only Admin and Operator are supported account roles. The public landing page's Contact Support Team button opens `mailto:support@bananavision.com`. No implemented ticket submission, provider inbox, support conversation, acknowledgement, assignment or resolution lifecycle was found in the frontend routes/API client or backend route/model registries. The email address's operation and delivery were not verified.

Evidence: `backend/app/schemas/enums.py:18`; `frontend/src/types/index.ts:20`; `frontend/src/pages/Landing.tsx:322`; `frontend/src/App.tsx:63`; `frontend/src/lib/api.ts:124`; `backend/app/api/v1/router.py:9`; `backend/app/models/__init__.py:5`.

Admin and Operator can be adequate for one local station if they cover its approved responsibilities. If the product promises that the inventors receive customer issues inside BananaVision, provider support, network delivery and a support process are real missing capabilities. The number of role names is not a measure of completeness.

No review can guarantee that panelists will have no questions. The useful target is a complete explanation of the approved scope, demonstrable workflows, failure behavior and disclosed limitations. The approved manuscript/objectives and final slides remain unavailable, so full requirements coverage cannot yet be certified.

## Functionality already present

These capabilities should not be presented as missing. Source presence does not certify their live deployment or research accuracy.

| Area | Implemented capability | Source evidence |
|---|---|---|
| Accounts and authorization | Admin/Operator accounts, backend role checks, temporary credentials, password/PIN changes and Admin resets; protection against removing the last active Admin | `backend/app/api/deps.py:66`; `backend/app/api/v1/users.py:62`, `:198`, `:291`, `:321` |
| Inspection | Kiosk operator/PIN selection, active intake selection, scan progress, results and printing | `frontend/src/pages/Kiosk.tsx:70`, `:173`, `:560`, `:790`; `backend/app/api/v1/scans.py:69` |
| Traceable records and QC | Saved scans/evidence, notes, flags, Admin corrections with reasons, original fused AI comparison and event history | `frontend/src/pages/admin/QualityControl.tsx:173`, `:806`, `:863`; `frontend/src/pages/ScanDetail.tsx:1001` |
| Operations and inventory | Suppliers, delivery intakes, stock views, Sold/For Processing/Spoiled transitions, intake bulk changes, filtered logs, analytics and report exports | `frontend/src/App.tsx:72`; `frontend/src/pages/ScanDetail.tsx:76`, `:323`; `frontend/src/pages/admin/DeliveryIntake.tsx:159`; [export notes](knowledge/Frontend.md#csv-and-xlsx-exports-2026-10-22) |
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
| Operator | Perform inspections, view permitted records, flag uncertain results and report faults | Keep the existing role; decide whether fault reports go first to the owner or directly to support |
| Owner / station Admin | Manage their installation and staff, review quality, control maintenance, submit issues and authorize diagnostic sharing | Keep Admin for a standalone station; document who represents the owner |
| Provider Support / inventor team | Receive assigned customer issues, inspect approved diagnostics, reply and record resolutions | Add when integrated provider support is included; scope access to the support responsibility |
| Platform / Super Admin | Register customer stations, manage provider staff and oversee a central service | Add only if a central multi-customer platform is approved; it is not a mandatory capstone role |
| Buyer / consumer | View the deliberately public produce summary | Existing public access may be enough; an account is unnecessary unless private buyer actions are required |
| Supplier | Be identified as the delivery source | Existing supplier records may be enough; a supplier login needs an actual self-service requirement |

Being the inventor does not itself require unrestricted access to every customer's business data or power/restore controls. Provider access should be explicit, limited and audited. This follows [OWASP's authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) on least privilege, default denial and checking permissions on each request.

There is currently no verified customer/station ownership boundary for central administration: Admin reads cover this installation, and the account/device models do not identify a customer tenant. Multiple separately installed stations can still each operate locally; that is different from one service safely administering all customers. A central service needs an explicit isolation design, using separate installations or another verified boundary; see [OWASP's multi-tenant guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html).

Evidence: `backend/app/models/user_account.py:21`; `backend/app/models/device.py:21`; `backend/app/models/system_config.py:19`; `backend/app/api/v1/users.py:47`; `backend/app/services/scan_records.py:49`. The existing station-ownership lock in `backend/app/services/maintenance_database.py:25` controls the hardware-owning backend process; it is not customer ownership.

Adding a third role requires coordinated role definitions and seed data, API, record scope, WebSocket and UI permission changes. The role-name column already accepts a string, so a new role does not inherently require a schema migration. Both the current API Admin dependency and frontend guards compare the exact Admin role: `backend/app/api/deps.py:66`; `frontend/src/App.tsx:47`; `frontend/src/components/AppSidebar.tsx:38`.

## Confirmed gaps and priorities

| Gap | Verified behavior | Priority and practical response |
|---|---|---|
| **G01. Integrated issue reporting** | Only an external email contact; no report/reply/resolution flow or provider receipt | Essential if in-product provider support is promised. Build a complete support flow rather than only a new role |
| **G02. Remote delivery and station identity** | Local scan notifications exist; no central provider dispatch/registered customer-station boundary was found | Essential for support across installations. Define the reachable provider service, station identity, delivery acknowledgement and customer isolation |
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
- G08/G09: [pre-defense audit findings F01, F04, F05 and F15](../Capstone_Pre_Defense_Audit_Report.md); `backend/app/services/prediction_label.py:34`; `backend/app/api/v1/scans.py:178`; `backend/app/services/scan_service.py:235`.

The existing Camera Calibration screen maps feeds to physical positions. It does not prove measured optical/sensor calibration. A calibration procedure and evidence are needed for measurement claims; a large calibration-management module is not automatically required. Evidence: `frontend/src/components/CameraCalibrationModal.tsx:112`; `backend/app/api/v1/cameras.py:153`.

## Minimum useful in-product support flow

If integrated support is selected, the smallest complete workflow is:

1. **Report:** Owner submits category/component, description and impact, with station identity, application version, occurrence time and optionally selected diagnostics. Operator reporting follows a defined permission policy.
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
- An unauthorized user cannot grant provider access, assign roles or invoke maintenance through the support flow.
- Losing connectivity preserves an honestly marked pending report; recovery delivers once despite retries.
- Diagnostics exclude credentials and follow bounded, authorized file handling; attachments cannot expose unrelated files.
- Station/backend downtime has a demonstrated alternative contact route, with no false claim of successful delivery.
- Separately, exercise sole-Admin recovery and sensor disconnect/recovery using isolated fixtures or an authorized human rehearsal.

## How to defend the current scope

Use answers that describe current behavior, then clearly identify proposed work:

| Likely panel question | Defensible answer today |
|---|---|
| Why are there only two roles? | Admin manages this station and Operator performs inspections. Roles follow distinct responsibilities. A provider support responsibility is proposed for ongoing external support; it is not currently implemented |
| How does the owner tell the inventors about a fault? | The current interface opens external email. Integrated reporting, replies and resolution tracking are a confirmed gap; we should not claim they already exist |
| Why not give the inventors unlimited Super Admin access? | Support can work from submitted issues and approved diagnostics. Broad customer-data and maintenance access needs a separate, explicit permission boundary |
| Will inventors be informed when internet or station power fails? | Current local alerts do not establish remote delivery. A future service needs pending-delivery handling and a separately reachable fallback; total power loss cannot send a report from the failed station |
| What if the only Admin forgets the password? | Admin-assisted resets and last-Admin protection exist, but an owner-verified recovery procedure still needs to be established |
| Are these all the missing requirements? | This is a verified code/workflow gap review. Final completeness requires comparison with the approved objectives and scope, current model evaluation and a dated hardware/UAT rehearsal |

For the capstone, prioritize existing core defects, honest prediction/stock/QR behavior, a recovery procedure and claim-to-evidence alignment. Add a small complete support workflow if it is an approved deliverable. For a commercial product, additionally define provider support, station registration/isolation, delivery reliability and maintenance history. Version inventory and a tested update/rollback/support-lifetime policy also need a deployment review; their absence was not established by this focused application review.

## Verification and limits

- Reviewed frontend routes/types/pages/API clients, backend authorization/routes/models/services, relevant local knowledge notes and the earlier audit. Three independent focused reviews covered roles/support, frontend workflows and IoT operations.
- Initial working tree was clean on `main`. `git diff --name-only 0964ea9 HEAD` listed only prior review/progress/prompt/history documents, confirming that the application source matches the earlier audit's source checkpoint.
- **No new runtime tests, type checks, lint or build were run:** this change adds review documentation only. Earlier audit results remain historical evidence: backend 680 passed / 1 skipped / 1 warning; frontend 266 passed; production build passed. Existing frontend lint had 35 errors / 5 warnings and Ruff had 627 findings. Those suites do not validate the proposed support feature or real-world model accuracy.
- No live station database, captures, physical cameras/sensor/printer, secrets or OS power were accessed. Actual deployment, external mailbox, remote connectivity, calibration and hardware recovery remain unverified.
- Graphify graph/CLI and ICM tools were unavailable. Relevant local Obsidian notes were consulted and checked against source. No tools were installed and no integration configuration was changed. No graph refresh or persistent-memory write is claimed.
- This artifact and the current progress checkpoint are documentation changes. No application/schema changes, staging, commits, pushes, branch/worktree changes, deployment or live maintenance were performed.

**Next decision:** compare the approved manuscript with this review, then choose the intended deployment and a bounded implementation scope. Do not treat this report's recommendations as completed functionality.
