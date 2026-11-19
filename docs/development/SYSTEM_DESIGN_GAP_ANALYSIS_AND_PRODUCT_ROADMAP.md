# BananaVision System Design Gap Analysis and Product Roadmap

> **Document type:** Product-management and system-design proposal  
> **Prepared:** October 6, 2026  
> **Scope:** Expanding BananaVision from a two-role scanning prototype into a flexible banana quality, traceability, and operational decision-support platform  
> **Status:** Proposal only. Items in this document are not automatically implemented.

## 1. Executive Summary

BananaVision already has a meaningful technical foundation: multi-camera capture, banana classification, ripeness and finger-count results, spoilage estimation, environmental readings, delivery intakes, supplier records, inventory statuses, quality review, analytics, audit logs, and device administration.

The largest remaining product-design gap is not simply that the system has only **Admin** and **Operator** users. The deeper issue is that the system does not yet model the complete banana business process or clearly separate responsibility, approval, ownership, and data visibility. At present:

- The **Operator** performs scans and mainly views operational information.
- The **Admin** is simultaneously the IT administrator, user manager, supplier manager, receiving clerk, inventory controller, quality reviewer, system configurator, and business supervisor.

This is acceptable for a prototype, but it creates weak separation of duties and makes the product difficult to adapt to farms, cooperatives, suppliers, warehouses, processors, distributors, exporters, retailers, and other banana businesses.

The recommended direction is to make BananaVision a **lot-centered, organization-aware, IoT-edge quality and traceability platform**. It should follow a banana lot from its source and delivery through sampling, scanning, quality disposition, storage, allocation, dispatch, sale, processing, rejection, or waste. AI should support decisions, while authorized people remain responsible for high-impact business decisions.

The most important near-term additions are:

1. A real batch/lot lifecycle with quantities, units, location, and traceability.
2. Dedicated Receiving, Quality Assurance, Inventory, and Manager capabilities.
3. Permission-based access instead of relying only on two hard-coded roles.
4. Quality approval, quarantine, release, rejection, and corrective-action workflows.
5. Model, sensor, camera, and data-quality controls that make accuracy measurable and auditable.
6. Organization and site boundaries so the product can serve different banana businesses safely.

BananaVision should not attempt to implement every possible role and business feature at once. A phased roadmap is proposed so the next version can demonstrate one complete and credible process before expanding into a commercial multi-client platform.

---

## 2. Product Purpose

### 2.1 Proposed product statement

**BananaVision is an IoT-edge quality, traceability, and inventory decision-support platform for banana businesses. It combines multi-camera computer vision, environmental sensing, human quality review, and lot history to help organizations receive, inspect, grade, store, prioritize, dispatch, and account for bananas.**

### 2.2 What the system should accomplish

The system should help a banana business answer the following questions:

- Where did this banana lot come from?
- When was it harvested, treated, received, inspected, stored, moved, and dispatched?
- Who performed each action?
- What did the cameras, sensors, and AI observe?
- How reliable was the result, and which model/configuration produced it?
- Was the sample representative of the lot?
- Who reviewed and approved the quality decision?
- Is the lot available, quarantined, released, allocated, sold, processed, rejected, recalled, or spoiled?
- Where is the lot now, and how much quantity remains?
- Which lots should be prioritized under a first-expired, first-out policy?
- Which suppliers, storage conditions, or processes are associated with quality problems?
- Can the business produce evidence for a customer complaint, supplier claim, audit, or recall?

### 2.3 What the system should not claim without evidence

BananaVision should not claim that it:

- Guarantees banana quality or remaining shelf life.
- Replaces a qualified inspector or laboratory examination.
- Measures the quality of an entire lot from an unrepresentative sample.
- Automatically improves its AI just because it stores more images.
- Provides certified accuracy without a defined ground-truth dataset and independent validation.
- Provides complete inventory or financial accounting when quantity, movement, order, and reconciliation records are absent.

The preferred wording is **decision support**, **estimated classification**, **predicted spoilage window**, and **quality evidence**, with uncertainty shown to users.

---

## 3. Current System Strengths

The current implementation should be treated as a foundation rather than discarded. It already includes:

- Admin and Operator authentication and role-aware access.
- Multi-camera scanning at an edge station.
- YOLO-based cultivar/ripeness classification and finger counting.
- Multi-camera result fusion.
- Temperature and humidity readings from the DHT22 integration.
- Spoilage estimation using engineered environmental and treatment features.
- Supplier and delivery-intake records.
- Scan history, images, detections, notes, flags, overrides, and original AI results.
- Inventory states such as In Stock, For Processing, Sold, and Spoiled.
- Quality-control, analytics, notification, device-status, audit, and configuration screens.
- Session security, retention behavior, database migrations, and automated regression tests documented in the changelog.

