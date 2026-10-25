# Storyboard

A storyboard is a sequence of visual frames used to illustrate how users interact with a system over time. It presents key screens, actions, and transitions to communicate the flow of tasks and the expected system responses.

## BananaVision Storyboard (Quality & Shelf-Life Dashboard and Mini PC Kiosk)

These figures map directly to the implemented interfaces. The storyboard is divided into the Web Dashboard (for monitoring and administration) and the Mini PC Kiosk (for physical edge deployment).

## Figure 28: Landing Page - Hero Section (Web)

Figure 28: Illustrates the hero section of the public-facing landing page, introducing BananaVision as an AI-powered banana classification system built for medium and large enterprises. The section presents the system tagline, a brief value proposition, and primary call-to-action buttons for accessing the dashboard or learning more.

- Route: `/`
- User Type: Public
- Main Actions: Navigate to login, scroll to learn more

## Figure 29: Landing Page - About Section (Web)

Figure 29: Shows the About BananaVision section, describing the system's mission and capabilities. It explains how the system uses AI and camera-based recognition to identify banana cultivar, determine ripeness, and estimate shelf life, serving medium and large enterprises including retail grocery chains, banana processing and chip manufacturing facilities, and wholesale distributors.

- Route: `/#about`
- User Type: Public
- Main Actions: Read system overview

## Figure 30: Landing Page - Key Features Section (Web)

Figure 30: Displays the Key Features grid highlighting the six core capabilities of the system: AI-Assisted Scanning, Operator Kiosk, Scan Review, Inventory Tracking, Reports & Charts, and Full Scan History. Each feature is presented with an icon and brief description.

- Route: `/#features`
- User Type: Public
- Main Actions: Review feature highlights

## Figure 31: Landing Page - System Modules Section (Web)

Figure 31: Shows the System Modules section, presenting three role-based modules: Operator Kiosk, Operator Dashboard, and Admin Dashboard. Each module is displayed with a numbered card listing its specific capabilities and user actions.

- Route: `/#modules`
- User Type: Public
- Main Actions: Understand role-based system structure

## Figure 32: Landing Page - FAQs Section (Web)

Figure 32: Displays the Frequently Asked Questions section using an accordion interface. Questions address the target market (medium and large enterprises including retail grocery chains, processing facilities, and wholesale distributors), internet connectivity requirements (runs locally on mini PC with no internet needed), and required hardware (mini PC, webcams, external monitor).

- Route: `/#faqs`
- User Type: Public
- Main Actions: Expand/collapse FAQ items

## Figure 33: Landing Page - Contact Support Section (Web)

Figure 33: Shows the Contact Support section with a call-to-action for reaching the support team via email. Provides a direct link to contact support for setup and business inquiries.

- Route: `/#contact`
- User Type: Public
- Main Actions: Contact support team via email

## Figure 34: Login Page (Web)

Figure 34: Depicts the authentication interface, requiring users to input valid credentials to access the role-based system dashboard.

- Route: `/login`
- User Type: Public
- Main Actions: Sign in, toggle password visibility

## Figure 35: First Login Password Change for Newly Created Account

Figure 35: Shows the mandatory security prompt presented to new users upon their first login. The user is required to set and confirm a new permanent password before they can access their role-based dashboard.

## Figure 36: First Login Password Change after Password Reset

Figure 36: Shows the forced password reset workflow triggered when an administrator has reset an existing user\'s password. The user must provide a new password before gaining system access.


## Figure 37: Dashboard (Operator View)

Figure 37: Shows the operator dashboard presenting scan-related KPIs, active sources, confidence statistics, and recent scan activity for day-to-day monitoring.

- Route: `/dashboard`
- User Type: Operator
- Main Actions: Review KPIs, open logs, navigate to module pages

## Figure 38: Global Notification Center (Operator View)

Figure 38: Shows the global notification dropdown accessible from the top navigation header. This view dynamically filters alerts to display only immediate operational updates relevant to the current user, specifically scan completions and flagged scans requiring operator attention.

- Route: Available globally on all protected routes
- User Type: Operator
- Main Actions: View alerts, navigate to scan details, mark as read, clear all notifications

