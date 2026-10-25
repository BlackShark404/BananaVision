# User - Guide

BananaVision is an AI-powered web application designed to support intelligent banana ripeness detection and classification at agricultural post-harvest inspection stations. The system allows administrators and operators to capture multi-angle images of banana bunches, classify their cultivar and ripeness stage using trained YOLO deep learning models, predict spoilage timelines based on environmental conditions, and manage the complete inspection workflow through an intuitive web interface. By integrating a multi-camera array, automated AI classification, environmental sensing, and a responsive web application, BananaVision helps reduce subjective manual grading, improve classification consistency, and streamline post-harvest quality control.

The system consists of an inspection station equipped with four USB cameras, a DHT22 temperature and humidity sensor connected to an Arduino microcontroller, a thermal label printer, and a kiosk display, all connected to a station computer running the BananaVision backend server and web application accessible through a local network.

## Admin User's Guide

### I. Access the System

#### Log In

1. Open the BananaVision web application using Google Chrome or any modern browser by navigating to the station server address.
2. Enter the registered admin username and password.
3. Tap Login to proceed.

#### After Login

- The admin is redirected to the Admin Dashboard, where system-wide controls, real-time statistics, and monitoring tools are available.

### II. Navigation Using the Admin Menu

#### A. Account Management

- Login - Securely access the admin account using registered credentials.
- Logout - Safely exit the application after use.
- Change Password - Update the account password through the profile settings.

#### B. User Management

- View User Accounts - Display all registered administrator and operator accounts with their status and roles.
- Add User - Register new administrators or operators with temporary access credentials.
- Edit User - Update user details, assigned roles, and profile information.
- Deactivate User - Disable access for inactive or unauthorized users while preserving data integrity.
- Reset Password or PIN - Generate temporary credentials for users needing account recovery.

#### C. Supplier Management

- View Suppliers - Display all registered banana suppliers with their contact information and status.
- Add Supplier - Register new banana growers or suppliers into the system.
- Edit Supplier - Update supplier contact details or toggle their active status.

#### D. Delivery Intake Management

- View Delivery Intakes - Display all batch intake records with supplier, source, and treatment data.
- Create Intake - Register a new delivery batch with harvest date, treatment type, and batch number.
- Track Intake Status - Monitor batch lifecycle from active delivery to depleted stock.
- Link Scans to Intakes - Associate inspection scans with specific supplier batches for full provenance tracking.

#### E. Scan Logs and Evidence

- Browse Scan Records - View a paginated history of all completed scans with classification summaries.
- Search and Filter Scans - Filter records by date range, cultivar, ripeness stage, operator, or flag status.
- View Scan Details - Inspect multi-angle camera images, detected bounding boxes, and environmental data.
- Enlarge Camera Images - Open full-resolution camera captures with bounding box overlays for visual review.
- Print QR Labels - Generate adhesive labels containing QR codes and classification data for batch tracking.
- View QR Code - Display the scan QR code on screen for quick mobile scanning and verification.

#### F. Quality Control

- View Flagged Scans - Review scans flagged automatically by the AI or manually by operators.
- Override Classification - Correct cultivar, ripeness stage, or finger count with change history tracking.
- View Original AI Result - Compare manual corrections against the immutable original AI prediction.
- Accept Reviewed Scans - Mark verified scans as approved and clear their review flag.

#### G. Analytics and Inventory

- Scan Volume Trends - View interactive charts showing inspection volume over time by cultivar and ripeness.
- Quality Metrics - Monitor AI confidence distributions, override rates, and classification consistency.
- Inventory Status - Track inspected batches categorized by In Stock, Sold, For Processing, or Spoiled.
- Spoilage Projections - Review predicted shelf-life timelines based on environmental storage conditions.

#### H. Device Management

- View Camera Status - Monitor real-time online or offline indicators for all four inspection cameras.
- Sensor Connection - Check active communication and data polling from the DHT22 Arduino module.
- System Health Overview - View overall operational status of cameras, sensors, and loaded AI models.

#### I. Activity and Audit Logs

- View Audit Trail - Browse a server-side paginated log of all security and administrative events.
- Search Activity Records - Filter audit logs by action type, user account, date range, or IP address.
- Security Auditing - Track IP addresses and timestamps for logins, overrides, and configuration changes.

#### J. System Configuration

- Scanner Configuration - Map physical camera positions to detected USB indices and adjust detection confidence.
- Camera Calibration - Access live camera previews to verify lens focus, illumination, and alignment.
- Data Retention - Configure automated cleanup rules for expired image captures while preserving scan records.
- Export Scan Data - Download filtered scan records as CSV spreadsheets for external reporting.
- Backup and Restore - Create typed system archives with SHA-256 validation and restore previous configurations.
- System Controls - Initiate controlled operating system shutdown or restart with active scan drain coordination.
- System Metrics - Monitor real-time CPU utilization, memory consumption, and disk storage capacity.