These components cover important pieces of a banana operation. The next design step is to connect them into a governed end-to-end process.

---

## 4. Primary System-Design Lapses

### 4.1 Roles do not represent real business responsibilities

The current Admin role contains both technical and operational authority. One person can manage accounts, configure models and cameras, maintain suppliers, change inventory, and override AI results. This creates several problems:

- Weak separation of duties.
- Excessive access for staff who need only one function.
- Poor accountability when the same role records and approves a decision.
- Higher damage potential if an administrator account is misused.
- Difficulty selling the product to organizations with specialized staff.

Adding roles alone will not solve this. The system needs granular permissions and organization/site scope.

### 4.2 The workflow begins too late and ends too early

The current core workflow is close to:

`Supplier/Intake -> Scan -> Result -> Inventory Status`

A real process commonly begins with an expected delivery or purchase reference and ends with dispatch, processing, sale, rejection, claim, recall, or waste. Missing stages make it difficult to prove full traceability or business value.

### 4.3 Inventory is scan-centered rather than lot-and-quantity-centered

Individual scans are useful evidence, but an inventory system must know quantities and movements. The present structure does not fully express:

- Received quantity and accepted/rejected quantity.
- Unit of measure such as kilograms, boxes, crates, hands, or pieces.
- Current balance.
- Storage site, room, zone, rack, or bin.
- Lot splitting, merging, repacking, or processing.
- Reservations and allocations to customers/orders.
- Physical stock counts and adjustments.
- Yield and loss.

Counting scan records is not the same as counting inventory.

### 4.4 Intake and quality disposition are too simple

An intake with only Active/Depleted and scans with only broad inventory statuses cannot fully express a controlled receiving and inspection process. The design lacks clear states such as:

- Expected
- Arrived
- Receiving
- Awaiting Sampling
- Under Inspection
- Quarantined
- Accepted/Released
- Conditionally Accepted
- Rejected
- Partially Accepted
- Closed

Without a disposition workflow, it is unclear when stock is allowed to enter sellable inventory.

### 4.5 No formal sampling plan

AI can accurately describe an image and still lead to a poor lot-level conclusion if the sampled bananas are not representative. The system should define:

- Lot size and sampling method.
- Required sample size.
- Random or stratified sample positions.
- Number of scans completed versus required.
- Rescan rules.
- Acceptance thresholds.
- Who selected the sample.

This is a major accuracy gap because system accuracy depends on both model accuracy and process accuracy.

### 4.6 AI review is not a complete quality-management workflow

Flags and overrides are helpful, but a mature process also needs:

- A review queue with priority and due time.
- Review assignment.
- Correct/incorrect/uncertain confirmation.
- Standardized reason codes.
- Manual defect tagging.
- Independent reviewer identity and timestamp.
- Approval or rejection at scan, sample, and lot level.
- Escalation and second review for disputed results.
- Corrective/preventive actions and final resolution.

### 4.7 Environmental context is limited

A sensor value captured around scan time does not describe a lot's full storage exposure. For meaningful spoilage support, the design should connect continuous sensor readings to a site/room/zone and calculate lot exposure over time. Important gaps include:

- Sensor-to-location assignment.
- Calibration date and acceptable tolerance.
- Missing/stale/out-of-range reading detection.
- Time synchronization across the edge device, camera, sensor, and database.
- Temperature/humidity excursion duration.
- Lot movement between environments.
- Optional commodity/core-temperature measurements where required.

### 4.8 The system cannot yet serve multiple organizations safely

Supplier records are business data, not user accounts for different clients. A flexible product needs explicit boundaries for:

- Organization/tenant.
- Site/facility.
- Station.
- Storage location.
- Users and memberships.
- Suppliers, customers, lots, scans, devices, and reports owned by an organization.

Without this boundary, expanding to several client companies risks data leakage and configuration conflicts.

### 4.9 External stakeholders have no controlled participation

Suppliers, customers, third-party inspectors, and auditors may need limited access. They should not receive Admin access. Possible controlled capabilities include:

- A supplier viewing only its own deliveries, quality outcomes, and claims.
- A customer verifying a dispatched lot through a traceability code.
- An auditor viewing immutable records without changing them.
- A technician viewing device health without seeing commercial records.

### 4.10 Commercial flow is incomplete

The prototype tracks supplier-side intake but not the downstream demand side. For broader banana businesses, useful missing concepts include:

- Customer accounts.
- Orders and required specifications.
- Lot allocation.
- Pick/pack/dispatch records.
- Delivery proof.
- Returns and complaints.
- Supplier claims and customer claims.
- Optional price/cost fields and ERP/accounting integration.

BananaVision does not need to become a full accounting system. It should provide quality and traceability records and integrate with accounting/ERP products when necessary.

