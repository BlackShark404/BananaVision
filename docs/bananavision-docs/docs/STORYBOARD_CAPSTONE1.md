# Storyboard

A storyboard is a sequence of visual frames used to illustrate how users interact with a system over time. It presents key screens, actions, and transitions to communicate the flow of tasks and the expected system responses.

## BananaVision Storyboard (Quality & Shelf-Life Dashboard and Mini PC Kiosk)

These figures map directly to the implemented interfaces and application routes across the BananaVision platform. The storyboard is organized into four interconnected deployment domains: the Public Web Portal & Traceability featuring the landing page and unauthenticated QR-code batch tracking portal (`/track/:scanId`); the Operator Web Dashboard providing role-scoped shift monitoring, scan logs, FIFO inventory management, analytics, and device status; the Dedicated Mini PC Kiosk providing an isolated, touch-first edge scanning terminal for physical post-harvest inspection, multi-camera capture, 4-stage AI classification, and automated thermal label printing; and the Administrator Web Dashboard delivering comprehensive operational governance, user credential handoff, delivery intake batch management, quality control review and overrides, activity audit logs, and station configuration.

---

## Figure 35: Landing Page - Hero Section (Web)

Figure 35: Illustrates the hero section of the public-facing landing page, introducing BananaVision as an AI-powered banana classification and shelf-life estimation system built for medium and large enterprises. The section features a modern glassmorphic hero banner, the system tagline ("Smarter Classification with BananaVision"), a concise value proposition, and primary call-to-action buttons for accessing the dashboard or learning more.

- Route: `/`
- User Type: Public
- Main Actions: Navigate to login (`/login`), smooth-scroll to explore system capabilities (`/#about`)

---

## Figure 36: Landing Page - About Section (Web)

Figure 36: Shows the About BananaVision section, describing the system's operational mission and industrial scope. It highlights how the platform combines multi-angle computer vision and ambient environmental sensing to identify banana cultivars (Lakatan, Latundan, Cardaba), determine ripeness stages (Unripe, Semi Ripe, Ripe, Overripe), and estimate remaining shelf life. The section outlines support for medium and large enterprises in the banana supply chain, including retail grocery chains, banana processing and chip manufacturing facilities, and commercial wholesale distributors.

- Route: `/#about`
- User Type: Public
- Main Actions: Read system mission, understand supply-chain application

---

## Figure 37: Landing Page - Key Features Section (Web)

Figure 37: Displays the Key Features grid highlighting the six core functional capabilities of the system. The presentation outlines AI-assisted scanning for identifying commercial Philippine banana cultivars (Lakatan, Latundan, Cardaba), determining ripeness stages, counting bunch fingers, and calculating shelf life using microclimate telemetry; the touch-friendly operator kiosk for rapid multi-camera batch scanning; scan review mechanisms that automatically flag low-confidence or conflicting classifications for administrative oversight; real-time inventory tracking with First-In, First-Out (FIFO) handling guidance and 2-day spoilage warnings; interactive analytics reports and charts illustrating throughput trends and worker performance; and a complete, searchable scan history providing an exportable audit trail of every inspection record.

- Route: `/#features`
- User Type: Public
- Main Actions: Review core functional highlights

---

## Figure 38: Landing Page - System Modules Section (Web)

Figure 38: Shows the System Modules section, presenting the three role-tailored application environments across numbered cards. The section details the Operator Kiosk deployed on the edge terminal for PIN-authenticated scanning, multi-angle camera previewing, intake batch and ripening treatment assignment, result validation, and thermal label printing; the Operator Dashboard providing a role-scoped web view of personal shift throughput KPIs, individual scan history, performance analytics, FIFO inventory health, and camera and sensor status; and the Admin Dashboard delivering enterprise-wide operational oversight, user account administration with temporary credential handoff, delivery intake batch management, supplier registration, quality control review queues, activity audit logs, and station hardware configuration with power controls.

- Route: `/#modules`
- User Type: Public
- Main Actions: Understand role-based system structure and access boundaries

