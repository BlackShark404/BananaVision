# Storyboard

A storyboard is a sequence of visual frames used to illustrate how users interact with a system over time. It presents key screens, actions, and transitions to communicate the flow of tasks and the expected system responses.

## BananaVision Storyboard (Quality & Shelf-Life Dashboard and Mini PC Kiosk)

These figures map directly to the implemented interfaces and application routes across the BananaVision platform. The storyboard is organized into four interconnected deployment domains: the Public Web Portal & Traceability featuring the landing page and unauthenticated QR-code batch tracking portal (`/track/:scanId`); the Operator Web Dashboard providing role-scoped shift monitoring, scan logs, FIFO inventory management, analytics, and device status; the Dedicated Mini PC Kiosk providing an isolated, touch-first edge scanning terminal for physical post-harvest inspection, multi-camera capture, 4-stage AI classification, and automated thermal label printing; and the Administrator Web Dashboard delivering comprehensive operational governance, user credential handoff, delivery intake batch management, quality control review and overrides, activity audit logs, and station configuration.

---

## Figure 35: Landing Page - Hero Section (Web)

Figure 35: Illustrates the hero section of the public-facing landing page, introducing BananaVision as an AI-powered banana classification and shelf-life estimation system built for medium and large enterprises. The section features a modern glassmorphic hero banner with layered blur backgrounds, a subtle grid texture overlay, and a decorative primary-color gradient bloom positioned behind the content for visual depth. At the top of the section, an animated pulse dot badge displays the text "Banana Classification System" to establish the product category at a glance. The system tagline ("Smarter Classification with BananaVision") is rendered in a large, bold heading with the product name styled using a horizontal gradient spanning primary yellow, amber, and orange tones. Below the tagline, a concise value proposition describes the system's core capability: classifying cultivar and ripeness in seconds while tracking stock and reducing waste. Two primary call-to-action buttons are presented side by side — "Access Dashboard" with a glowing yellow box-shadow and hover lift animation linking to `/login`, and "Learn More" with an outlined variant that smooth-scrolls to the About section. The entire hero section occupies at least 85% of the viewport height and features a fade-in animation on initial render.

- Route: `/`
- User Type: Public
- Main Actions: Navigate to login (`/login`), smooth-scroll to explore system capabilities (`/#about`)

---

## Figure 36: Landing Page - About Section (Web)

Figure 36: Shows the About BananaVision section, describing the system's operational mission and industrial scope. The layout uses a responsive two-column grid: the left column presents editorial content while the right column features a decorative logo showcase card. An "Our Mission" badge anchors the section heading, followed by the section title "About BananaVision" and two descriptive paragraphs. The first paragraph positions the system as an enterprise-grade AI solution designed to solve real challenges faced by medium and large enterprises in the banana supply chain. The second paragraph explains how the platform uses AI and camera-based recognition to identify the banana variety, determine how ripe it is, and estimate how long it will last — helping businesses speed up their scanning process and reduce product waste. The right column displays the BananaVision logo inside a circular frosted-glass container with a subtle animated gradient glow effect, hover rotation transform, and a scale-up interaction on the logo element. The section background uses a gradient from primary tint to transparent, with a thin decorative gradient line at the top border. The system highlights support for medium and large enterprises in the banana supply chain, including retail grocery chains, banana processing and chip manufacturing facilities, and commercial wholesale distributors.

- Route: `/#about`
- User Type: Public
- Main Actions: Read system mission, understand supply-chain application

---

## Figure 37: Landing Page - Key Features Section (Web)

Figure 37: Displays the Key Features grid highlighting the six core functional capabilities of the system. The section opens with a centered heading "Key Features" and a subtitle "Everything your business needs to modernize banana handling and classification." Below, a responsive three-column card grid presents each feature inside tall, rounded glassmorphic cards with a frosted backdrop-blur, semi-transparent white background, and a top-edge glare gradient for a premium appearance. Each card hovers upward with an enhanced shadow and reveals a subtle primary-tinted background overlay on interaction. Every card contains a large icon inside a rounded container that transitions from a tinted outline style to a filled primary-colored badge on hover, a bold title, and a descriptive paragraph. The six core features are: (1) AI-Assisted Scanning for identifying commercial Philippine banana cultivars (Lakatan, Latundan, Cardaba), determining ripeness stages, counting bunch fingers, and calculating shelf life using microclimate telemetry; (2) the touch-friendly Operator Kiosk for rapid multi-camera batch scanning where warehouse workers can quickly scan bananas one delivery at a time; (3) Scan Review mechanisms that automatically flag low-confidence or conflicting classifications for administrative oversight so a manager can double-check and correct them later; (4) real-time Inventory Tracking with First-In, First-Out (FIFO) handling guidance and alerts when items are about to spoil; (5) interactive Reports & Charts illustrating daily output, intake results, and worker performance through easy-to-read visualizations; and (6) a complete, searchable Full Scan History providing a browsable and filterable audit trail of every inspection record filtered by date, intake, or worker.

- Route: `/#features`
- User Type: Public
- Main Actions: Review core functional highlights

---

## Figure 38: Landing Page - System Modules Section (Web)

Figure 38: Shows the System Modules section, presenting the three role-tailored application environments across numbered cards in a responsive three-column layout. The section opens with the heading "System Modules" and the subtitle "Different views for different roles — operators scan, managers oversee." Each module is displayed inside a tall glassmorphic card with a decorative blurred primary circle in the top-right corner that intensifies on hover, a top-edge glare gradient, and a numbered badge that transitions to filled primary styling on interaction. Each card lists specific capabilities as a checklist with green checkmark icons. The section details: (1) the Operator Kiosk — a focused scanning screen for warehouse workers featuring quick operator switching using a PIN, multi-angle camera capture, delivery source selection, accept-or-flag result actions, and instant recent scan visibility; (2) the Operator Dashboard — a simplified dashboard showing only the operator's own work including personal scan results and history, performance charts, current stock with freshness alerts, and camera connection status; and (3) the Admin Dashboard — providing complete visibility and control for managers encompassing monitoring of all scans across the system, inventory tracking with freshness alerts, detailed charts and reports, scan result review and correction, user/supplier/device management, and access to activity history and system settings. The cards feature a horizontal divider between the module description and the feature checklist, and each item is rendered with a subtle color transition on card hover for enhanced interactivity.

- Route: `/#modules`
- User Type: Public
- Main Actions: Understand role-based system structure and access boundaries

---

## Figure 39: Landing Page - FAQs Section (Web)

Figure 39: Displays the Frequently Asked Questions section utilizing an interactive accordion interface built with the Radix UI Accordion primitive in single-collapsible mode, allowing users to expand one question at a time while automatically closing previously open items. The section is rendered within a centered container with a maximum width for comfortable reading. Three questions are presented with large, left-aligned trigger text and muted-color answer content that smoothly expands and collapses with CSS height transitions. The questions address: (1) the target market — clarifying that BananaVision is made for medium and large enterprises that handle banana packaging and distribution, helping workers classify bananas faster and giving managers a clear picture of their inventory; (2) the offline network capability — explaining that the entire system runs on a local Mini PC that hosts both the frontend and backend, with devices like tablets or computers connecting through a local network (LAN or hotspot) without requiring an active internet connection; and (3) the physical hardware requirements — describing the scanning station's use of a Mini PC that runs the entire system, connected to external webcams for capturing banana images and an external monitor displaying the Kiosk interface, while other devices access the dashboard by connecting over the local network. The section background uses a gradient from the base background to a subtle primary tint to visually link it to the surrounding sections.

- Route: `/#faqs`
- User Type: Public
- Main Actions: Expand/collapse FAQ accordion items

---

## Figure 40: Landing Page - Contact Support Section (Web)

Figure 40: Shows the Contact Support section featuring a direct communication channel for enterprise inquiries. The section is centered within a narrow container and opens with a large rounded icon container holding a Mail icon rendered in the primary color against a tinted background. Below, the heading "Need Help?" is followed by a supportive paragraph: "Have questions about setting up BananaVision for your business? We're here to help." A prominent action button labeled "Contact Support Team" links directly to the technical support team via email (`mailto:support@bananavision.com`) for station deployment, hardware setup assistance, and business inquiries. The section background features a gradient from primary tint to a slightly deeper primary tone with a thin decorative gradient line at the bottom border and a top border separator, creating visual closure for the landing page content. The entire landing page concludes with a minimal footer displaying the copyright notice with the current year dynamically rendered.

- Route: `/#contact`
- User Type: Public
- Main Actions: Contact technical support team via email

---

## Figure 41: Login Page (Web)

Figure 41: Depicts the centralized authentication portal presented as a single Card component centered within a full-viewport layout with decorative background blurs in warm banana tones positioned at opposite corners of the screen. The login card features the BananaVision logo at the top with a subtle pulsing glow animation, the system name "BananaVision" as the card title, and the subtitle "AI-Powered Banana Classification System." The form contains labeled username and password input fields with 44px height and rounded corners for a polished appearance, along with a password visibility toggle button using Eye/EyeOff icons that allows users to switch between hidden and visible password display. The submit button spans the full card width, displays a spinning animation during authentication, and shows contextual text ("Signing in..." while loading). Upon successful authentication, the system evaluates the user's role and redirects them to the Dashboard at `/dashboard`. If the account is deactivated, an error toast notifies the user to contact an administrator. The form includes a double-submission guard using a ref-based flight lock to prevent duplicate authentication requests during network latency.