### 4.11 Edge operation and central management are not fully designed

An IoT-edge product needs explicit behavior for:

- Internet outage.
- Database or central-service outage.
- Retry and synchronization.
- Duplicate event prevention.
- Conflict resolution.
- Local storage limits.
- Remote health monitoring.
- Secure software/model/configuration updates.
- Backup and recovery.

Offline-capable local scanning is a strength only if synchronization and recovery are dependable and auditable.

### 4.12 Accuracy is not yet an operationally governed property

An AI model file and a confidence score do not prove business accuracy. The system needs an accuracy-management process covering ground truth, model version, equipment condition, lighting, sampling, reviewer agreement, drift, and performance by operating subgroup.

---

## 5. Recommended User and Access Model

### 5.1 Do not hard-code every business type as a role

A farm, warehouse, distributor, and retailer may use different job titles for the same capability. BananaVision should use three layers:

1. **Organization type** describes the client business.
2. **Role template** provides a convenient starting permission set.
3. **Permissions and scope** determine what a particular user can actually do and where.

Example:

`User -> Organization Membership -> Role Template -> Permissions -> Allowed Sites/Stations`

The backend must enforce permissions and scope. Hiding a frontend menu is not security.

### 5.2 Supported organization types

The same core platform can support:

- Farm or plantation
- Grower cooperative
- Consolidator
- Supplier or trader
- Packing house
- Warehouse or cold-storage operator
- Processor
- Distributor or wholesaler
- Exporter/importer
- Supermarket, market, restaurant, or retail chain
- Independent quality-inspection service
- Research or government program

An organization may perform more than one function, so organization type should be descriptive, not restrictive.

### 5.3 Recommended role templates

| Role template | Main responsibility | Typical permissions | Restrictions |
| --- | --- | --- | --- |
| Platform Administrator | Operate a hosted multi-client platform | Tenant provisioning, global health, releases | No routine access to client content unless explicitly authorized and audited |
| Organization Owner/Admin | Manage one client's workspace | Memberships, sites, policies, reports | Cannot alter platform-level controls |
| Site/Operations Manager | Supervise a facility | Operational dashboard, assignments, approvals, site reports | Scoped to assigned sites |
| Receiving Clerk | Record deliveries | Create intake, weigh/identify lot, print labels, record documents | Cannot approve own quality result by default |
| Scan Operator | Acquire evidence | Select lot/sample, scan, rescan, flag issues | Cannot override AI or release/reject a lot |
| QA Inspector | Validate quality | Review images/results, tag defects, confirm/correct AI, grade lot, recommend disposition | Cannot configure system security or delete evidence |
| QA Approver | Make final disposition | Release, conditionally accept, quarantine, reject, reopen with reason | Optional second-person approval for high-impact decisions |
| Inventory/Warehouse Staff | Control physical stock | Move, split, merge, adjust, count, allocate, mark processing/waste | Cannot change original AI evidence |
| Sales/Dispatch Staff | Fulfill customer demand | Orders, allocation, pick/pack/dispatch, traceability documents | Cannot change inspection results |
| Maintenance Technician | Keep station operational | Device health, calibration, maintenance, diagnostics | No supplier pricing or quality-decision authority |
| Analyst/Manager | Review performance | Read analytics and approved reports | No operational mutation by default |
| Auditor/Viewer | Verify records | Read immutable history and audit evidence | No write permissions |
| Supplier/Partner User | Collaborate externally | View own deliveries, submit documents, respond to claims | Restricted to their organization's shared records |

### 5.4 Minimum roles for the next prototype

Do not implement all role templates immediately. The strongest next demonstration would use:

1. **Admin** – accounts, security, devices, models, and configuration.
2. **Receiving/Inventory** – intakes, quantities, storage, movements, and dispatch status.
3. **Operator** – sample selection and scanning.
4. **QA** – validation, defects, grading, quarantine/release/reject, and corrective action.
5. **Manager/Viewer** – dashboards, trends, and reports without system configuration.

Supplier portal access can follow after organization scoping is reliable.

### 5.5 Permission examples

Permissions should describe actions, for example:

- `users.manage`
- `sites.manage`
- `stations.configure`
- `devices.calibrate`
- `suppliers.manage`
- `customers.manage`
- `intakes.create`
- `intakes.receive`
- `samples.collect`
- `scans.perform`
- `scans.view_own`
- `scans.view_site`
- `quality.review`
- `quality.override_ai`
- `quality.disposition`
- `inventory.move`
- `inventory.adjust`
- `orders.allocate`
- `dispatch.confirm`
- `claims.manage`
- `analytics.view`
- `reports.export`
- `audit.view`

High-risk permissions should support approval policies and should always create an audit event.