---

## Figure 39: Landing Page - FAQs Section (Web)

Figure 39: Displays the Frequently Asked Questions section utilizing an interactive accordion interface to clarify system deployment. The questions address the target market of medium and large agricultural enterprises handling banana packaging, ripening, processing, and wholesale distribution; the offline network capability allowing the entire platform to operate autonomously on a local edge Mini PC over local LAN or Wi-Fi hotspot without requiring an active internet connection; and the physical hardware architecture consisting of an x86_64 Mini PC connected to a 4-camera USB webcam array, an Arduino Uno DHT22 temperature and humidity sensor module, a Grozziie TP870 S USB thermal label printer, and an external kiosk display monitor.

- Route: `/#faqs`
- User Type: Public
- Main Actions: Expand/collapse FAQ accordion items

---

## Figure 40: Landing Page - Contact Support Section (Web)

Figure 40: Shows the Contact Support section featuring a direct communication channel for enterprise inquiries. Provides an action button linking directly to the technical support team via email (`mailto:support@bananavision.com`) for station deployment, hardware setup assistance, and business inquiries.

- Route: `/#contact`
- User Type: Public
- Main Actions: Contact technical support team via email

---

## Figure 41: Login Page (Web)

Figure 41: Depicts the centralized authentication portal, requiring users to submit valid username and password credentials. Features password visibility toggling and client-side form validation. Upon successful authentication, the system evaluates the user's role and redirects them to either the Operator Dashboard or Admin Dashboard.

- Route: `/login`
- User Type: Public / Unauthenticated Staff
- Main Actions: Sign in with credentials, toggle password visibility, trigger authentication

---

## Figure 42: First Login Password Change for Newly Created Account

Figure 42: Shows the mandatory security modal presented immediately upon first sign-in for newly registered accounts created with temporary credentials (`new_account`). The user is prevented from navigating the system until they establish and confirm a new, permanent password meeting security complexity requirements.

- Route: `/login` (mandatory modal prompt)
- User Type: Newly Onboarded Operator / Admin
- Main Actions: Enter new permanent password, confirm password, establish account security

---

## Figure 43: First Login Password Change after Password Reset

Figure 43: Shows the forced password update interface presented to existing users whose credentials were reset by an administrator (`password_reset`). The user must replace the administrator-issued temporary password with a new permanent password before gaining dashboard access.

- Route: `/login` (mandatory modal prompt)
- User Type: Operator / Admin
- Main Actions: Enter new permanent password, confirm password, regain account access

---

## Figure 44: Dashboard (Operator View)

Figure 44: Shows the operator dashboard tailored for daily shift monitoring. Displays operator-scoped KPIs (personal scan count, active delivery sources, average detection confidence), shortcuts to operational modules, a feed of recent personal scans, and real-time operational alerts received via WebSockets.

- Route: `/dashboard`
- User Type: Operator
- Main Actions: Review shift throughput, inspect recent personal scans, monitor operational alerts, navigate to operational modules

---

## Figure 45: Global Notification Center (Operator View)

Figure 45: Shows the global notification dropdown accessible from the top navigation header on all authenticated routes. Dynamically filters notifications to present immediate operational updates relevant to the current operator, including scan completions, flagged scans requiring attention, and station hardware alerts.

- Route: Global header across protected routes
- User Type: Operator
- Main Actions: View operational alerts, jump directly to scan details, mark notifications as read, clear notifications

---

## Figure 46: Logs and Scan History (Operator View)

Figure 46: Shows the operator logs page presenting a comprehensive table of scan records strictly scoped to the logged-in operator. Features multi-criteria filtering by search keyword, cultivar (Lakatan, Latundan, Cardaba), ripeness stage (Unripe, Semi Ripe, Ripe, Overripe), delivery source, inventory status (In Stock, Sold, For Processing, Spoiled), scan date (Asia/Manila calendar date), and card-based attention filters (At-Risk <=2 days, Pending Review, Auto-approved). Supports live logs reconciliation via WebSockets, inline inventory status updates with mandatory reason logging, CSV/XLSX exports, and clickable QR code thumbnails.