- Route: `/login`
- User Type: Public / Unauthenticated Staff
- Main Actions: Sign in with credentials, toggle password visibility, trigger authentication

---

## Figure 42: First Login Password Change for Newly Created Account

Figure 42: Shows the mandatory security modal presented immediately upon first sign-in for newly registered accounts created with temporary credentials (`new_account`). When the backend login response returns `requires_password_change_new_account`, the login form transitions with a fade-in animation to display a password update interface. A prominent banner with a primary-tinted background displays the message: "Welcome! Your account was newly created. Please set a new secure password to continue." The user is presented with two input fields — "New Password" and "Confirm Password" — each with individual password visibility toggles and rounded styling consistent with the login form. Client-side validation enforces that both password fields match and that the new password meets a minimum length of 6 characters, displaying descriptive toast error messages for each violation. The submit button text changes to "Save & Continue to Dashboard" and shows an "Updating..." spinner during the API call. The user is prevented from navigating the system until they establish and confirm a new, permanent password meeting security complexity requirements. Upon successful password update, a success toast confirms the change and the user is redirected to the Dashboard.

- Route: `/login` (mandatory modal prompt)
- User Type: Newly Onboarded Operator / Admin
- Main Actions: Enter new permanent password, confirm password, establish account security

---

## Figure 43: First Login Password Change after Password Reset

Figure 43: Shows the forced password update interface presented to existing users whose credentials were reset by an administrator (`password_reset`). When the backend login response returns `requires_password_change_reset`, the login form transitions to the same password update interface described in Figure 42, but with a contextually different banner message: "Welcome back! Because your password was recently reset, please set a new secure password to continue." This distinction ensures the user understands why they are being prompted — their administrator initiated the reset rather than this being a new account setup. The same client-side validation rules apply, requiring matching passwords with a minimum of 6 characters. The user must replace the administrator-issued temporary password with a new permanent password before gaining dashboard access. The authentication flow uses the `setupPasswordAndLogin` function from the AuthContext, which atomically updates the credential and establishes a new authenticated session in a single API call, avoiding the need for a separate re-login step after the password change.

- Route: `/login` (mandatory modal prompt)
- User Type: Operator / Admin
- Main Actions: Enter new permanent password, confirm password, regain account access

---

## Figure 44: Dashboard (Operator View)

Figure 44: Shows the operator dashboard tailored for daily shift monitoring, rendered within the authenticated AppLayout shell with sidebar navigation and a top header bar. The dashboard content is keyed to the current user's ID and role, ensuring a clean state reset when operator accounts are swapped. The page subscribes to two WebSocket rooms — "dashboard" and "devices" — to receive real-time updates, with a debounced 750ms refresh delay after each event to ensure data consistency after backend commit. A 15-second polling interval updates the displayed clock, and a midnight-boundary timer automatically refreshes metrics when the business date rolls over in Asia/Manila timezone. The dashboard displays operator-scoped KPIs rendered as AppStatsCard components including personal scan count, active delivery sources, and average detection confidence. Quick-access shortcut cards link to operational modules such as Logs, Inventory, Analytics, and Device Status. A feed of recent personal scans is presented via the DashboardRecords component with inline scan thumbnails, cultivar badges, and ripeness indicators. Real-time operational alerts received via WebSockets appear as live-updating entries, including scan completions, classification flag events, and hardware status changes from the station. The dashboard also reports the current WebSocket connection status, providing visual feedback if the real-time data link is interrupted.

- Route: `/dashboard`
- User Type: Operator
- Main Actions: Review shift throughput, inspect recent personal scans, monitor operational alerts, navigate to operational modules

---

## Figure 45: Global Notification Center (Operator View)

Figure 45: Shows the global notification dropdown accessible from the top navigation header on all authenticated routes. The AppNotifications component is rendered within the AppLayout header and dynamically filters notifications to present immediate operational updates relevant to the current operator's account scope. Notifications include scan completions with cultivar and ripeness summaries, flagged scans requiring attention, station hardware alerts such as camera disconnections and sensor timeouts, and inventory status transitions. Each notification entry displays a timestamp, a descriptive message, and a contextual icon indicating the notification type. Clicking on a scan-related notification navigates the user directly to the corresponding scan detail page at `/scans/:scanId`. Individual notifications can be marked as read with a single click, and a "Clear All" action dismisses all accumulated notifications. The notification center updates in real-time through the WebSocket connection, ensuring operators are immediately informed of system events without needing to manually refresh the page.

- Route: Global header across protected routes
- User Type: Operator
- Main Actions: View operational alerts, jump directly to scan details, mark notifications as read, clear notifications

---

## Figure 46: Logs and Scan History (Operator View)

Figure 46: Shows the operator logs page presenting a comprehensive, server-paginated table of scan records strictly scoped to the logged-in operator using the AppDataTable component with configurable column definitions and sortable headers. The page header displays the title "Scan History" with a summary subtitle and is accompanied by an ExportDropdown component offering CSV and XLSX export options that collect all matching pages before generating the download. The table features multi-criteria filtering through the AppTableFilters component and dedicated filter controls: a text search field for keyword matching against scan IDs, operator names, and source names; cultivar dropdown filter (Lakatan, Latundan, Cardaba); ripeness stage dropdown filter (Unripe, Semi Ripe, Ripe, Overripe); delivery source filter; inventory status filter (In Stock, Sold, For Processing, Spoiled); an AppDateFilter component for Asia/Manila calendar date selection; and card-based attention filters rendered as clickable stat cards (At-Risk ≤2 days, Pending Review, Auto-approved) that highlight counts and apply the corresponding filter on click. The table supports live logs reconciliation via WebSocket events using a custom event-driven system with `SCAN_UPDATED_EVENT`, `SCANS_ADDED_EVENT`, and `LIVE_RESUMED_EVENT` dispatched through the browser's CustomEvent API, ensuring rows are updated in real-time without disrupting active user edits. Each row includes an inline inventory status dropdown with mandatory reason logging via a confirmation dialog with a Textarea component, and clickable QR code thumbnails that open the QR code modal. Spoilage days are formatted using the `formatSpoilageDays` utility with RMSE range display, and remaining shelf-life is calculated dynamically relative to the current time. The page also provides `scanLogParams` URL-driven state management, preserving filter selections across navigation.

- Route: `/logs`
- User Type: Operator
- Main Actions: Search and filter scans, export CSV/XLSX, update inventory status with reason, view QR code modal, inspect scan details

---

## Figure 47: QR Code Modal & Thermal Label Printing (Logs View)

Figure 47: Shows the QR code modal triggered by clicking any QR code thumbnail in the scan logs table. The modal is rendered using the Dialog component and displays an enlarged, scannable QR code generated by the `generateQRCodeDataUrl` utility function, which encodes the scan's prediction values (scan UUID, cultivar, ripeness, spoilage days, confidence, temperature, humidity) into the QR payload. The QR code image is presented at high resolution within the modal content area, accompanied by the scan's key classification details for quick visual verification. The ScanLabelPrint component is integrated within the modal, providing thermal label printing capabilities via the connected Grozziie TP870 S USB printer on the edge station. Operators can specify a label quantity using a number input constrained between 1 and 10 copies and click "Print labels" to dispatch the print job using the `printQRTag` function, which formats the QR data and classification details onto 40mm × 30mm adhesive label templates suitable for produce packaging. The modal also provides a download option to save the QR code as a PNG image file to the local device for external use or archival purposes.

- Route: `/logs` (modal overlay)
- User Type: Operator / Admin
- Main Actions: View enlarged QR code, select label quantity (1–10 copies), dispatch print job to station thermal label printer

---

## Figure 48: Scan Detail Page (Operator Context)

Figure 48: Shows the comprehensive scan evidence view rendered by the ScanDetail component, which fetches the full scan record including camera detections, images, original AI results, status logs, and audit notes. The page layout is organized into logical sections: a header area with a back-navigation arrow, scan metadata (date/time, operator, source), and status badges; a multi-camera evidence grid displaying synchronized captures from all four cameras (Top CAM-001, Left CAM-002, Right CAM-003, Rear CAM-004) rendered using the ScanImage component with the BoundingBoxOverlay component providing toggleable YOLO detection bounding boxes with class labels and per-camera confidence scores displayed as badges; a classification summary section showing detected finger count, cultivar, ripeness stage with colored status badges, and detection confidence percentage; an environmental microclimate telemetry section displaying temperature, relative humidity, and calculated Vapor Pressure Deficit (VPD) in kPa from the Arduino Uno DHT22 sensor readings captured during the scan; a spoilage shelf-life estimation section showing predicted remaining days with RMSE confidence range using the `formatSpoilageDays` and `spoilageDayUnit` utilities; an immutable original AI result comparison panel preserving the unmodified algorithm predictions for auditability; a QR tracking section with an image download button and print tag action using the ScanLabelPrint component; an audit note history section rendered as a chronological list with a Textarea input for adding new notes; and inventory status transition controls enforcing valid state transitions (e.g., "In Stock" → "Sold" / "For Processing" / "Spoiled") with mandatory reason logging via a confirmation dialog and optimistic revision-based conflict detection through the `scanRevision` and `isScanConflict` utilities.