---

## 6. Recommended End-to-End Business Process

### Stage 1: Organization and facility setup

- Register the client organization.
- Define sites, storage locations, stations, and time zone.
- Assign users through organization memberships.
- Configure cultivar/ripeness/grade vocabularies and quality rules.
- Register cameras, sensors, scales, printers, and station identifiers.
- Record device calibration and maintenance schedules.
- Provision approved model versions and operating thresholds.

**Control:** A station may only write data to its assigned organization and site.

### Stage 2: Partner and specification setup

- Register suppliers/farms/cooperatives and customers.
- Store contact and traceability identifiers.
- Define customer or contract specifications, such as accepted cultivars, ripeness range, defect tolerance, packaging, and minimum remaining shelf-life estimate.
- Record certifications or documents where relevant.

**Control:** Expired or missing documents should warn users; they should not silently disappear.

### Stage 3: Expected delivery and receiving

- Create an expected delivery, purchase reference, or advance shipment notice.
- On arrival, record supplier, source farm, vehicle, arrival time, harvest/treatment information, declared cultivar, and batch/lot identifier.
- Record quantity, unit, packaging, weight, and receiving location.
- Generate or scan a QR/barcode label.
- Attach delivery documents and receiving photos.
- Record visible arrival condition.

**Output:** A unique, immutable lot ID with a human-readable label.

### Stage 4: Sampling

- Determine the sample size based on lot size and the configured policy.
- Guide the operator to select samples from defined positions or packages.
- Record each sample's sequence and relationship to the lot.
- Prevent final lot disposition when the required sample is incomplete unless an authorized user records an exception.

**Output:** Evidence that the scanned sample was intentionally collected rather than conveniently selected.

### Stage 5: IoT-edge scan and data-quality checks

- Confirm station, lot, operator, and sample identity.
- Check camera availability, calibration status, lighting/exposure, storage capacity, model availability, and sensor freshness.
- Capture all required views.
- Detect image problems such as blur, obstruction, missing view, poor lighting, or no banana.
- Read temperature/humidity with timestamp and sensor identity.
- Run inference locally and store the result, confidence/uncertainty, timing, model version, threshold/configuration version, and original evidence.
- If minimum quality gates fail, request a rescan rather than producing a normal result.

**Output:** A reproducible scan result plus evidence and provenance.

### Stage 6: Human quality review

- Automatically pass only results allowed by the organization's policy.
- Route low-confidence, contradictory, anomalous, random-audit, or operator-flagged scans to QA.
- Let QA confirm, correct, mark uncertain, or request a rescan.
- Record standardized defect types, severity, location, and notes.
- Preserve original AI output separately from the reviewed result.
- Require a reason for overrides.

**Output:** Reviewed scan/sample findings and labeled feedback for future model evaluation.

### Stage 7: Lot grading and disposition

- Aggregate the completed sample results.
- Present the distribution, not only an average: cultivar agreement, ripeness distribution, defects, count, spoilage estimates, and environmental warnings.
- Let an authorized QA user assign grade and disposition:
  - Released/Accepted
  - Conditionally Accepted
  - Quarantined
  - Partially Accepted
  - Rejected
  - Resampling Required
- Record reason codes, reviewer, timestamp, and any second approval.

**Control:** Quarantined or rejected stock cannot be allocated or sold.

### Stage 8: Inventory and storage

- Place accepted quantity into a storage location.
- Record every receipt, move, split, merge, repack, adjustment, processing issue, return, and disposal as an inventory transaction.
- Calculate balance from transactions instead of overwriting a single status.
- Associate continuous sensor exposure with the lot's location and time interval.
- Alert on excursions and predicted risk.
- Prioritize lots through FEFO where appropriate.

**Output:** Quantity and location traceability with an explainable current balance.

### Stage 9: Order, processing, or dispatch

- Record customer/order or processing request.
- Match lots against cultivar, ripeness, grade, and remaining-life requirements.
- Allocate eligible inventory.
- Pick, pack, and dispatch with a traceability reference.
- Record dispatched quantity, destination, vehicle, time, and responsible user.
- For processing, record consumed input lots and resulting output lot/yield.

**Output:** Forward traceability from input lot to customer shipment or processed output.

### Stage 10: Claims, returns, recall, and closure

- Record supplier rejection/claim evidence when incoming quality fails.
- Record customer complaints and returned quantity.
- Trace affected source lots and downstream deliveries.
- Quarantine remaining related stock when necessary.
- Record investigation, resolution, credit/replacement reference, and corrective action.
- Close the lot only after its quantity is fully dispatched, processed, rejected, wasted, or adjusted with reasons.

### Stage 11: Analytics and continuous improvement