- Route: `/logs`
- User Type: Operator
- Main Actions: Search and filter scans, export CSV/XLSX, update inventory status with reason, view QR code modal, inspect scan details

---

## Figure 47: QR Code Modal & Thermal Label Printing (Logs View)

Figure 47: Shows the QR code modal triggered by clicking any QR code thumbnail in the scan logs table. Displays an enlarged scannable QR code encoding saved prediction values (scan UUID, cultivar, ripeness, spoilage days, confidence, temperature, humidity) and provides integrated thermal label printing via the connected Grozziie TP870 S USB printer. Operators can specify label quantity (1 to 10 copies) and click "Print labels" to print 40mm × 30mm adhesive tags for produce packaging.

- Route: `/logs` (modal overlay)
- User Type: Operator / Admin
- Main Actions: View enlarged QR code, select label quantity (1–10 copies), dispatch print job to station thermal label printer

---

## Figure 48: Scan Detail Page (Operator Context)

Figure 48: Shows the comprehensive scan evidence view displaying synchronized captures from all four cameras (Top CAM-001, Left CAM-002, Right CAM-003, Rear CAM-004) with toggleable YOLO detection bounding boxes and per-camera confidence scores. Displays detected finger count, cultivar, ripeness stage, environmental microclimate telemetry (temperature, relative humidity, and calculated Vapor Pressure Deficit in kPa), spoilage shelf-life estimation with RMSE range, immutable original AI result comparison, QR tracking section with image download and print tag actions, audit note history, and inventory status transition controls with reason logging.

- Route: `/scans/:scanId`
- User Type: Operator
- Main Actions: Inspect multi-angle camera evidence and bounding boxes, review microclimate sensor readings, download QR code, print tag, flag scan for review, log audit notes, transition inventory status

---

## Figure 49: Analytics Page (Operator View)

Figure 49: Shows the operator analytics dashboard presenting visual charts filtered strictly to the logged-in operator's historical activity. Features custom date range selection, ripeness stage distribution pie charts, cultivar count bar charts (Lakatan, Latundan, Cardaba), and daily scan throughput trendlines.

- Route: `/analytics`
- User Type: Operator
- Main Actions: Adjust date range, inspect personal ripeness distribution, review cultivar counts, analyze daily scan throughput

---

## Figure 50: Inventory Monitoring Page (Operator Context)

Figure 50: Shows the inventory monitoring module summarizing active in-stock produce. Displays total banana hands and finger counts, stock breakdown by ripeness stage and cultivar, First-In, First-Out (FIFO) handling guidance, and an urgent spoilage alert table highlighting items expiring within 2 days or already overdue, with direct links to filtered scan records.

- Route: `/inventory`
- User Type: Operator
- Main Actions: Monitor stock counts by cultivar and ripeness, review FIFO dispatch recommendations, inspect 2-day spoilage alerts table

---

## Figure 51: Device Status Page (Operator Context)

Figure 51: Shows the hardware monitoring interface displaying the operational health of station peripherals: a 4-camera connection grid (Top, Left, Right, Rear) with real-time online/offline indicators, Arduino Uno DHT22 ambient temperature and relative humidity readings polled continuously over USB serial, and edge Mini PC host performance metrics (CPU usage, memory allocation, SSD disk space, uptime).

- Route: `/devices`
- User Type: Operator
- Main Actions: Verify camera connectivity, inspect live ambient temperature and humidity, monitor edge PC host performance

---

## Figure 52: User Profile and Account Settings (Operator View)

Figure 52: Shows the operator profile page where users manage personal account details, upload a custom profile avatar (up to 2MB), toggle between light and dark visual themes, view personal lifetime scan metrics and confidence averages, and open modals to change their web password or 4-digit kiosk PIN.

- Route: `/profile`
- User Type: Operator
- Main Actions: Update profile information, upload avatar, toggle theme, launch Change Password modal, launch Change Kiosk PIN modal

---