## Figure 39: Logs and Scan History (Operator View)

Figure 39: Shows the operator logs page listing the operator's scan records with filters, search, status indicators, environmental IoT data (temperature and humidity), QR code thumbnails, and export support for operational tracking. Clicking a QR code thumbnail opens a modal displaying the enlarged QR code with a "Print Tag" button for printing a compact tag to attach to the banana hand.

- Route: `/logs`
- User Type: Operator
- Main Actions: Filter scans, export CSV, open scan details, view QR code modal, print tag, update inventory status

## Figure 40: QR Code Modal (Logs View)

Figure 40: Shows the QR code preview modal that appears when clicking a QR code thumbnail in the scan logs table. The modal displays the enlarged QR code, the cultivar name, scan ID, and a single "Print Tag" button that prints a compact tag (QR code, scan ID, cultivar, ripeness, and date) designed to be attached directly to the banana hand.

- Route: `/logs` (modal overlay)
- User Type: Operator / Admin
- Main Actions: View enlarged QR code, print compact tag

## Figure 41: Scan Detail Page (Operator Context)

Figure 41: Shows the detailed scan view presenting cultivar, ripeness, confidence, estimated spoilage range (in days), environmental sensor readings (temperature and humidity), camera captures, QR tracking section with save and print tag actions, and note history.

- Route: `/scans/:scanId`
- User Type: Operator
- Main Actions: View full scan context, save QR code image, print tag, flag scan, add notes

## Figure 42: Analytics Page (Operator View)

Figure 42: Shows the operator analytics screen with chart-based insights filtered uniquely to the logged-in operator's activity.

- Route: `/analytics`
- User Type: Operator
- Main Actions: Change date range, compare trends, inspect distributions

## Figure 43: Inventory Monitoring Page (Operator Context)

Figure 43: Shows the inventory module summarizing stock quantities, ripeness breakdown, estimated spoilage day ranges (RMSE-adjusted), and FIFO-based handling guidance.

- Route: `/inventory`
- User Type: Operator
- Main Actions: Monitor stock health, review spoilage urgency

## Figure 44: Device Status Page (Operator Context)

Figure 44: Shows the connected device monitoring interface for camera health, online/offline state, uptime indicators, and real-time environmental sensors (ambient temperature and humidity) used by the random forest model.

- Route: `/devices`
- User Type: Operator
- Main Actions: Check camera availability and sensor readings

## Figure 45: User Profile and Account Settings (Operator View)

Figure 45: Shows the operator profile page where users manage account details, avatar, password and PIN settings, and personal usage statistics.

- Route: `/profile`
- User Type: Operator
- Main Actions: Update profile settings, change password and kiosk PIN, switch theme

## Figure 46: Change Password Modal

Figure 46: Shows the interface within the user profile where operators and admins can securely update their own login password by providing their current credential followed by the desired new string.

## Figure 47: Change Kiosk PIN Modal

Figure 47: Displays the modal used by warehouse operators to independently manage their secure 4-digit numeric PIN, which is required for authenticating physical actions on the mini PC kiosk.


## Figure 48: Kiosk Idle/Lock Screen (Login)

Figure 48: Shows the primary idle lock screen presented when the kiosk is not in use or explicitly locked. A warehouse operator must input their secure 4-digit PIN to unlock the environment and begin their shift or batch session.

## Figure 49: Set New PIN for Newly Created Account

Figure 49: Captures the initialization prompt delivered to a newly registered warehouse operator the very first time they attempt to sign into an edge kiosk, creating their personal 4-digit PIN.

## Figure 50: Set New PIN after Admin Reset

Figure 50: Shows the recovery interface that forces an existing operator to define a new, securely remembered 4-digit PIN immediately following an administrator-triggered PIN reset.

## Figure 51: Kiosk Interface (Mini PC)

Figure 51: Shows the full-screen kiosk interface deployed on the mini PC terminal for rapid operator scanning, displaying current operator details, time context, and scan controls.

- Route: `/kiosk`
- User Type: Operator
- Deployment Context: Dedicated mini PC kiosk terminal
- Main Actions: Select source, start scan, swap operator

## Figure 52: Swap Operator Modal