- Measure supplier quality, rejection rate, shelf-life outcomes, waste, environmental excursions, QA agreement, operator rescan rate, and station reliability.
- Evaluate AI predictions against reviewed ground truth and later outcomes.
- Detect performance drift by cultivar, ripeness class, supplier, site, station, camera, lighting, treatment, and season.
- Approve new models through a controlled evaluation and deployment process.

---

## 7. Recommended Domain and Data-Model Extensions

The following is a conceptual model, not a final database migration.

### 7.1 Organization and access

- `organization`
- `site`
- `station`
- `storage_location`
- `organization_membership`
- `role_template`
- `permission`
- `role_permission`
- `membership_scope`

All business records should carry `organization_id`; site-bound records should also carry `site_id`.

### 7.2 Partners and commercial references

- `business_partner` with partner types such as Supplier, Customer, Farm, Carrier, or Inspector
- `partner_contact`
- `partner_document`
- `quality_specification`
- `expected_delivery`
- `customer_order`
- `shipment`
- `claim`

A supplier should remain a business partner. A supplier user should be an account linked to that partner and granted limited organization access.

### 7.3 Lot, sampling, and quality

- `lot` as the primary traceable inventory object
- `lot_relationship` for split, merge, repack, or transformation lineage
- `receiving_event`
- `sampling_plan`
- `sample`
- `scan` linked to a sample and lot
- `quality_review`
- `defect_observation`
- `lot_grade`
- `quality_disposition`
- `corrective_action`

The current `delivery_intake` can evolve into or reference a lot rather than being removed abruptly.

### 7.4 Inventory

- `inventory_transaction`
- `inventory_balance` as a derived/cache representation
- `stock_count`
- `allocation`
- `processing_event`
- `waste_event`

Each transaction should record lot, quantity, unit, source/destination location, reason, actor, timestamp, and an idempotency key where integrations are involved.

### 7.5 Device, sensor, and ML provenance

- `device_assignment`
- `device_calibration`
- `maintenance_event`
- `sensor_location_assignment`
- `environmental_excursion`
- `model_registry`
- `model_deployment`
- `inference_run`
- `data_quality_check`

Every inference should be traceable to model checksum/version, configuration version, station, cameras, sensor readings, application version, and processing time.

### 7.6 Important data rules

- Business identifiers may be human-readable, but primary identifiers should remain immutable.
- Original captured evidence and original AI results should be append-only.
- Corrections should create revisions/events rather than silently replacing history.
- Inventory balance must reconcile with its transaction ledger.
- Lot lineage must prevent loops.
- A record must not reference another organization's data.
- High-impact transitions must require a reason, actor, and timestamp.
- Time should be stored consistently with timezone and displayed in the site's local timezone.

---

## 8. Accuracy and Reliability Improvement Plan

### 8.1 Define accuracy per output

There is no single “system accuracy.” Measure each output separately:

| Output | Recommended measures |
| --- | --- |
| Cultivar classification | Per-class precision, recall, F1, confusion matrix, macro F1 |
| Ripeness classification | Per-class precision/recall/F1, confusion matrix, ordinal error distance |
| Banana/finger counting | MAE, RMSE, exact-match rate, undercount/overcount rate |
| Object detection | Precision-recall, mAP at defined IoU values, missed-detection rate |
| Spoilage/remaining-life prediction | MAE, RMSE, bias, error distribution, interval coverage |
| Confidence quality | Calibration error/reliability curve; accuracy at each confidence band |
| End-to-end lot decision | QA agreement, false accept rate, false reject rate, resample rate |
| Operational reliability | Successful scan rate, rescan rate, inference latency, device uptime |

Thresholds must be selected from business risk. A false acceptance of poor stock and a false rejection of good stock have different costs.

### 8.2 Create defensible ground truth

- Write a labeling guide with examples and edge cases.
- Use qualified domain reviewers.
- Require two reviewers for a validation subset.
- Resolve disagreements through adjudication.
- Keep training, validation, and test lots separate.
- Avoid putting images from the same banana/lot in both training and test sets.
- Test data from different farms, seasons, lighting conditions, devices, treatments, and sites.
- Preserve dataset version and label history.

### 8.3 Improve input quality

- Standardize station lighting and background.
- Fix camera distance, angle, resolution, and exposure where possible.
- Add a physical positioning guide.
- Detect blur, darkness, glare, obstruction, and missing views before inference.
- Calibrate cameras and sensors on a schedule.
- Warn when a calibration is overdue.
- Validate the scan's lot/sample identity before capture.

### 8.4 Use uncertainty and abstention

The system should not force a confident-looking answer for every input. Define outcomes such as:

- Accepted automatically
- Accepted but randomly audited
- Requires QA review
- Requires rescan
- Unable to determine