## Figure 53: Change Password Modal

Figure 53: Shows the self-service password update modal within the user profile. Requires the user to enter and verify their current password before defining and confirming a new permanent password.

- Route: `/profile` (modal overlay)
- User Type: Operator / Admin
- Main Actions: Verify current password, input new password, confirm new password

---

## Figure 54: Change Kiosk PIN Modal

Figure 54: Displays the modal utilized by warehouse operators to independently manage their secure 4-digit numeric kiosk PIN. Utilizes a 4-slot input OTP interface requiring verification of the existing PIN before capturing and confirming the new 4-digit sequence used for edge station authentication.

- Route: `/profile` (modal overlay)
- User Type: Operator
- Main Actions: Verify current 4-digit PIN, input new 4-digit PIN, confirm new PIN

---

## Figure 55: Kiosk Idle/Lock Screen (PIN Login)

Figure 55: Shows the primary edge terminal lock screen displayed when the kiosk is idle or locked. Features a grid of registered warehouse operators with avatars and names. The operator selects their profile and enters their 4-digit numeric PIN on the touch-friendly keypad to unlock the scanning terminal.

- Route: `/kiosk` (idle screen)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal (fullscreen kiosk mode)
- Main Actions: Select operator profile, enter 4-digit numeric PIN, unlock scanning terminal

---

## Figure 56: Set New PIN for Newly Created Account (Kiosk)

Figure 56: Captures the initialization prompt presented to a newly registered warehouse operator the first time they sign into the edge kiosk using temporary credentials (`new_account`). Forces the operator to define and confirm their personal 4-digit PIN before unlocking the scanning station.