Figure 52: Shows the quick-swap authentication overlay presented when changing operators mid-shift. This secondary challenge ensures accountability for subsequent scans without fully locking the kiosk context.

## Figure 53: Kiosk Source Selection Modal

Figure 53: Displays the source selection dialog window presented to the operator. This ensures that every subsequent banana classification scanned sequentially corresponds to the explicitly selected intake supplier or farm batch origin until the operator changes it.

## Figure 54: Kiosk Scanning In Progress

Figure 54: Depicts the fullscreen data entry interface presented on the physical kiosk hardware when actively processing image captures and logging visual inspection readings along with IoT temperature and humidity capture.

## Figure 55: Kiosk Scan Result & Validation

Figure 55: Shows the immediate post-scan result panel on the kiosk interface, presenting the predicted cultivar, ripeness, finger count, environmental sensor data, confidence level, and a QR code preview confirming that a tracking tag has been generated. The operator is prompted via large action buttons to explicitly "Accept" the classification into inventory or "Flag for Review" if the AI's classification seems incorrect.

## Figure 56: Dashboard (Admin View)

Figure 56: Shows the admin dashboard with system-level visibility, including aggregate scan metrics, multi-user activity context, and operational status indicators.

- Route: `/dashboard`
- User Type: Admin
- Main Actions: Review overall system status, jump to management modules

## Figure 57: Global Notification Center (Admin View)

Figure 57: Shows the global notification dropdown accessible from the top navigation header. This administrative view displays a comprehensive list of all system-wide notification types, including system-level alerts, batch intake updates, global quality warnings, and individual scan updates.

- Route: `/alert` Available globally on all protected routes
- User Type: Admin
- Main Actions: View comprehensive system alerts, navigate to the source of the alert, mark as read, clear all notifications

## Figure 58: Logs and Scan History (Admin View)

Figure 58: Shows the admin logs page listing organization-wide scan records with additional operator-level filtering, QR code thumbnails, environmental IoT data (temperature and humidity), and management actions. Clicking a QR code thumbnail opens a modal with an enlarged QR code and a "Print Tag" button.

- Route: `/logs`
- User Type: Admin
- Main Actions: Filter scans across all operators, export CSV, open scan details, view QR code modal, print tag

## Figure 59: Scan Detail Page (Admin Context)

Figure 59: Shows the detailed scan view similar to the operator's view but with elevated control actions to edit or override algorithm estimates. Includes QR tracking section with save and print tag actions.

- Route: `/scans/:scanId`
- User Type: Admin
- Main Actions: View full scan context, save QR code, print tag, apply data corrections, add authoritative notes

## Figure 60: Analytics Page (Admin View)

Figure 60: Shows the admin analytics screen with broader organization-level chart insights and source-based filtering across users and intakes.

- Route: `/analytics`
- User Type: Admin
- Main Actions: Change date range, filter by source, compare trends across operators

## Figure 61: Inventory Monitoring Page (Admin Context)

Figure 61: Shows the inventory module with authoritative actions to adjust stock counts manually alongside the computed spoilage alerts.

- Route: `/inventory`
- User Type: Admin
- Main Actions: Monitor stock health, inspect intake-linked items, manual overrides

## Figure 62: Device Status Page (Admin Context)

Figure 62: Shows connected device monitoring including granular system resource status and camera restart actions.

- Route: `/devices`
- User Type: Admin
- Main Actions: Check availability, monitor performance telemetry, remote troubleshooting

## Figure 63: User Management (Admin)

Figure 63: Shows the user administration page for managing operator and admin accounts, including role assignment, status updates, and account resets.

- Route: `/admin/users`
- User Type: Admin
- Main Actions: Add user, edit user, reset password/PIN, activate or deactivate account

## Figure 64: Create User with Temporary Credentials

Figure 64: Shows the initial account creation form used by administrators to generate placeholder credentials (e.g., password ) when onboarding new staff or operator personnel.

## Figure 65: Reset User Password to Temporary Password

Figure 65: Displays the administrative action to forcibly revert an existing user's password back to a default state, allowing them to regain access and establish a permanent credential.

## Figure 66: Reset Operator Kiosk PIN