Use confidence together with multi-camera disagreement, image-quality results, class ambiguity, and out-of-distribution signals. Confidence is not the same as probability of correctness unless calibrated.

### 8.5 Validate spoilage predictions appropriately

Spoilage prediction needs observed outcomes, not only reviewer opinion. Record:

- Prediction timestamp and predicted interval.
- Actual spoilage/unsellable timestamp under a written definition.
- Storage-location exposure and treatment history.
- Censoring when a lot is sold or processed before spoilage can be observed.
- Prediction error by cultivar, ripeness, treatment, site, and season.

Use prediction intervals where possible instead of presenting one exact day as certain.

### 8.6 Establish a controlled model lifecycle

1. Register candidate model and checksum.
2. Evaluate it against a locked test dataset.
3. Document class map, training data scope, metrics, limitations, and hardware latency.
4. Obtain approval.
5. Deploy to selected stations.
6. Run shadow or limited rollout where possible.
7. Monitor errors and drift.
8. Roll back if acceptance criteria fail.

Human corrections should enter a curated review pool. They should not automatically retrain or deploy a model.

### 8.7 Monitor field performance

Create dashboards for:

- AI-to-QA agreement.
- Override rate and reason.
- Unknown/abstain rate.
- Rescan rate.
- Per-class error trends.
- Camera-specific disagreement.
- Supplier/site/season performance shifts.
- Sensor missingness and excursions.
- Prediction versus actual spoilage.

Define an alert when performance falls below the approved operating range.

---

## 9. Functional Improvements by Area

### 9.1 Receiving and traceability

- Expected delivery and receiving checklist.
- Quantity, unit, weight, packaging, vehicle, source farm, and document capture.
- Unique lot label and QR/barcode printing.
- Duplicate batch detection within the appropriate supplier/site scope.
- Partial receipt and partial rejection.
- Chain-of-custody timeline.

### 9.2 Quality assurance

- Dedicated QA work queue.
- Defect catalog and severity.
- Sampling-plan completion.
- Scan confirmation/correction/uncertain decision.
- Lot grade and disposition.
- Quarantine and release controls.
- Supplier claim evidence package.
- Corrective action and approval.

### 9.3 Inventory and warehouse

- Quantity ledger and balances.
- Storage locations.
- Moves, splits, merges, repacking, processing, waste, returns, and adjustments.
- FEFO suggestions.
- Physical stock count and reconciliation.
- Prohibition on allocating quarantined/rejected lots.

### 9.4 Sales, processing, and dispatch

- Customer and specification records.
- Order allocation based on quality requirements.
- Pick/pack/dispatch confirmation.
- Shipment traceability code and quality certificate/summary.
- Processing input/output lineage and yield.
- Returns and customer claims.

### 9.5 IoT and station operations

- Station readiness checklist.
- Camera/sensor calibration records.
- Continuous environment monitoring by location.
- Alert acknowledgment and escalation.
- Offline queue and synchronized event status.
- Signed, versioned model/configuration deployment.
- Remote diagnostics with strict permissions.
- Local storage and backup health.

### 9.6 Reporting

- Lot traceability report.
- Receiving and quality-disposition report.
- Supplier scorecard.
- Inventory aging and FEFO report.
- Waste/yield report.
- Environmental excursion report.
- Model performance report.
- Audit and chain-of-custody report.
- Claim/complaint evidence report.

---

## 10. Non-Functional Requirements

### 10.1 Security and privacy

- Enforce organization and site scope on every API query and mutation.
- Apply least privilege and separation of duties.
- Use strong session controls and optional MFA for high-privilege users.
- Protect secrets and encrypt network traffic.
- Audit logins, exports, approvals, overrides, configuration changes, and access to sensitive evidence.
- Define retention policies by record type and legal/business need.
- Ensure exported reports respect the requesting user's scope.

### 10.2 Reliability and recovery

- Define recovery point and recovery time objectives.
- Back up the database, evidence files, configuration, and model registry.
- Test restoration regularly.
- Use idempotent operations for scan upload and synchronization.
- Show whether data is local, queued, synchronized, failed, or conflicted.
- Preserve evidence if a downstream service is temporarily unavailable.

### 10.3 Performance

- Set measurable targets for capture, inference, result display, queue synchronization, and reporting.
- Measure on the actual Mini PC and production camera configuration.
- Separate interactive scan latency from background analytics/export workloads.

### 10.4 Usability and accessibility

- Provide task-specific dashboards instead of showing every feature to every user.
- Design kiosk screens for gloves, distance, and rapid repeated operation.
- Use clear status labels, confirmation for irreversible actions, and recovery instructions.
- Support keyboard use, readable contrast, screen-reader semantics, and responsive layouts.
- Consider local terminology and language support for deployed users.

### 10.5 Interoperability