- Route: `/scans/:scanId`
- User Type: Operator
- Main Actions: Inspect multi-angle camera evidence and bounding boxes, review microclimate sensor readings, download QR code, print tag, flag scan for review, log audit notes, transition inventory status

---

## Figure 49: Analytics Page (Operator View)

Figure 49: Shows the operator analytics dashboard presenting visual charts filtered strictly to the logged-in operator's historical activity, powered by the Recharts charting library integrated through the ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, and ChartLegendContent wrapper components. The page provides a date range selector at the top enabling custom analysis periods through predefined range options fetched via `api.analytics`. Summary KPIs are displayed as AppStatsCard components showing total scans, average confidence, and scan trend indicators. The visualization section includes: a ripeness stage distribution PieChart using color-coded segments (Unripe green, Semi Ripe purple, Ripe yellow, Overripe red) with interactive tooltips; cultivar count BarChart with distinct amber tones for Lakatan, Latundan, and Cardaba; a cultivar-ripeness breakdown using a stacked bar composition; a daily scan throughput trendline rendered as a LineChart or ComposedChart tracking scan volume over the selected period; an hourly distribution chart showing scan activity patterns throughout the working day; and a source-based comparison chart when multiple delivery intake origins exist. Each chart configuration uses a typed `ChartConfig` satisfies-pattern ensuring consistent color assignments and label definitions across all visualizations. The data is fetched through `useDashboardResource` with proper loading skeleton states via the ContentSkeleton component.

- Route: `/analytics`
- User Type: Operator
- Main Actions: Adjust date range, inspect personal ripeness distribution, review cultivar counts, analyze daily scan throughput

---

## Figure 50: Inventory Monitoring Page (Operator Context)

Figure 50: Shows the inventory monitoring module summarizing active in-stock produce through computed metrics derived from the ScanContext and InventoryContext. The page filters scans to those with `inventoryStatus === "In Stock"` and `inventoryEligible === true`, then computes inventory statistics in a memoized block. The header area displays AppStatsCard components for total banana hands count, total finger count (aggregated from individual scan `fingerCount` values), and the number of items with unknown remaining shelf life. A source filter dropdown enables narrowing the view to a specific supplier's inventory. Stock breakdown sections group items by ripeness stage (Unripe, Semi Ripe, Ripe, Overripe) and cultivar (Lakatan, Latundan, Cardaba), showing counts, finger totals, and progress bar visualizations relative to total stock. First-In, First-Out (FIFO) handling guidance prioritizes items with the earliest scan timestamps for dispatch. The urgent spoilage alert table is the most prominent section, highlighting items expiring within 2 days or already overdue by using the `remainingStockDays` utility to compute real-time remaining shelf life against the current timestamp, updated every 60 seconds via an interval timer. Spoilage alerts are grouped by intake, cultivar, and ripeness combination using a Map, with each row showing the supplier source, count of affected hands, total fingers, oldest scan date, and the shortest remaining shelf life formatted via the `shelfLifeLabel` utility. Each alert row includes a direct link to the filtered scan log records via `buildScanLogsUrl`, enabling operators to quickly navigate to the affected scan entries for inventory status updates.

- Route: `/inventory`
- User Type: Operator
- Main Actions: Monitor stock counts by cultivar and ripeness, review FIFO dispatch recommendations, inspect 2-day spoilage alerts table

---

## Figure 51: Device Status Page (Operator Context)

Figure 51: Shows the hardware monitoring interface rendered by the DeviceStatus component, displaying the operational health of station peripherals through three distinct panels. The camera connection grid presents each of the four cameras (Top, Left, Right, Rear) as cards with real-time online/offline indicators using green/red Badge components and Wifi/WifiOff icons, with device data sourced from the AdminContext's device registry. The Arduino Uno DHT22 ambient sensor panel displays temperature and humidity readings with a sophisticated freshness-tracking system: each incoming sensor payload includes a `recorded_at` timestamp and `stale_after_seconds` threshold, and the component uses a `latestReading` ref to implement race-condition protection that prevents delayed or out-of-order WebSocket events from replacing newer readings. The sensor reading age is computed relative to performance.now() and displayed in human-readable format (seconds, minutes, or hours) using the `readingAge` utility. The sensor connection state is tracked separately, showing connected/disconnected status. The edge Mini PC host performance metrics panel shows CPU usage with processor name, memory allocation (used/total GB with percentage), SSD disk space (used/total GB with percentage), system uptime formatted as a human-readable duration, and CPU temperature when available from the hardware sensors. The page subscribes to the "devices" and "sensors" WebSocket rooms for real-time updates, with a manual refresh button for on-demand metric polling. Loading states are handled through Skeleton placeholder components during initial data fetch.

- Route: `/devices`
- User Type: Operator
- Main Actions: Verify camera connectivity, inspect live ambient temperature and humidity, monitor edge PC host performance

---

## Figure 52: User Profile and Account Settings (Operator View)

Figure 52: Shows the operator profile page rendered by the Profile component, where users manage personal account details within a structured layout. The profile header section displays the user's avatar with an upload zone supporting drag-and-drop or click-to-select file input constrained to image types up to 2MB, the user's full name, username, and role badge. A theme toggle switch enables users to switch between light and dark visual themes using the ThemeProvider context, with the preference persisted to localStorage. The personal metrics section displays lifetime scan statistics including total scan count, average confidence percentage, and account activity summary. Below the metrics, two action cards provide access to security modals: the "Change Password" card opens a modal for web credential management with current-password verification, and the "Change Kiosk PIN" card opens a modal for updating the 4-digit numeric PIN used on the edge scanning terminal. Each card displays a brief description of its function and a primary action button. The profile information form allows editing the user's display name and saving changes via an API call with success/error toast notifications.

- Route: `/profile`
- User Type: Operator
- Main Actions: Update profile information, upload avatar, toggle theme, launch Change Password modal, launch Change Kiosk PIN modal

---

## Figure 53: Change Password Modal

Figure 53: Shows the self-service password update modal within the user profile, rendered as a Dialog component overlaying the Profile page. The modal form requires the user to enter and verify their current password in the first field before defining and confirming a new permanent password in two subsequent fields. All three input fields feature the same rounded styling and password visibility toggle buttons consistent with the login page design. Client-side validation ensures the new password fields match and meet minimum length requirements before the form submission is enabled. The submission triggers an authenticated API call that verifies the current password server-side before applying the update. Success and error states are communicated through toast notifications from the Sonner library. The modal includes a cancel button to dismiss without changes and a submit button that shows a loading spinner during the API call.

- Route: `/profile` (modal overlay)
- User Type: Operator / Admin
- Main Actions: Verify current password, input new password, confirm new password

---

## Figure 54: Change Kiosk PIN Modal

Figure 54: Displays the modal utilized by warehouse operators to independently manage their secure 4-digit numeric kiosk PIN. The modal employs a 4-slot OTP-style input interface where each digit is entered into an individual input field that automatically advances focus to the next slot on input and supports backspace navigation to the previous slot. The workflow requires three sequential PIN entries: first, the user must verify their existing PIN to confirm their identity; then they enter the desired new 4-digit PIN; and finally they confirm the new PIN by re-entering it. Input validation ensures all PINs are exactly 4 numeric digits and that the new PIN entries match before submission. The verified current PIN is sent alongside the new PIN to the backend API endpoint, which performs server-side current-PIN verification before applying the update. This 4-digit sequence is subsequently used for edge station authentication on the kiosk terminal, where operators authenticate via the touch-friendly keypad instead of typing a full password.

- Route: `/profile` (modal overlay)
- User Type: Operator
- Main Actions: Verify current 4-digit PIN, input new 4-digit PIN, confirm new PIN

---

## Figure 55: Kiosk Idle/Lock Screen (PIN Login)

Figure 55: Shows the primary edge terminal lock screen displayed when the kiosk is idle or locked, rendered by the KioskOperatorSwap component within the Kiosk page. The lock screen is presented as a fullscreen modal overlay and features a grid of registered warehouse operators fetched from a dedicated public API endpoint (`api.auth.kioskOperators()`) that does not require authentication, ensuring the operator selection list is populated even on fresh kiosk sessions without an active JWT token. Each operator is displayed as a selectable card showing their profile avatar (rendered via the Avatar component with an AvatarFallback showing initials), full name, and username. The operator list is filtered to show only Active-status Operator-role accounts, with a fallback to the AdminContext user list if the public endpoint is unavailable. When an operator selects their profile, a touch-friendly numeric keypad appears for 4-digit PIN entry with large touch targets optimized for the kiosk's external display. The PIN is validated against the backend, and upon successful authentication, the operator gains access to the scanning terminal with their identity established for scan attribution and shift tracking.

- Route: `/kiosk` (idle screen)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal (fullscreen kiosk mode)
- Main Actions: Select operator profile, enter 4-digit numeric PIN, unlock scanning terminal

---

## Figure 56: Set New PIN for Newly Created Account (Kiosk)