Figure 66: Represents the admin action to forcibly reset an operator's secure access PIN, prompting them to create a new one upon their next kiosk login.

## Figure 67: Intake Management (Admin)

Figure 67: Shows the delivery intakes page used to track batches, monitor intake status, and perform bulk inventory state updates across an entire batch.

- Route: `/admin/intakes`
- User Type: Admin
- Main Actions: Search/Filter intakes, change intake activity status, apply bulk inventory updates

## Figure 68: Bulk Update Status Menu

Figure 68: Demonstrates the time-saving administrative feature allowing the bulk re-assignment of an entire intake batch\'s inventory status simultaneously via a quick-access dropdown menu.

## Figure 69: Terminal Status Warning Dialog

Figure 69: Captures the critical safeguard dialog that pauses bulk administrative operations to require final confirmation before finalizing permanent inventory state changes.

## Figure 70: Supplier Management (Admin)

Figure 70: Shows the supplier management module for maintaining supplier records, contact details, and activation status.

- Route: `/admin/suppliers`
- User Type: Admin
- Main Actions: Add supplier, edit supplier data, activate or deactivate supplier

## Figure 71: Add New Supplier Modal

Figure 71: Shows the data entry form utilized by management to onboard a new agricultural supplier or farm entity into the system, including critical registry and contact fields.

## Figure 72: Edit Supplier Modal

Figure 72: Depicts the data modification screen an administrator uses to maintain the accuracy of supplier records, adjusting contact info or status metrics as business relationships evolve.

## Figure 73: Deactivation Confirmation Dialog

Figure 73: Displays the mandatory verification modal protecting the organization\'s supplier registry, ensuring active suppliers are not accidentally suspended or removed from routing options.

## Figure 74: Quality Control (Admin)

Figure 74: Shows the quality control page focused on flagged and low-confidence scans, enabling review, override, and correction workflows. Displays ML inputs including cultivar, temperature, and humidity.

- Route: `/admin/quality`
- User Type: Admin
- Main Actions: Filter quality issues, review scan anomalies, apply override updates

## Figure 75: Scan Details Review Modal

Figure 75: Views the focused modal utilized by system administrators to meticulously review individual scan captures that the vision model flagged due to low confidence or anomalies.

## Figure 76: Edit Scan Data / Override Mode

Figure 76: Shows the authoritative override interface where an administrator formally rejects a system estimation and manually catalogs the true cultivar or ripeness, permanently logging the human correction.

## Figure 77: Activity Log (Admin)

Figure 77: Shows the activity log screen that records user and system actions for auditing, traceability, and administrative review.

- Route: `/admin/activity`
- User Type: Admin
- Main Actions: Search events, filter by action/user, export audit logs

## Figure 78: System Configuration (Admin)

Figure 78: Shows the system configuration page for scanner settings, AI threshold adjustment, data handling options, and controlled power actions. All configuration modules are viewable on a single consolidated page for immediate system state oversight.

- Route: `/admin/config`
- User Type: Admin
- Main Actions: Update camera IDs, tune confidence threshold, trigger export, run system controls

## Figure 79: Hardware Integration

Figure 79: Displays the hardware setup panel used by system administrators to configure the specific camera device IDs utilized by the edge equipment during active fruit inspection.

## Figure 80: AI Settings

Figure 80: Depicts the machine learning configuration interface where administrators calibrate the required certainty thresholds the vision algorithm must meet to auto-accept a scan.

## Figure 81: Storage Management

Figure 81: Shows the administrative tools dedicated to managing historical data volume, including toggling routine storage cleanup rules and executing manual flat-file CSV backups of scan activity.

## Figure 82: Power Management

Figure 82: Captures the remote operations view where administrators can observe the uptime of deployment edge terminals and trigger maintenance restart or shutdown operations across the network.

## Figure 83: User Profile and Account Settings (Admin View)

Figure 83: Shows the admin profile page where users manage account details, avatar, password settings, and system-level personal statistics.

- Route: `/profile`
- User Type: Admin
- Main Actions: Update profile settings, change password, switch theme

## Figure 84: Change Password Modal

Figure 84: Displays the administrative self-service interface dedicated to maintaining the security of the manager\'s own account by allowing credential modification.