- Route: `/kiosk` (initialization overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Enter temporary PIN, create new 4-digit PIN, confirm new PIN

---

## Figure 57: Set New PIN after Admin Reset (Kiosk)

Figure 57: Shows the recovery interface presented on the kiosk immediately following an administrator-triggered PIN reset (`pin_reset`). Forces the operator to enter the administrator-issued temporary PIN and establish a new permanent 4-digit PIN.

- Route: `/kiosk` (recovery overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Enter temporary PIN, create new 4-digit PIN, confirm new PIN

---

## Figure 58: Kiosk Interface (Mini PC Scanning Terminal)

Figure 58: Shows the full-screen kiosk interface deployed on the edge Mini PC terminal. Displays current operator badge, live system clock, active delivery intake batch, 4-camera live feed preview with angle switcher (Top, Left, Right, Rear), "Scan Now" button, "Demo Mode" print calibration button, and a sidebar displaying the 5 most recent scans from the active shift.

- Route: `/kiosk`
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Preview camera feeds, select active delivery intake, trigger scan, run demo label print, swap operator, inspect recent scans

---

## Figure 59: Swap Operator Modal (Kiosk)

Figure 59: Shows the rapid shift-handover overlay allowing operators to switch active accounts at the edge terminal without terminating the current delivery intake session. Prompts for target operator selection and 4-digit PIN verification.

- Route: `/kiosk` (overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Select new operator profile, enter 4-digit PIN, transfer active scanning shift

---

## Figure 60: Kiosk Source / Delivery Intake Selection Modal

Figure 60: Displays the intake selection dialog presented to the operator. Enables selecting a registered agricultural supplier and choosing the ripening treatment (`Natural` or `Ethephon`) to create or select the active delivery intake batch, ensuring all subsequent scans maintain strict provenance.

- Route: `/kiosk` (modal dialog)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Select supplier, choose ripening treatment (`Natural` / `Ethephon`), establish active delivery intake batch

---

## Figure 61: Kiosk Scanning In Progress (4-Stage Pipeline)

Figure 61: Depicts the fullscreen active scanning interface presented on the physical kiosk hardware, visualizing the 4-stage edge AI inspection pipeline through real-time progress indicators. The interface tracks synchronized parallel image capture across all four cameras (Top CAM-001, Left CAM-002, Right CAM-003, Rear CAM-004) paired with serial polling of Arduino Uno DHT22 ambient temperature and humidity; Ultralytics YOLO26 object detection for finger counting and per-camera cultivar and ripeness bounding box localization; multi-camera confidence-weighted fusion with botanical harmonization and Magnus-Tetens Vapor Pressure Deficit (VPD) feature engineering; and Random Forest Regression (RFR) spoilage shelf-life calculation.

- Route: `/kiosk` (active scan overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Monitor live scan execution, observe multi-camera capture status

---

## Figure 62: Kiosk Scan Result & Validation

Figure 62: Shows the immediate post-scan result panel on the kiosk interface. Displays predicted cultivar (Lakatan, Latundan, Cardaba), ripeness stage (Unripe, Semi Ripe, Ripe, Overripe), detected finger count, detection confidence percentage, ambient sensor data ($T$, $RH$, and $VPD$), spoilage shelf-life estimation in days with RMSE range, multi-camera thumbnail carousel with bounding box toggle, auto-print status for the Grozziie TP870 S 40mm × 30mm adhesive QR label, and touch buttons to "Accept" into inventory or "Flag for Review".

- Route: `/kiosk` (post-scan panel)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Review classification and spoilage predictions, inspect bounding boxes, verify label printing, accept scan into inventory, flag scan for review

---

## Figure 63: Dashboard (Admin View)

Figure 63: Shows the administrator dashboard providing enterprise-wide visibility. Displays aggregate scan metrics, active delivery intake totals, overall AI confidence averages, flagged scan counts requiring review, a system-wide recent scan timeline, real-time WebSocket alerts, and direct shortcuts to all management modules.

- Route: `/dashboard`
- User Type: Admin
- Main Actions: Monitor enterprise KPIs, track active delivery intakes, review quality alerts, navigate to management modules

---

## Figure 64: Global Notification Center (Admin View)

Figure 64: Shows the administrative notification center accessible from the navigation header. Consolidates system-wide operational alerts, including hardware status notifications (camera disconnects, sensor timeouts), quality control alerts (classification conflicts, low-confidence scans), intake delivery updates, and automated data retention notices.

- Route: Global header across protected routes
- User Type: Admin
- Main Actions: Review system-wide alerts, navigate to source records, mark notifications as read, clear notifications

---

## Figure 65: Logs and Scan History (Admin View)

Figure 65: Shows the administrative scan history page displaying all organization-wide scans across all operators. Includes an operator filter dropdown alongside standard filters (cultivar, ripeness, intake source, inventory status, Asia/Manila calendar date, and attention cards). Supports live WebSocket reconciliation, inline inventory status updates with mandatory reason logging, CSV/XLSX exports, and QR code modals with multi-label thermal printing (1–10 copies).

- Route: `/logs`
- User Type: Admin
- Main Actions: Filter scans across all operators, export CSV/XLSX, update inventory statuses with reason, view QR modal & print batch labels, inspect scan details

---

## Figure 66: Scan Detail Page (Admin Context)

Figure 66: Shows the detailed scan view in administrative context. Combines full 4-camera visual evidence with bounding box overlays, DHT22 microclimate readings, calculated VPD, spoilage shelf-life range, immutable original AI result comparison, and QR tag management with authoritative management controls: "Edit Scan Data" override mode (correcting cultivar, ripeness, finger count, or source with mandatory audit reason logging and revision locking) and note logging.

- Route: `/scans/:scanId`
- User Type: Admin
- Main Actions: Inspect multi-angle evidence and bounding boxes, download QR code, print tag, apply authoritative classification overrides, log audit notes, update inventory status

---

## Figure 67: Analytics Page (Admin View)

Figure 67: Shows the enterprise analytics dashboard providing organization-level business intelligence. Features custom date range filtering, source-based comparisons across intakes, cultivar distribution charts (Lakatan, Latundan, Cardaba), ripeness stage breakdowns, volume trends, and a comprehensive operator performance table evaluating throughput and review rates.

- Route: `/analytics`
- User Type: Admin
- Main Actions: Select custom date ranges, filter by intake source, compare operator throughput, inspect cultivar and ripeness distributions

---

## Figure 68: Inventory Monitoring Page (Admin Context)

Figure 68: Shows the enterprise inventory monitoring module displaying active stock levels (hands and fingers) by cultivar and ripeness stage, First-In, First-Out (FIFO) queue guidance, and critical 2-day spoilage warnings across all supplier sources, with direct links to filtered scan log records.

- Route: `/inventory`
- User Type: Admin
- Main Actions: Monitor enterprise stock health, evaluate FIFO dispatch priorities, inspect 2-day spoilage alert table, filter by supplier source

---

## Figure 69: Device Status Page (Admin Context)

Figure 69: Shows connected device diagnostics including 4-camera connection health, DirectShow enumeration status, Arduino Uno DHT22 serial communication loop metrics, and granular edge Mini PC host performance telemetry (CPU usage, memory allocation, SSD disk space, uptime, and CPU temperature).

- Route: `/devices`
- User Type: Admin
- Main Actions: Monitor camera array connectivity, check DHT22 sensor communication, review edge server host resource metrics

---

## Figure 70: User Management (Admin)

Figure 70: Shows the user administration module for governing operator and administrator accounts. Displays account table with username, full name, role badge, status badge, search, role filters (Admin, Operator), status filters (Active, Inactive), and action triggers (Add User, Edit User, Toggle Status, Reset Password, Reset PIN).

- Route: `/admin/users`
- User Type: Admin
- Main Actions: Search/filter user registry, register new user, edit user details, activate/deactivate account, initiate password reset, initiate kiosk PIN reset

---

## Figure 71: Create User with Temporary Credentials Handoff Dialog

Figure 71: Shows the initial account creation form used by administrators to register new personnel, paired with a secure one-time handoff dialog that displays the auto-generated temporary password and 4-digit operator kiosk PIN for physical handoff to the employee.

- Route: `/admin/users` (dialog overlay)
- User Type: Admin
- Main Actions: Input username, full name, role, and status; view auto-generated temporary password and 4-digit PIN; securely hand off credentials to employee

---

## Figure 72: Reset User Password Dialog

Figure 72: Displays the administrative action dialog to reset an existing user's password. Generates a secure temporary password displayed once in a confirmation modal for administrative handoff, forcing the user to create a new password upon their next login.

- Route: `/admin/users` (dialog overlay)
- User Type: Admin
- Main Actions: Confirm password reset, view auto-generated temporary password, securely hand off credential

---

## Figure 73: Reset Operator Kiosk PIN Dialog

Figure 73: Represents the administrative recovery dialog to reset an operator's 4-digit kiosk access PIN. Generates an auto-generated temporary PIN displayed once for administrative handoff, prompting mandatory PIN initialization upon next kiosk login.

- Route: `/admin/users` (dialog overlay)
- User Type: Admin
- Main Actions: Confirm PIN reset, view auto-generated temporary 4-digit PIN, hand off PIN for kiosk sign-in

---

## Figure 74: Delivery Intake Management (Admin)

Figure 74: Shows the delivery intake management page used to govern produce batch arrivals. Lists all intakes with supplier name, harvest date, ripening treatment (`Natural` / `Ethephon`), associated scan counts, and status (`Active` / `Depleted`). Features actions to create new intakes, print batch QR code labels for pallet containers, and initiate bulk inventory updates.

- Route: `/admin/delivery-intakes`
- User Type: Admin
- Main Actions: Search and filter intake batches, register new delivery intake, monitor batch lifecycle, print batch QR labels, trigger bulk inventory updates

---

## Figure 75: Bulk Update Status Menu (Delivery Intake)

Figure 75: Demonstrates the administrative bulk inventory management action allowing simultaneous reassignment of an entire delivery intake batch's inventory status (In Stock, For Processing, Sold, Spoiled) via a quick-access menu with mandatory audit reason logging and revision conflict resolution.

- Route: `/admin/delivery-intakes` (dropdown action)
- User Type: Admin
- Main Actions: Select target inventory status for entire intake batch, input mandatory change reason, commit bulk transition

---

## Figure 76: Terminal Status Warning Confirmation Dialog (Delivery Intake)

Figure 76: Captures the critical safeguard dialog that pauses bulk inventory operations when selecting irreversible terminal statuses (Sold, Spoiled). Displays affected scan counts and requires explicit confirmation to prevent accidental produce retirement.

- Route: `/admin/delivery-intakes` (alert dialog)
- User Type: Admin
- Main Actions: Review affected scan volume, acknowledge permanent status transition, confirm bulk status update

---

## Figure 77: Supplier Management (Admin)

Figure 77: Shows the supplier management module maintaining the agricultural grower directory. Lists farm suppliers, contact persons, phone numbers, and active/inactive statuses, with search, status filtering, and management actions.

- Route: `/admin/suppliers`
- User Type: Admin
- Main Actions: Search supplier registry, filter by status, register new supplier, edit supplier details, toggle supplier activation

---

## Figure 78: Add New Supplier Modal

Figure 78: Shows the data entry form used to onboard a new agricultural supplier or farm entity into the system, enforcing unique supplier name validation, contact person, and phone number fields.

- Route: `/admin/suppliers` (modal overlay)
- User Type: Admin
- Main Actions: Input supplier name, contact person, and phone number; validate uniqueness; save to registry

---

## Figure 79: Edit Supplier Modal

Figure 79: Depicts the data modification screen an administrator uses to maintain the accuracy of supplier records, adjusting contact details or status metrics as business relationships evolve.

- Route: `/admin/suppliers` (modal overlay)
- User Type: Admin
- Main Actions: Update supplier contact name and phone details, save modifications

---

## Figure 80: Deactivation Confirmation Dialog (Supplier)

Figure 80: Displays the protective confirmation modal safeguarding the supplier registry, ensuring active farm suppliers are not accidentally suspended or removed from intake selection.

- Route: `/admin/suppliers` (alert dialog)
- User Type: Admin
- Main Actions: Confirm supplier deactivation, review warning on intake routing

---

## Figure 81: Quality Control (Admin)

Figure 81: Shows the dedicated quality control inspection queue presenting banana scans requiring human oversight due to low vision confidence (< configured threshold), cross-camera classification conflicts, or manual operator flags. Displays multi-camera thumbnails, detected bounding boxes, DHT22 temperature and humidity readings, and calculated VPD.

- Route: `/admin/quality`
- User Type: Admin
- Main Actions: Filter quality queue by "Flagged", "Low Confidence", or "Overridden"; open review modal; approve verified scans

---

## Figure 82: Scan Details Review Modal (Quality Control)

Figure 82: Shows the focused review modal utilized by administrators to meticulously inspect individual scan captures. Displays multi-view camera captures with bounding boxes, per-camera confidence scores, detected finger counts, immutable original AI predictions, and microclimate telemetry.

- Route: `/admin/quality` (modal overlay)
- User Type: Admin
- Main Actions: Inspect multi-angle camera evidence and bounding boxes, compare original AI predictions, review sensor readings

---

## Figure 83: Edit Scan Data / Authoritative Override Mode

Figure 83: Shows the authoritative override interface where an administrator formally overrides algorithm estimates and manually catalogs the true cultivar, ripeness stage, finger count, or source, permanently logging the human correction with a mandatory audit reason and optimistic revision locking.

- Route: `/admin/quality` and `/scans/:scanId` (modal overlay)
- User Type: Admin
- Main Actions: Select corrected cultivar, ripeness stage, finger count, or source; input mandatory justification reason; save authoritative correction

---

## Figure 84: Activity Log (Admin)

Figure 84: Shows the activity log screen recording all user and system actions for security auditing and compliance. Displays a server-paginated table of events (logins, logouts, scan creations, scan overrides, user modifications, configuration changes) with timestamps, user identities, action categories, detail descriptions, and client IP addresses, alongside 24-hour summary metrics and CSV export.

- Route: `/admin/activity`
- User Type: Admin
- Main Actions: Search audit events, filter by action type and user, review 24-hour summary metrics, export audit logs as CSV

---

## Figure 85: System Configuration - Overview (Admin)

Figure 85: Shows the consolidated system configuration portal organizing station settings into four tabs: Scanner Configuration, AI Settings, Storage Management, and Power Management.

- Route: `/admin/config`
- User Type: Admin
- Main Actions: Navigate configuration tabs, monitor maintenance state, save global station settings

---

## Figure 86: Scanner Configuration & Camera Calibration

Figure 86: Displays the hardware setup panel used by administrators to discover USB cameras via DirectShow/cv2-enumerate-cameras, map physical camera positions (Top CAM-001, Left CAM-002, Right CAM-003, Rear CAM-004), and launch live camera calibration preview feeds to adjust lens focus, lighting, and bunch placement.

- Route: `/admin/config` (Scanner Configuration tab)
- User Type: Admin
- Main Actions: Discover connected camera indices, map physical camera positions, launch live camera calibration preview modal

---

## Figure 87: AI Settings (Confidence Threshold Calibration)

Figure 87: Depicts the machine learning configuration interface where administrators calibrate the required review confidence threshold slider (0% to 100%), establishing the certainty level the YOLO vision model must satisfy to auto-accept a scan into inventory versus routing it to the Quality Control queue.

- Route: `/admin/config` (AI Settings tab)
- User Type: Admin
- Main Actions: Adjust detection review confidence threshold slider, save threshold configuration

---

## Figure 88: Storage Management & Station Backup / Restore

Figure 88: Shows the administrative data management tools dedicated to configuring automated image retention cleanup policies for expired camera captures, triggering flat-file CSV scan activity exports, and generating or restoring typed system backup archives with SHA-256 validation.

- Route: `/admin/config` (Storage Management tab)
- User Type: Admin
- Main Actions: Toggle automated capture retention cleanup, export scan data CSV, create typed system backup archive, restore configuration archive

---

## Figure 89: Power Management & System Maintenance Controls

Figure 89: Captures the remote station operations view where administrators observe terminal uptime and trigger controlled operating system restart or shutdown commands, coordinated by a maintenance state machine that drains active scans before power execution to prevent data corruption.

- Route: `/admin/config` (Power Management tab)
- User Type: Admin
- Main Actions: Monitor station uptime, initiate controlled Mini PC shutdown, initiate controlled Mini PC restart

---

## Figure 90: User Profile and Account Settings (Admin View)

Figure 90: Shows the administrator profile page where users manage account details, upload an avatar (up to 2MB), toggle dark/light themes, review administrative activity metrics, and open the Change Password modal (omitting kiosk PIN controls since edge scanning is operator-specific).

- Route: `/profile`
- User Type: Admin
- Main Actions: Update profile settings, upload avatar, toggle theme, launch Change Password modal

---

## Figure 91: Change Password Modal (Admin Context)

Figure 91: Displays the administrative self-service modal dedicated to maintaining account security by verifying the current password before applying a new permanent credential.

- Route: `/profile` (modal overlay)
- User Type: Admin
- Main Actions: Verify current password, input new password, confirm new password

---

## Figure 92: Public Scan Tracking View (Mobile & Web QR Portal)

Figure 92: Shows the public-facing scan tracking interface accessible by scanning the QR code on a printed 40mm × 30mm produce label with any smartphone camera or standard web browser without requiring system authentication. Displays verified banana provenance: cultivar (Lakatan, Latundan, Cardaba), ripeness stage, finger count, estimated remaining shelf life in days, scan timestamp, delivery intake origin, and inspection capture photos, while automatically redirecting authenticated warehouse personnel to the full internal scan detail page.

- Route: `/track/:scanId`
- User Type: Public / Downstream Consumer / Quality Inspector
- Main Actions: Scan printed QR label with smartphone or browser, inspect produce provenance and classification, verify remaining shelf-life days, view multi-camera capture photos