Figure 56: Captures the initialization prompt presented to a newly registered warehouse operator the first time they sign into the edge kiosk using temporary credentials (`new_account`). When the kiosk PIN authentication detects the `new_account` status flag on the operator's record, the standard scanning interface is replaced with a mandatory PIN setup flow. The interface presents a sequence of input screens: first, the operator enters the temporary PIN that was generated by the administrator during account creation and communicated through the secure handoff process; then the operator defines their personal 4-digit PIN using the touch-friendly numeric keypad; and finally they confirm the new PIN by re-entering it. The 4-slot OTP-style input interface provides clear visual feedback for each entered digit, and validation ensures both new PIN entries match before submission. The operator cannot access the scanning terminal or perform any scans until this initialization step is completed, ensuring every operator has a personally chosen PIN for accountability and security. Forces the operator to define and confirm their personal 4-digit PIN before unlocking the scanning station.

- Route: `/kiosk` (initialization overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Enter temporary PIN, create new 4-digit PIN, confirm new PIN

---

## Figure 57: Set New PIN after Admin Reset (Kiosk)

Figure 57: Shows the recovery interface presented on the kiosk immediately following an administrator-triggered PIN reset (`pin_reset`). When an administrator uses the User Management module to reset an operator's kiosk PIN, the backend generates a new temporary PIN and flags the operator's account with the `pin_reset` status. The next time the affected operator attempts to sign into the kiosk, the system detects this flag and presents a forced PIN recovery flow. The interface mirrors the new-account PIN setup from Figure 56 but is contextually adapted for the recovery scenario: the operator first enters the administrator-issued temporary PIN (which was displayed once in the admin's reset confirmation dialog for physical handoff), then creates a new permanent 4-digit PIN, and confirms it. This workflow ensures that administrator-initiated credential resets are resolved at the point of use, maintaining the principle that only the operator knows their active PIN while providing administrators with the ability to restore access for locked-out personnel.

- Route: `/kiosk` (recovery overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Enter temporary PIN, create new 4-digit PIN, confirm new PIN

---

## Figure 58: Kiosk Interface (Mini PC Scanning Terminal)

Figure 58: Shows the full-screen kiosk interface deployed on the edge Mini PC terminal, rendered by the Kiosk component (the largest page at approximately 920 lines and 49KB). The interface is divided into a main content area and a sidebar. The main area displays the current operator badge showing their avatar and name, a live system clock updated every second via a state interval, and the active delivery intake batch with supplier name and ripening treatment. The centerpiece is a 4-camera live feed preview section using backend-discovered camera devices from `api.cameras.list()`, with angle labels (Top, Left, Right, Rear) mapped from the `cameraAngles` array, and a camera switcher allowing operators to focus on individual camera views. The prominent "Scan Now" button triggers the `startScan` action from ScanContext, which initiates the full pipeline. A "Demo Mode" button provides print calibration functionality for testing the thermal printer without consuming a real scan. The sidebar displays the 5 most recent scans from the active shift with cultivar and ripeness badges, confidence percentages, and timestamp information. Ripeness stages are visually distinguished using emoji indicators: green circle for Unripe, orange circle for Semi Ripe, yellow circle for Ripe, and red circle for Overripe. The interface also includes an operator swap trigger, delivery source selection modal, and detection image modal for reviewing captured images with bounding box overlays.

- Route: `/kiosk`
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Preview camera feeds, select active delivery intake, trigger scan, run demo label print, swap operator, inspect recent scans

---

## Figure 59: Swap Operator Modal (Kiosk)

Figure 59: Shows the rapid shift-handover overlay rendered by the KioskOperatorSwap component (approximately 25KB), allowing operators to switch active accounts at the edge terminal without terminating the current delivery intake session. The modal presents the same operator selection grid as the lock screen (Figure 55), showing avatars and names of all active operators. When a target operator is selected, a 4-digit PIN verification keypad appears for the incoming operator to authenticate. The swap operation uses a dedicated API endpoint that atomically deauthenticates the current operator and establishes a session for the new one, preserving the active delivery intake batch assignment and recent scan sidebar context. This design enables multiple warehouse workers to share a single physical scanning terminal across shift boundaries or concurrent work periods without disrupting the scanning workflow or requiring a full kiosk restart. The incoming operator's identity is immediately reflected in the operator badge and all subsequent scans are attributed to their account.

- Route: `/kiosk` (overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Select new operator profile, enter 4-digit PIN, transfer active scanning shift

---

## Figure 60: Kiosk Source / Delivery Intake Selection Modal

Figure 60: Displays the intake selection dialog rendered as a Dialog component presented to the operator before scanning can begin or when changing the active delivery batch. The modal draws supplier data from the InventoryContext and filters the list to only Active-status suppliers. The operator selects a registered agricultural supplier from a list showing supplier names and selects the ripening treatment type using two clearly labeled toggle options: `Natural` (for bananas ripening without chemical treatment) and `Ethephon` (for bananas treated with the chemical ripening agent). Upon confirmation, the component calls the `startIntake` function from InventoryContext, which creates or selects the active delivery intake batch on the backend, ensuring all subsequent scans maintain strict provenance linking each scan to its supplier origin and treatment method. The `startingIntake` loading state displays a spinner on the confirmation button to prevent duplicate submissions. If no active suppliers are available, the modal communicates this state with an appropriate empty message guiding the operator to contact an administrator.

- Route: `/kiosk` (modal dialog)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Select supplier, choose ripening treatment (`Natural` / `Ethephon`), establish active delivery intake batch

---

## Figure 61: Kiosk Scanning In Progress (4-Stage Pipeline)

Figure 61: Depicts the fullscreen active scanning interface presented on the physical kiosk hardware, visualizing the 4-stage edge AI inspection pipeline implemented in the `execute_scan_pipeline` function (`scan_service.py`). The interface tracks progress through real-time WebSocket events broadcast to the `ROOM_KIOSK` room, with the kiosk frontend consuming `scanState` from ScanContext including `isScanning`, `scanStep`, and `scanProgress` properties. A Progress component renders a determinate progress bar that advances through the pipeline stages: Stage 1 (0–30%) — synchronized parallel image capture across all four cameras (Top CAM-001, Left CAM-002, Right CAM-003, Rear CAM-004) via `camera_manager.capture_all()` paired with serial polling of the Arduino Uno DHT22 ambient temperature and humidity through the `sensor_reader`; Stage 2 (30–50%) — banana pre-detection using a base COCO YOLO model (`banana_pre_detector`) to verify banana presence before proceeding, followed by Ultralytics YOLO26 object detection (`banana_classifier`) for per-camera finger counting and cultivar/ripeness bounding box localization with configurable confidence thresholds; Stage 3 (50–80%) — multi-camera confidence-weighted fusion through the `fusion_engine.fuse()` function with cross-view botanical harmonization that normalizes dissenting per-camera cultivar detections to the consensus classification when no conflict is flagged, and Magnus-Tetens Vapor Pressure Deficit (VPD) feature engineering via the `calc_vpd` function; and Stage 4 (80–100%) — Random Forest Regression (RFR) spoilage shelf-life calculation through the `spoilage_predictor`. Each stage broadcasts granular WebSocket events (`SCAN_STARTED`, `SCAN_CAPTURING`, `SCAN_CAPTURED`, `SCAN_DETECTING`, `SCAN_DETECTED`, `SCAN_ANALYZING`, `SCAN_COMPLETED`) that update the kiosk UI in real-time. The entire pipeline is protected by a `station_lock` and `coordinator` to prevent concurrent scan operations, and any `ModelInferenceError` (such as "No banana found") is gracefully communicated to the operator.

- Route: `/kiosk` (active scan overlay)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Monitor live scan execution, observe multi-camera capture status

---

## Figure 62: Kiosk Scan Result & Validation

Figure 62: Shows the immediate post-scan result panel on the kiosk interface, displayed after the scan pipeline completes and `lastResult` is populated in the scanState from ScanContext. The result panel presents a structured summary of the AI classification: predicted cultivar (Lakatan, Latundan, Cardaba) with an AppStatusBadge component, ripeness stage (Unripe, Semi Ripe, Ripe, Overripe) with a corresponding emoji indicator and colored badge, detected finger count shown with a Hand icon, and detection confidence percentage displayed with a Target icon. Environmental sensor data is presented with labeled values showing temperature ($T$), relative humidity ($RH$), and calculated Vapor Pressure Deficit ($VPD$) in kPa. The spoilage shelf-life estimation displays predicted remaining days formatted with `formatSpoilageDays` and unit label from `spoilageDayUnit`, including the RMSE confidence range. A multi-camera thumbnail carousel is rendered below the classification data, showing captures from all four cameras with a toggle for bounding box visibility using Eye/EyeOff icons and the `showKioskBoxes` state, with the BoundingBoxOverlay component rendering detection rectangles over each image. The component checks for cultivar camera conflicts using the `cultivarCameraConflict` utility and highlights disagreements visually. The auto-print status is tracked via the KioskPrintStatus component, which monitors the Grozziie TP870 S thermal printer's output of a 40mm × 30mm adhesive QR label. Two primary touch buttons enable the operator to "Accept" the scan into inventory or "Flag for Review" using the `flagScan` function, with the `scanAction` state tracking which action was taken and the `flaggingScan` state preventing double-submissions.

- Route: `/kiosk` (post-scan panel)
- User Type: Operator
- Deployment Context: Dedicated edge Mini PC terminal
- Main Actions: Review classification and spoilage predictions, inspect bounding boxes, verify label printing, accept scan into inventory, flag scan for review

---

## Figure 63: Dashboard (Admin View)

Figure 63: Shows the administrator dashboard providing enterprise-wide visibility, using the same Dashboard component as the operator view but with role-conditional rendering that expands the displayed information to span all operators and system activity. The dashboard subscribes to the same WebSocket rooms ("dashboard" and "devices") and midnight-boundary refresh logic, but the admin-scoped API response includes aggregate metrics across all operators rather than individual totals. The display shows aggregate scan metrics encompassing total system-wide scans, active delivery intake totals across all sources, overall AI confidence averages computed from the full scan population, and flagged scan counts requiring quality control review. A system-wide recent scan timeline replaces the operator-personal feed, showing scans from all operators with operator name attribution and colored role badges. Real-time WebSocket alerts include system-level events such as hardware status changes, classification conflicts detected across cameras, and automated data retention notices. Direct shortcut cards link to all management modules including User Management, Delivery Intakes, Supplier Management, Quality Control, Activity Log, and System Configuration, in addition to the shared modules (Logs, Analytics, Inventory, Device Status).

- Route: `/dashboard`
- User Type: Admin
- Main Actions: Monitor enterprise KPIs, track active delivery intakes, review quality alerts, navigate to management modules

---

## Figure 64: Global Notification Center (Admin View)

Figure 64: Shows the administrative notification center accessible from the navigation header, extending the operator notification functionality (Figure 45) with system-wide scope. The AppNotifications component receives the admin role context and consolidates operational alerts from across the entire system rather than filtering to a single operator's activity. Notification categories include: hardware status notifications such as camera disconnects (detected via the Device model's online status changes) and DHT22 sensor communication timeouts from the serial reader; quality control alerts including classification conflicts (triggered when the fusion engine's `cultivar_conflict` flag is set), low-confidence scans that fall below the configured review threshold, and operator-flagged scans requiring administrative attention; intake delivery updates such as new batch creations and bulk status transitions; and automated data retention notices from the capture cleanup service. Each notification carries a severity indicator, timestamp, and contextual navigation link. The notification center provides the same mark-as-read and clear-all actions as the operator view, but operates on the system-wide notification pool, ensuring administrators have comprehensive awareness of all operational events occurring across the scanning station.

- Route: Global header across protected routes
- User Type: Admin
- Main Actions: Review system-wide alerts, navigate to source records, mark notifications as read, clear notifications

---

## Figure 65: Logs and Scan History (Admin View)

Figure 65: Shows the administrative scan history page displaying all organization-wide scans across all operators, using the same Logs component as the operator view but with admin-specific enhancements. The most significant addition is an operator filter dropdown populated from the user registry, allowing administrators to isolate scan records by any specific operator's activity alongside the standard filter suite (cultivar, ripeness, intake source, inventory status, Asia/Manila calendar date, and attention card filters). The attention cards display system-wide totals: At-Risk items expiring within 2 days, scans Pending Review (either flagged by operators or below the confidence threshold), and Auto-approved scans that passed the confidence threshold without requiring human review. The table includes additional columns visible only to administrators, such as the operator attribution column showing which operator performed each scan. Live WebSocket reconciliation operates on the system-wide scan feed, ensuring new scans from any operator appear in real-time and existing rows update when inventory status changes or authoritative overrides are applied. The inline inventory status update dialogs enforce mandatory reason logging with the same revision-based conflict detection system, and the CSV/XLSX export functionality uses the `collectScanPages` utility to paginate through all server-side results before generating the download file. QR code modals with multi-label thermal printing (1–10 copies) remain available on every row via the ScanLabelPrint component.

- Route: `/logs`
- User Type: Admin
- Main Actions: Filter scans across all operators, export CSV/XLSX, update inventory statuses with reason, view QR modal & print batch labels, inspect scan details

---

## Figure 66: Scan Detail Page (Admin Context)

Figure 66: Shows the detailed scan view in administrative context, rendered by the same ScanDetail component as the operator view but with additional admin-only controls enabled through role-conditional rendering. The page combines the full 4-camera visual evidence grid with BoundingBoxOverlay components displaying toggleable YOLO detection rectangles, per-camera confidence scores, and inference time metrics. The DHT22 microclimate readings section shows captured temperature and humidity alongside the calculated VPD using the `calc_vpd` formula. Spoilage shelf-life range is displayed with RMSE bounds. The immutable original AI result comparison panel (sourced from the `scan_original_ai_result` model) preserves the unmodified algorithm predictions separately from any subsequent overrides, enabling administrators to see exactly what the AI predicted versus any human corrections. QR tag management includes both image download and thermal print actions. The admin-exclusive "Edit Scan Data" override mode (toggled via the `editMode` state) unlocks form controls for correcting cultivar (Select dropdown with Lakatan, Latundan, Cardaba options), ripeness (Select dropdown with Unripe, Semi Ripe, Ripe, Overripe options), finger count (NumberField component), or source assignment. Each override requires a mandatory audit reason logged in the `editReason` Textarea field. The override submission uses optimistic revision locking through the `scanRevision` utility, which attaches the scan's current `revision` number to the update request; if another user modified the record concurrently, the backend returns a conflict response detected by `isScanConflict`, and the `scanRetryAction` utility provides a recovery mechanism. The AppChangePreview component shows a visual diff of proposed changes before confirmation.

- Route: `/scans/:scanId`
- User Type: Admin
- Main Actions: Inspect multi-angle evidence and bounding boxes, download QR code, print tag, apply authoritative classification overrides, log audit notes, update inventory status

---

## Figure 67: Analytics Page (Admin View)

Figure 67: Shows the enterprise analytics dashboard providing organization-level business intelligence, rendered by the same Analytics component with admin-scoped API responses that aggregate data across all operators and delivery sources. The page features all the chart types available in the operator view (ripeness distribution PieChart, cultivar BarChart, daily scan trendline, hourly distribution, confidence distribution) but computed over the entire organization's scan history. Additional admin-specific features include: custom date range filtering with predefined range shortcuts (today, last 7 days, last 30 days, custom) powered by the `AnalyticsRange` type; source-based comparisons across intake batches using the source filter dropdown populated from all registered suppliers; cultivar distribution charts with breakdown by ripeness stage using stacked bar compositions in the `cultivarRipenessChartConfig`; and a comprehensive operator performance table rendered via the AppDataTable component, evaluating each operator's throughput (total scans), average confidence percentage, review rate (proportion of scans flagged or below threshold), and activity period. The chart color schemes use consistent domain-specific assignments: green for Unripe, purple for Semi Ripe, yellow for Ripe, red for Overripe; amber tones for Lakatan, lighter amber for Latundan, dark amber for Cardaba. Each chart supports interactive tooltips via ChartTooltipContent and color-coded legends via ChartLegendContent.

- Route: `/analytics`
- User Type: Admin
- Main Actions: Select custom date ranges, filter by intake source, compare operator throughput, inspect cultivar and ripeness distributions

---

## Figure 68: Inventory Monitoring Page (Admin Context)

Figure 68: Shows the enterprise inventory monitoring module rendered by the same Inventory component with admin-scoped data access, displaying active stock levels across all supplier sources rather than being limited to the current operator's scans. The page aggregates in-stock produce counts (hands and fingers) by cultivar and ripeness stage using the same memoized computation logic as the operator view, but applied to the full organization-wide scan dataset. First-In, First-Out (FIFO) queue guidance is generated from the chronologically sorted in-stock items, prioritizing the oldest scans for dispatch recommendations. The source filter dropdown is populated with all registered suppliers, enabling administrators to isolate inventory health by individual supplier or view the combined picture. The critical 2-day spoilage warnings section highlights items expiring within 2 days or already overdue, grouped by intake-cultivar-ripeness combination with aggregate hand counts, total finger counts, shortest remaining shelf life, and oldest scan date. Each spoilage alert row provides a direct link to the filtered scan log records using `buildScanLogsUrl` with the appropriate source, ripeness, and attention parameters pre-populated, allowing administrators to quickly navigate to the specific affected records and perform bulk or individual inventory status transitions.

- Route: `/inventory`
- User Type: Admin
- Main Actions: Monitor enterprise stock health, evaluate FIFO dispatch priorities, inspect 2-day spoilage alert table, filter by supplier source

---

## Figure 69: Device Status Page (Admin Context)

Figure 69: Shows connected device diagnostics rendered by the DeviceStatus component with admin-level system metrics access. The 4-camera connection health grid displays each registered device from the AdminContext's device registry with online/offline status indicators, device IDs, camera labels, and DirectShow enumeration status reflecting the USB camera discovery results from the `camera_discovery` service on the backend. The Arduino Uno DHT22 serial communication panel extends the operator view with additional metrics about the serial loop: the `sensor_reader` service continuously polls the Arduino over USB serial at the configured baud rate (default 9600), and the component tracks reading freshness with sub-second precision using the `performance.now()` timing API and the `stale_after_seconds` threshold from the server payload. The edge Mini PC host performance telemetry panel provides granular metrics fetched from the `api.system.metrics()` endpoint: CPU usage percentage with the processor name string, memory allocation showing used versus total gigabytes with a Progress bar for visual representation, SSD disk space with used/total GB and percentage, system uptime as a formatted duration string, and CPU temperature in degrees Celsius when hardware sensor data is available (shown as null when the sensor is unsupported). The page subscribes to "devices" and "sensors" WebSocket rooms for live updates and provides a manual refresh button with a RefreshCw icon and loading spinner.

- Route: `/devices`
- User Type: Admin
- Main Actions: Monitor camera array connectivity, check DHT22 sensor communication, review edge server host resource metrics

---

## Figure 70: User Management (Admin)

Figure 70: Shows the user administration module for governing operator and administrator accounts, rendered by the UserManagement component. The page header includes a search input for filtering users by name or username and an "Add User" primary action button. The user registry is displayed as a table using the AppDataTable component with columns for username, full name, role badge (styled differently for Admin and Operator roles), status badge (Active shown in green, Inactive in muted gray), and an actions column. Filter controls include role dropdown filters (Admin, Operator, All) and status filters (Active, Inactive, All) for narrowing the displayed user list. The actions column provides contextual operations per user: Edit User opens a modal for modifying the user's full name and role; Toggle Status activates or deactivates the account with a confirmation dialog explaining the impact; Reset Password triggers the password reset flow that generates a new temporary credential; and Reset PIN triggers the kiosk PIN reset flow for operators. The table is sorted and paginated for efficient management of larger user populations.

- Route: `/admin/users`
- User Type: Admin
- Main Actions: Search/filter user registry, register new user, edit user details, activate/deactivate account, initiate password reset, initiate kiosk PIN reset

---

## Figure 71: Create User with Temporary Credentials Handoff Dialog

Figure 71: Shows the initial account creation form used by administrators to register new personnel, rendered as a Dialog overlay on the User Management page. The form collects the new user's username, full name, and role selection (Admin or Operator) with status defaulting to Active. Upon form submission, the backend generates two temporary credentials: an auto-generated secure temporary password for web dashboard authentication and an auto-generated 4-digit operator kiosk PIN for edge terminal access. These credentials are returned in the API response and displayed in a one-time secure handoff dialog that appears immediately after successful account creation. The handoff dialog prominently presents the temporary password and PIN in large, readable text with copy-to-clipboard buttons, along with clear instructions that these credentials will not be shown again after the dialog is closed. The dialog emphasizes that the administrator must physically communicate these credentials to the employee, who will be forced to change them upon first login (web) or first kiosk sign-in (PIN). This workflow ensures secure credential distribution while maintaining the principle that temporary credentials are visible only once during the administrative handoff process.

- Route: `/admin/users` (dialog overlay)
- User Type: Admin
- Main Actions: Input username, full name, role, and status; view auto-generated temporary password and 4-digit PIN; securely hand off credentials to employee

---

## Figure 72: Reset User Password Dialog

Figure 72: Displays the administrative action dialog to reset an existing user's password, rendered as an AlertDialog component with a confirmation step. The dialog warns the administrator about the impact of the password reset, explaining that the target user will be required to create a new password upon their next login. Upon confirmation, the backend generates a secure temporary password and returns it in the response. The confirmation dialog then transitions to display the auto-generated temporary password in a prominent, copyable format for the administrator to record and physically communicate to the affected user. The dialog includes a clear warning that the temporary password will not be displayed again after closing. When the affected user next attempts to log in with the temporary password, the system detects the `password_reset` flag and forces the password change flow described in Figure 43. This mechanism provides administrators with the ability to restore access for personnel who have forgotten their credentials while maintaining the security principle that only the individual user knows their permanent password.

- Route: `/admin/users` (dialog overlay)
- User Type: Admin
- Main Actions: Confirm password reset, view auto-generated temporary password, securely hand off credential

---

## Figure 73: Reset Operator Kiosk PIN Dialog

Figure 73: Represents the administrative recovery dialog to reset an operator's 4-digit kiosk access PIN, rendered as an AlertDialog component with a confirmation step similar to the password reset flow. The dialog explains that the affected operator will be prompted to create a new PIN the next time they sign into the kiosk terminal. Upon confirmation, the backend generates an auto-generated temporary 4-digit PIN and returns it in the response. The confirmation dialog displays the temporary PIN in a large, copyable format with instructions for the administrator to communicate it to the operator through a secure physical handoff. The dialog warns that the temporary PIN is displayed only once and cannot be retrieved after closing. When the operator next attempts to sign into the kiosk terminal, the system detects the `pin_reset` flag on their account and presents the mandatory PIN recovery flow described in Figure 57, requiring the temporary PIN for verification before establishing a new permanent PIN. This enables administrators to assist operators who have forgotten their kiosk access credentials without compromising the PIN security model.

- Route: `/admin/users` (dialog overlay)
- User Type: Admin
- Main Actions: Confirm PIN reset, view auto-generated temporary 4-digit PIN, hand off PIN for kiosk sign-in

---

## Figure 74: Delivery Intake Management (Admin)

Figure 74: Shows the delivery intake management page rendered by the DeliveryIntake component, used to govern produce batch arrivals and maintain supply chain provenance. The page lists all intakes in a table with columns for supplier name, harvest date, ripening treatment (`Natural` / `Ethephon`) displayed with distinctive badges, associated scan counts showing how many individual scans belong to each intake batch, and lifecycle status (`Active` / `Depleted`) with colored AppStatusBadge components. A search input enables filtering by supplier name, and status filters allow isolating active or depleted batches. The "Create New Intake" action opens a dialog for registering a new delivery intake by selecting a supplier from the active supplier registry and specifying the ripening treatment type. Each intake row provides actions to print batch QR code labels for pallet containers using the thermal printer integration, and a critical "Bulk Update" dropdown menu that enables administrators to initiate a bulk inventory status transition for all scans associated with the selected intake batch. The page maintains a clear audit trail of intake creation timestamps, ensuring every scan's provenance chain is traceable from the supplier source through the scanning process to the final inventory disposition.

- Route: `/admin/delivery-intakes`
- User Type: Admin
- Main Actions: Search and filter intake batches, register new delivery intake, monitor batch lifecycle, print batch QR labels, trigger bulk inventory updates

---

## Figure 75: Bulk Update Status Menu (Delivery Intake)

Figure 75: Demonstrates the administrative bulk inventory management action rendered as a DropdownMenu component on each intake row, allowing simultaneous reassignment of an entire delivery intake batch's inventory status. The dropdown presents the available target statuses (In Stock, For Processing, Sold, Spoiled) as DropdownMenuItem entries, each with an appropriate icon. When a target status is selected, a confirmation dialog appears displaying the number of scans that will be affected by the transition. The confirmation dialog includes a mandatory audit reason Textarea field that the administrator must complete before the bulk operation can proceed, ensuring every mass status change is documented with a justification. The bulk update API call includes revision conflict resolution logic: if any individual scan within the batch has been modified by another user since the page was loaded, the system detects the revision mismatch and reports which scans could not be updated, preventing silent data overwrites. This mechanism enables efficient management of entire delivery batches — for example, marking an entire pallet of bananas as "Sold" after a wholesale transaction or flagging an entire intake as "Spoiled" when quality issues are discovered at the batch level.

- Route: `/admin/delivery-intakes` (dropdown action)
- User Type: Admin
- Main Actions: Select target inventory status for entire intake batch, input mandatory change reason, commit bulk transition

---

## Figure 76: Terminal Status Warning Confirmation Dialog (Delivery Intake)

Figure 76: Captures the critical safeguard dialog rendered as an AlertDialog that pauses bulk inventory operations when selecting irreversible terminal statuses (Sold, Spoiled). This additional confirmation layer appears after the initial bulk update confirmation from Figure 75 when the selected target status represents a terminal state from which inventory items cannot be transitioned back. The dialog displays a prominent warning icon with AlertTriangle styling, the affected scan count showing exactly how many individual scan records will be permanently moved to the terminal status, and an explicit statement that this action marks these items as permanently disposed and cannot be reversed. The administrator must click a clearly labeled destructive-styled confirmation button to proceed, or cancel to return to the intake management view without changes. This dual-confirmation pattern prevents accidental produce retirement by requiring two distinct acknowledgments — first the reason-logged confirmation and then the terminal-status warning — before the irreversible bulk status update is committed to the database.

- Route: `/admin/delivery-intakes` (alert dialog)
- User Type: Admin
- Main Actions: Review affected scan volume, acknowledge permanent status transition, confirm bulk status update

---

## Figure 77: Supplier Management (Admin)

Figure 77: Shows the supplier management module rendered by the SupplierManagement component, maintaining the agricultural grower directory that feeds into the delivery intake and scan provenance systems. The page displays a table of farm suppliers with columns for supplier name, contact person, phone number, and active/inactive status with colored badges. A search input enables filtering by supplier name or contact person, and a status filter dropdown allows isolating active or inactive suppliers. Management actions include "Add New Supplier" which opens the creation modal (Figure 78), row-level "Edit" buttons opening the edit modal (Figure 79), and "Toggle Status" actions for activating or deactivating suppliers with a confirmation dialog (Figure 80). The supplier registry directly feeds the kiosk's delivery intake selection modal (Figure 60), meaning deactivating a supplier removes them from the intake creation options while preserving historical references in existing intake batches and scan records. Active suppliers are highlighted with green status badges while inactive suppliers show muted gray badges.

- Route: `/admin/suppliers`
- User Type: Admin
- Main Actions: Search supplier registry, filter by status, register new supplier, edit supplier details, toggle supplier activation

---

## Figure 78: Add New Supplier Modal

Figure 78: Shows the data entry form rendered as a Dialog overlay used to onboard a new agricultural supplier or farm entity into the system. The form contains three input fields: Supplier Name (required, with unique-name validation against existing suppliers in the registry), Contact Person (required, the name of the primary farm contact), and Phone Number (required, the contact phone number). The supplier name uniqueness is validated on the frontend by checking against the loaded supplier list, and the backend enforces the constraint through database-level unique indexing. The form submit button shows a loading spinner during the API call and is disabled until all required fields are populated. Upon successful creation, a success toast notification confirms the new supplier has been added, and the supplier list automatically refreshes to include the new entry. The newly created supplier immediately becomes available in the kiosk's delivery intake selection modal for operators to associate with incoming produce batches.

- Route: `/admin/suppliers` (modal overlay)
- User Type: Admin
- Main Actions: Input supplier name, contact person, and phone number; validate uniqueness; save to registry

---

## Figure 79: Edit Supplier Modal

Figure 79: Depicts the data modification screen rendered as a Dialog overlay that an administrator uses to maintain the accuracy of supplier records. The modal pre-populates the form fields with the selected supplier's current data: supplier name (read-only to preserve referential integrity with existing intake batches), contact person name, and phone number. The administrator can adjust the contact details as business relationships evolve — for example, when a farm's primary contact person changes or when contact phone numbers are updated. The form includes the same validation rules as the creation form, and the submit button transitions to a loading state during the API call. Changes are persisted immediately to the database, and the supplier list view refreshes to reflect the updated information. A cancel button allows dismissing the modal without saving changes.

- Route: `/admin/suppliers` (modal overlay)
- User Type: Admin
- Main Actions: Update supplier contact name and phone details, save modifications

---

## Figure 80: Deactivation Confirmation Dialog (Supplier)

Figure 80: Displays the protective confirmation modal rendered as an AlertDialog, safeguarding the supplier registry by ensuring active farm suppliers are not accidentally suspended or removed from intake selection. When an administrator clicks the deactivation action for an active supplier, this dialog appears with a warning message explaining the consequences: deactivating the supplier will remove it from the available options when creating new delivery intakes on the kiosk, meaning operators will no longer be able to associate new incoming produce batches with this supplier. The dialog preserves historical data by clarifying that existing intake records and scan provenance linked to this supplier will remain intact and unaffected. The confirmation requires an explicit click on a clearly labeled deactivation button, while a cancel option returns the administrator to the supplier management view. For suppliers currently associated with active intake batches, the warning may include additional context about ongoing operations that reference the supplier.

- Route: `/admin/suppliers` (alert dialog)
- User Type: Admin
- Main Actions: Confirm supplier deactivation, review warning on intake routing

---

## Figure 81: Quality Control (Admin)

Figure 81: Shows the dedicated quality control inspection queue rendered by the QualityControl component (approximately 920 lines and 44KB), presenting banana scans requiring human oversight. The queue is populated from the full scan dataset filtered to items matching one of three conditions: low vision confidence (below the configurable `config.confidenceThreshold`), cross-camera classification conflicts (detected via the fusion engine's `cultivar_conflict` flag indicating camera disagreement on cultivar identification), or manual operator flags (set when an operator clicks "Flag for Review" on the kiosk). The page features four filter tabs: "All" showing all scans, "Flagged" showing operator-flagged items, "Low Confidence" filtering by confidence below threshold, and "Overridden" showing scans that have already received administrative corrections. A source filter dropdown enables narrowing by supplier, and a search field supports keyword matching against scan IDs, operator names, cultivars, and source names. The scan list is displayed using AppDataTable with sortable columns and paginated with a configurable page size of 15 items. Each row displays multi-camera thumbnails using the ScanImage component, detected bounding boxes via BoundingBoxOverlay, AppStatusBadge components for cultivar and ripeness, DHT22 temperature and humidity readings with Thermometer and Droplets icons, and calculated VPD. Clicking any row opens the detailed review modal (Figure 82), and the ExportDropdown enables CSV/XLSX export of the filtered quality queue.

- Route: `/admin/quality`
- User Type: Admin
- Main Actions: Filter quality queue by "Flagged", "Low Confidence", or "Overridden"; open review modal; approve verified scans

---

## Figure 82: Scan Details Review Modal (Quality Control)

Figure 82: Shows the focused review modal rendered as a Dialog component, utilized by administrators to meticulously inspect individual scan captures from the quality control queue. The modal header displays the scan ID, date/time, operator name, and supplier source information. The central area presents a multi-view camera evidence section where each camera (identified by `camera_id` from the recorded detections and images) is displayed with its captured image overlaid with the BoundingBoxOverlay component rendering YOLO detection rectangles. Camera views are dynamically constructed from the `recordedCameraIds` array, combining unique camera IDs from both the `images` and `detections` arrays of the selected scan. Each camera view shows per-camera confidence scores as numeric badges, detected cultivar and ripeness values, and the inference time in milliseconds. The immutable original AI predictions section preserves the algorithm's unmodified output for comparison against the current (potentially overridden) values, enabling administrators to verify whether previous corrections were appropriate. Microclimate telemetry displays the temperature, humidity, and VPD readings captured during the scan. The modal provides an "Approve" action for verified scans using the `acceptScan` function, which clears the flagged status and confirms the classification as accurate. From this modal, administrators can also launch the edit mode (Figure 83) for authoritative overrides when the AI classification requires correction.

- Route: `/admin/quality` (modal overlay)
- User Type: Admin
- Main Actions: Inspect multi-angle camera evidence and bounding boxes, compare original AI predictions, review sensor readings

---

## Figure 83: Edit Scan Data / Authoritative Override Mode

Figure 83: Shows the authoritative override interface activated when an administrator enters edit mode on a scan, accessible from both the Quality Control review modal and the Scan Detail page. The edit mode is toggled via the `editMode` state, and upon activation, the component captures the current scan values as a baseline in the `editBaseline` state for change-preview purposes. The override form presents Select dropdowns for correcting cultivar (Lakatan, Latundan, Cardaba), ripeness stage (Unripe, Semi Ripe, Ripe, Overripe), a NumberField for finger count adjustment (tracked by the `fingerCountEdited` flag to distinguish intentional zero values from untouched fields), and a source assignment dropdown populated from active intake sources. The AppChangePreview component renders a side-by-side visual diff showing the original values versus the proposed corrections, highlighted with colored indicators for changed fields. A mandatory justification Textarea (`editReason`) requires the administrator to document why the override is being applied — for example, "Camera angle caused misclassification" or "Operator confirmed cultivar identity visually." The save action uses the `scanWrite` utility with optimistic revision locking via `scanRevision`, which attaches the scan's current `revision` number to the update request. If another user modified the record concurrently, the backend returns a conflict response detected by `isScanConflict`, and the component displays a `writeFailure` message with a recovery action via `scanRetryAction` that allows the administrator to reload the latest version and reapply their corrections. The `recoveringWrite` state tracks active conflict recovery, and `pendingWrite` prevents duplicate submissions. The correction is permanently logged in the audit trail with the administrator's identity, timestamp, and stated reason.

- Route: `/admin/quality` and `/scans/:scanId` (modal overlay)
- User Type: Admin
- Main Actions: Select corrected cultivar, ripeness stage, finger count, or source; input mandatory justification reason; save authoritative correction

---

## Figure 84: Activity Log (Admin)

Figure 84: Shows the activity log screen rendered by the ActivityLog component, recording all user and system actions for security auditing and compliance. The page displays a server-paginated table built with AppDataTable, listing events in reverse chronological order with columns for timestamp (formatted in Asia/Manila timezone), user identity (username with avatar fallback), action category (e.g., login, logout, scan_created, scan_overridden, user_created, user_updated, config_changed, password_reset, pin_reset, bulk_status_update), detailed description of the action with contextual parameters, and client IP address for security audit trail purposes. The table supports text search across action descriptions and user identifiers, and a dropdown filter enables isolating events by action type. The page header includes summary metrics for the last 24 hours, showing total event count and breakdowns by category, providing administrators with a quick overview of system activity patterns. A CSV export button enables downloading the full audit log for external compliance reporting and archival. The activity log is automatically populated by the backend's ActivityLog model, which records entries as side effects of authenticated API operations throughout the system, ensuring comprehensive coverage of all significant user interactions and administrative actions without requiring manual logging by individual modules.

- Route: `/admin/activity`
- User Type: Admin
- Main Actions: Search audit events, filter by action type and user, review 24-hour summary metrics, export audit logs as CSV

---

## Figure 85: System Configuration - Overview (Admin)

Figure 85: Shows the consolidated system configuration portal rendered by the SystemConfig component (approximately 586 lines and 36KB), organizing station settings into four tabs using the Tabs component from Radix UI: Scanner Configuration, AI Settings, Storage Management, and Power Management. The tab navigation is rendered as a horizontal TabsList with TabsTrigger elements, and the active tab's content is displayed below in a TabsContent panel. The page maintains local configuration state synchronized with the server configuration via the AdminContext's `config` object, with change detection logic that compares `localConfig` against the server values to enable or disable the save button. A top-level save button persists all modified settings to the backend with a loading spinner during the API call. The page also monitors the station's maintenance state through periodic 5-second polling of `api.config.maintenance()`, which returns a MaintenanceStatus object. When the maintenance state is not "ready" (e.g., during an active shutdown or restart drain), configuration controls are disabled to prevent conflicting operations. The configuration change detection uses deep comparison for array values (camera device IDs) and simple equality for scalar values (confidence threshold, data retention toggle), with a ref-based mechanism to preserve user edits when the server configuration is refreshed externally.

- Route: `/admin/config`
- User Type: Admin
- Main Actions: Navigate configuration tabs, monitor maintenance state, save global station settings

---

## Figure 86: Scanner Configuration & Camera Calibration

Figure 86: Displays the hardware setup panel within the Scanner Configuration tab, used by administrators to manage the USB camera array. The panel integrates the `useCameraDiscovery` hook, which triggers the backend `camera_discovery` service to enumerate connected USB cameras via DirectShow (Windows) or Video4Linux (Linux) enumeration through the `cv2-enumerate-cameras` library. Discovered cameras are listed with their device index numbers and hardware names, and the CameraDevicePicker component allows mapping each discovered device index to a physical camera position in the 4-slot array (Top CAM-001, Left CAM-002, Right CAM-003, Rear CAM-004). Each camera slot can be assigned a specific USB device ID through an inline edit interface with Edit2 icons, where the administrator enters the integer device index and confirms. The CameraCalibrationModal component provides a live preview feed from each camera by requesting a snapshot from the backend's camera streaming endpoint, allowing administrators to verify lens focus, lighting conditions, and proper banana bunch placement before operational use. The calibration preview helps ensure each camera angle provides clear, well-lit images suitable for the YOLO detection model's inference requirements. Changes to camera slot assignments are saved as part of the unified configuration save operation.

- Route: `/admin/config` (Scanner Configuration tab)
- User Type: Admin
- Main Actions: Discover connected camera indices, map physical camera positions, launch live camera calibration preview modal

---

## Figure 87: AI Settings (Confidence Threshold Calibration)

Figure 87: Depicts the machine learning configuration interface within the AI Settings tab, where administrators calibrate the review confidence threshold that governs the automatic triage of scan results. The primary control is a Slider component rendered from 0% to 100% that sets the `confidenceThreshold` value in the system configuration. This threshold establishes the certainty level the YOLO vision model must satisfy on the fused multi-camera result to auto-accept a scan into inventory versus routing it to the Quality Control queue for human review. When a scan's fused confidence score falls below this threshold, the scan is automatically flagged for administrative review and appears in the Quality Control queue (Figure 81). The current threshold value is displayed as a percentage alongside the slider, and a descriptive label explains the behavior: higher thresholds route more scans to review (stricter quality control but more manual work), while lower thresholds auto-accept more scans (faster throughput but potentially less accurate). The threshold value is also used during the scan pipeline's fusion step (`review_confidence_threshold = config.confidence_threshold / 100.0`) and affects the pre-fusion confidence floor applied to individual camera detections. Changes take effect after saving the configuration and apply to all subsequent scans.

- Route: `/admin/config` (AI Settings tab)
- User Type: Admin
- Main Actions: Adjust detection review confidence threshold slider, save threshold configuration

---

## Figure 88: Storage Management & Station Backup / Restore

Figure 88: Shows the administrative data management tools within the Storage Management tab, combining three operational capabilities. The automated capture retention cleanup section provides a toggle switch for the `dataRetentionEnabled` configuration flag, which when enabled, activates the `capture_cleanup` service to automatically remove expired camera capture image files from the `captures/` directory after the configured retention period (default 30 days), freeing disk space on the edge Mini PC. The CSV export section offers an ExportDropdown component that triggers a server-side flat-file export of scan activity data, generating a comprehensive CSV file downloaded through the browser. The station backup and restore section is rendered by the StationBackupControls component (approximately 9KB), which provides the ability to generate typed system backup archives containing configuration snapshots, database records, and metadata with SHA-256 validation checksums. The backup archives follow versioned schemas (`archive_schema_v1.json`, `archive_schema_v2.json`, `archive_schema_v3.json`) maintained in the backend services directory, ensuring forward compatibility. The restore functionality accepts a previously generated archive file, validates its SHA-256 integrity, and restores the station configuration to the archived state. The `archiveBusy` state disables other configuration controls during backup/restore operations to prevent conflicting modifications.

- Route: `/admin/config` (Storage Management tab)
- User Type: Admin
- Main Actions: Toggle automated capture retention cleanup, export scan data CSV, create typed system backup archive, restore configuration archive

---

## Figure 89: Power Management & System Maintenance Controls

Figure 89: Captures the remote station operations view within the Power Management tab, where administrators observe terminal uptime and trigger controlled operating system power commands. The uptime display shows the edge Mini PC's running time as a human-readable duration string sourced from the system metrics endpoint. Two primary action buttons — "Shutdown" and "Restart" — each trigger an AlertDialog confirmation workflow before executing. The shutdown dialog (toggled by `showShutdownDialog`) warns about the impact of powering off the station and requires explicit confirmation, while the restart dialog (toggled by `showRestartDialog`) explains the temporary service interruption. The power commands are coordinated by a backend maintenance state machine implemented in the `maintenance_state` and `power_control` services, which transitions through states to drain active scan operations before executing the power command, preventing data corruption from interrupted scan pipelines. The `maintenance` status is polled every 5 seconds and displayed with visual state indicators, disabling power buttons when an operation is already in progress. The power command execution uses the `power_control` service with cross-platform subprocess handling (including the `getattr(subprocess, 'CREATE_NO_WINDOW', 0)` fix for macOS/Linux compatibility). The `powerPending` and `powerAccepted` states track the command lifecycle, and a recovery password field may appear if the maintenance system requires authentication for power operations.

- Route: `/admin/config` (Power Management tab)
- User Type: Admin
- Main Actions: Monitor station uptime, initiate controlled Mini PC shutdown, initiate controlled Mini PC restart

---

## Figure 90: User Profile and Account Settings (Admin View)

Figure 90: Shows the administrator profile page rendered by the same Profile component as the operator view, with role-conditional adjustments. The administrator can manage account details including full name editing with API persistence, upload a custom profile avatar (supporting image files up to 2MB with drag-and-drop or click-to-select file input), and toggle between dark and light visual themes with the preference stored in localStorage via the ThemeProvider. The administrative activity metrics section displays lifetime statistics scoped to the administrator's account, including total administrative actions performed, scans reviewed, overrides applied, and system configuration changes. The key difference from the operator profile (Figure 52) is the absence of the "Change Kiosk PIN" card, since edge kiosk scanning is operator-specific functionality and administrators do not authenticate at the physical terminal using a 4-digit PIN. The "Change Password" modal remains available and functions identically to the operator version (Figure 53), requiring current password verification before applying a new permanent credential.

- Route: `/profile`
- User Type: Admin
- Main Actions: Update profile settings, upload avatar, toggle theme, launch Change Password modal

---

## Figure 91: Change Password Modal (Admin Context)

Figure 91: Displays the administrative self-service modal dedicated to maintaining account security, rendered identically to the operator Change Password modal (Figure 53) since the same Dialog component and form logic are shared across roles. The modal requires three sequential inputs: the current password for identity verification, the new desired password, and a confirmation re-entry of the new password. Client-side validation enforces password matching and minimum length requirements before enabling the submission. The backend verifies the current password server-side using the password hash stored in the `user_account` model before applying the update. Upon successful password change, a success toast notification confirms the update, and the user's current session remains active (no forced re-authentication is required). The modal can be dismissed without changes via a cancel button, and the submit button shows a loading spinner with contextual text during the API call.

- Route: `/profile` (modal overlay)
- User Type: Admin
- Main Actions: Verify current password, input new password, confirm new password

---

## Figure 92: Public Scan Tracking View (Mobile & Web QR Portal)

Figure 92: Shows the public-facing scan tracking interface rendered by the PublicScanView component, accessible by scanning the QR code printed on a 40mm × 30mm produce label with any smartphone camera or standard web browser without requiring system authentication. The component uses the `useParams` hook to extract the `scanId` from the `/track/:scanId` URL and fetches scan data through the `api.scans.publicTrack()` endpoint, which returns a limited, non-sensitive subset of the scan record suitable for public consumption. The page displays verified banana provenance including: cultivar (Lakatan, Latundan, Cardaba) with a colored AppStatusBadge, ripeness stage with an emoji indicator (🟢 Unripe, 🟠 Semi Ripe, 🟡 Ripe, 🔴 Overripe) and a styled badge using the `ripenessColor` map, finger count with a Hand icon, estimated remaining shelf life in days formatted via `formatSpoilageDays` and `spoilageDayUnit`, scan timestamp formatted with a Calendar icon, and delivery intake origin identifying the supplier source. Camera capture photos are not shown: the public endpoint returns no image references, and capture evidence stays behind staff authentication. The page includes robust error handling with a 15-second loading timeout, retry functionality, and distinct empty states for "not found" versus "loading error" scenarios using the Empty component with EmptyMedia illustrations. The page is strictly read-only and shows only the scanned data: it has no login, website or navigation buttons, and signed-in staff who scan the code see the same page. The route is mounted outside the staff data providers, so a phone that still holds an old staff session is never sent to the login screen. Staff open the full scan detail page from the dashboard as usual.

- Route: `/track/:scanId`
- User Type: Public / Downstream Consumer / Quality Inspector
- Main Actions: Scan printed QR label with smartphone or browser, inspect produce provenance and classification, verify remaining shelf-life days, see whether the result is pending quality review