- Document versioned APIs.
- Support CSV import/export with explicit schemas.
- Plan adapters for scales, label printers, barcode readers, ERP/accounting, warehouse systems, and messaging services.
- Use stable external IDs and idempotency keys.

---

## 11. Proposed Product Architecture

### 11.1 Edge responsibilities

The site edge node should own operations that must continue with poor internet connectivity:

- Camera and sensor communication.
- Image-quality checks and AI inference.
- Scan workflow and immediate QA/operator feedback.
- Local evidence storage.
- Local identity/session support appropriate to the deployment.
- Durable event queue for later synchronization.
- Station health, logs, and update status.

### 11.2 Central or organization-level responsibilities

When a central service is introduced, it should handle:

- Cross-site organization management.
- Central supplier/customer/lot visibility.
- Consolidated analytics.
- Model registry and approved deployment packages.
- Backup/retention policy coordination.
- Partner portal and external reports.
- Integration with ERP, order, or notification systems.

### 11.3 Synchronization principles

- Every event has a globally unique ID, source station, timestamp, and version.
- Retries must not duplicate records.
- Original evidence is immutable.
- Conflicts are visible and resolved through defined rules.
- The UI displays synchronization state.
- A station cannot access another organization's information merely because it is offline.

For a single-site capstone deployment, these may begin as interfaces and design constraints rather than a full cloud service.

---

## 12. Prioritized Roadmap

### Phase 0: Validate the present prototype

**Goal:** Establish a trustworthy baseline before adding scope.

- Complete physical camera, sensor, reboot, power, offline, and autostart tests.
- Verify deployed database migrations and backup restoration.
- Record model metadata, class map, test metrics, and Mini PC latency.
- Validate current claims, role/session behavior, and legacy credential rotation.
- Interview at least one receiving worker, scanner/operator, QA person, warehouse person, and manager.

**Exit criterion:** Current features work on the target station and their limitations are documented.

### Phase 1: Complete one credible lot workflow

**Goal:** Demonstrate delivery-to-disposition traceability.

- Add lot quantity/unit and storage location.
- Add expected/received/inspection/quarantine/released/rejected states.
- Add a sampling plan and sample records.
- Add the QA role and review queue.
- Add defect tags, review decisions, lot grade, disposition, and override reasons.
- Prevent quarantined/rejected lots from becoming sellable.
- Add a lot timeline and traceability report.

**Exit criterion:** A delivery can be received, sampled, scanned, reviewed, accepted/rejected, stored, and audited without relying on an Admin to perform every step.

### Phase 2: Inventory and outcome tracking

**Goal:** Make inventory quantities and spoilage evaluation credible.

- Add inventory transaction ledger and reconciliation.
- Add move/split/merge/processing/waste actions.
- Add continuous sensor-to-location exposure.
- Add FEFO recommendations and alert acknowledgment.
- Record actual spoilage outcomes and model error.
- Add supplier scorecards and claim reports.

**Exit criterion:** On-hand quantity and lot location reconcile, and predicted outcomes can be compared with actual outcomes.

### Phase 3: Flexible client platform

**Goal:** Support several banana-business types safely.

- Add organizations, sites, memberships, role templates, permissions, and scope.
- Migrate existing records into a default organization/site.
- Add Manager/Viewer and Maintenance templates.
- Add customer/order/dispatch or processing modules according to validated client demand.
- Add supplier/partner access only after tenant isolation testing.

**Exit criterion:** Two organizations can use the system without seeing or modifying each other's data or configuration.

### Phase 4: Managed edge fleet and integrations

**Goal:** Operate multiple stations reliably.

- Add durable offline synchronization.
- Add fleet health and remote diagnostics.
- Add controlled software/model/configuration rollout and rollback.
- Add ERP, scale, printer, barcode, and messaging integrations.
- Add cross-site analytics and disaster-recovery exercises.

**Exit criterion:** Multiple stations continue safely during connectivity failures and reconcile correctly afterward.

---

## 13. Suggested Backlog Structure

Each backlog item should include:

- Business problem and affected user.
- Permission and data scope.
- Preconditions and normal flow.
- Failure, retry, cancellation, and offline behavior.
- State transitions and prohibited transitions.
- Audit events.
- Validation and error messages.
- Acceptance criteria.
- Automated tests.
- Hardware/manual acceptance steps where applicable.
- Metrics that show whether the feature delivers value.

Example epic breakdown:

1. Organization and Site Foundation
2. Role/Permission Authorization
3. Lot and Receiving
4. Sampling and Evidence Capture
5. QA Review and Disposition
6. Inventory Ledger and Storage
7. Environmental Monitoring and Alerts
8. Orders/Processing/Dispatch
9. Claims and Traceability
10. Model Governance and Accuracy Monitoring
11. Edge Synchronization and Fleet Management
12. Reporting, Integration, and Recovery