#### K. Notifications Management

- View Notifications - Review system alerts, scan completion summaries, and quality warnings.
- Quality Alerts - Receive notifications when scans are flagged for classification conflicts or low confidence.
- System Alerts - Get notified of camera disconnections, sensor dropouts, or storage threshold warnings.

#### L. Profile and Settings

- Profile Management - Update user profile information, display name, and avatar.
- Interface Theme - Toggle between light and dark visual themes for optimal viewing comfort.

---

## Operator (User) Guide

### Getting Started

#### Access the Kiosk

1. Power on the station computer; the system automatically boots into fullscreen kiosk mode.
2. Select the operator profile from the kiosk interface.
3. Enter the registered 4-digit operator PIN.
4. Tap Login to begin the inspection session.

#### After Login

- The operator is directed to the Kiosk Scanning Dashboard, where live camera preview feeds, environmental readings, and inspection controls are immediately accessible.

### Kiosk Scanning Operations

#### Prepare Inspection

- Position Banana Bunch - Place the banana bunch on the inspection tray within view of all four cameras.
- Verify Camera Feeds - Confirm on the live previews that Top, Left, Right, and Rear views are clear and unobstructed.
- Select Delivery Batch - Optionally select the active delivery intake batch to link produce provenance.

#### Scan Execution

- Pre-Detection Check - System verifies the presence of bananas before initiating the full AI pipeline.
- Multi-Camera Capture - All four cameras capture synchronized high-resolution images of the fruit.
- AI Ripeness Detection - YOLO models detect individual banana fingers and classify cultivar and ripeness.
- Spoilage Estimation - System calculates shelf-life days using visual ripeness and DHT22 temperature and humidity data.
- Review Results - Inspect the overall cultivar, ripeness stage, confidence score, and detected finger count.

#### Quality Verification

- Accept Scan - Confirm the automated classification and save the scan record to inventory.
- Flag for Review - Flag ambiguous or questionable classifications for administrator quality control review.

### Label Printing

- Automatic Printing - Print adhesive QR labels automatically upon scan completion when enabled.
- Manual Batch Printing - Select scan records from the log and print one to ten label copies on demand.
- Demo Label Print - Print a test label to verify printer alignment and thermal paper supply.

### Public Scan Tracking

- QR Code Verification - Scan the printed label QR code using any smartphone camera or handheld scanner.
- Public Provenance Access - View cultivar, ripeness stage, harvest date, and spoilage prediction without requiring login.

### Profile and Settings

- PIN Management - Update the 4-digit operator authentication PIN.
- View Scan History - Review completed personal scan counts and recent inspection logs.
- Interface Theme - Toggle between light and dark display modes based on station lighting.

BananaVision is designed to be simple, reliable, and user-friendly, allowing administrators and operators to manage banana inspection and quality classification with minimal technical complexity. By combining multi-camera computer vision, automated ripeness grading, and environmental sensing, the system supports standardized post-harvest quality control and improved agricultural decision-making.

#### Scan Execution

- Pre-Detection Check - System verifies the presence of bananas before initiating the full AI pipeline.
- Multi-Camera Capture - All four cameras capture synchronized high-resolution images of the fruit.
- AI Ripeness Detection - YOLO models detect individual banana fingers and classify cultivar and ripeness.
- Spoilage Estimation - System calculates shelf-life days using visual ripeness and DHT22 temperature and humidity data.
- Review Results - Inspect the overall cultivar, ripeness stage, confidence score, and detected finger count.

#### Quality Verification

- Accept Scan - Confirm the automated classification and save the scan record to inventory.
- Flag for Review - Flag ambiguous or questionable classifications for administrator quality control review.

### Label Printing

- Automatic Printing - Print adhesive QR labels automatically upon scan completion when enabled.
- Manual Batch Printing - Select scan records from the log and print one to ten label copies on demand.
- Demo Label Print - Print a test label to verify printer alignment and thermal paper supply.

### Public Scan Tracking

- QR Code Verification - Scan the printed label QR code using any smartphone camera or handheld scanner.
- Public Provenance Access - View cultivar, ripeness stage, harvest date, and spoilage prediction without requiring login.

### Profile and Settings

- PIN Management - Update the 4-digit operator authentication PIN.
- View Scan History - Review completed personal scan counts and recent inspection logs.
- Interface Theme - Toggle between light and dark display modes based on station lighting.

BananaVision is designed to be simple, reliable, and user-friendly, allowing administrators and operators to manage banana inspection and quality classification with minimal technical complexity. By combining multi-camera computer vision, automated ripeness grading, and environmental sensing, the system supports standardized post-harvest quality control and improved agricultural decision-making.