---

## 14. Product Success Measures

Avoid measuring success only by the number of pages or roles. Recommended measures include:

- Percentage of received lots with complete traceability.
- Percentage of lots completing required sampling.
- Median receiving-to-disposition time.
- Scan success and rescan rates.
- AI/QA agreement and override rates by reason.
- False accept and false reject rates on verified data.
- Inventory reconciliation variance.
- Waste/spoilage percentage and value where available.
- Environmental excursion frequency and response time.
- On-time QA review and alert acknowledgment.
- Supplier defect/rejection trend.
- Device uptime and mean time to recovery.
- Offline synchronization success and conflict rate.
- Number and age of unresolved claims/corrective actions.
- User task completion time and error rate.

These metrics should have a baseline and an agreed target. A dashboard without targets does not by itself prove improvement.

---

## 15. Risks and Design Trade-offs

| Risk | Why it matters | Recommended response |
| --- | --- | --- |
| Role explosion | Too many fixed roles become difficult to maintain | Use permission bundles and scope; begin with five practical roles |
| Premature multi-tenancy | Adds complexity before the core workflow is stable | Design organization IDs now; implement full tenant operations after Phase 1 |
| Becoming a full ERP | Dilutes the unique AI/quality value | Own quality and traceability; integrate accounting where appropriate |
| Overtrusting AI confidence | Can create unsafe accept/reject decisions | Use QA review, uncertainty, abstention, and measured thresholds |
| Unrepresentative sampling | Makes lot decisions unreliable even with a good model | Implement sampling plans and completion controls |
| Uncontrolled corrections | Destroys evidence and training value | Preserve original results and append reviewed revisions |
| Sensor overclaim | Ambient scan-time readings may not represent product exposure | Track location exposure and state sensor limitations |
| Offline data conflicts | Can duplicate or overwrite business events | Use immutable event IDs, idempotency, and visible sync states |
| Weak tenant isolation | Could expose one client's commercial data to another | Enforce organization filters in backend and test every route |
| Excessive prototype scope | Delays a demonstrable, stable outcome | Complete one delivery-to-disposition vertical slice first |

---

## 16. Decisions Required from the Project Team

Before implementation, the team should decide:

1. What is the first target client and site: supplier warehouse, cooperative, packing house, distributor, or retailer?
2. Is BananaVision evaluating individual bananas, sampled packages, hands/bunches, or whole delivery lots?
3. What quantity units must be supported?
4. What official definitions determine ripeness, defect severity, grade, acceptance, rejection, and spoilage?
5. Who is qualified to provide ground truth and approve a lot?
6. What sampling method is defensible for the target operation?
7. Which decisions may be automatic, and which always require human approval?
8. Is the first deployment single-site only, or must it support multiple facilities?
9. Must the station operate without internet, without the central database, or both?
10. Which reports or integrations does the first real client actually require?
11. What data-retention, privacy, and audit obligations apply?
12. What accuracy and latency thresholds constitute acceptance on the target hardware?

These decisions should be captured as requirements, not left as assumptions in code.

---

## 17. Recommended Capstone/Product Defense Position

The team can state:

> BananaVision currently demonstrates an IoT-edge inspection foundation that combines multi-camera AI, environmental sensing, traceable scan records, inventory indicators, and administration. Our product analysis identified that a deployable business solution requires more than Admin and Operator access. We therefore propose a permission-based and organization-scoped design with dedicated receiving, QA, inventory, management, and partner capabilities. The priority is to complete a controlled delivery-to-disposition workflow, measure AI and process accuracy against human-reviewed ground truth, and then expand into multi-site traceability, dispatch, claims, and external integrations.

This position is stronger than claiming the prototype already manages the entire banana supply chain. It clearly distinguishes:

- What works now.
- What is missing.
- Why the missing pieces matter.
- What should be built first.
- How success will be measured.

---

## 18. Final Recommendation

BananaVision should evolve around three connected foundations:

1. **Traceable lots and inventory:** know the identity, quantity, location, lineage, and disposition of the bananas.
2. **Governed quality decisions:** combine AI, sensors, sampling, human review, uncertainty, and approvals without erasing original evidence.
3. **Flexible organizational access:** support different banana businesses through organization/site scope, permission bundles, and task-specific roles.

The next development milestone should not be “add many users and pages.” It should be:

> **Demonstrate one complete, auditable journey from delivery intake through sampling, edge scanning, QA decision, inventory release/quarantine, storage, and final disposition.**

Once that vertical workflow is reliable, the same foundation can be extended for farms, suppliers, warehouses, processors, distributors, exporters, retailers, and quality-inspection organizations without redesigning the product for every client.

