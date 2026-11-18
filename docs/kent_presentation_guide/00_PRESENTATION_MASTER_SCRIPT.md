# 🍌 BananaVision — 10-15 Minute Prototype Presentation Master Guide

> **Presenter:** Kent RG A. Baguio  
> **Topic:** Prototype Output Presentation & Code Defense  
> **Time Limit:** 10 to 15 Minutes  
> **Core Focus:** Security Architecture, Account & User Governance, System & Scanner Hardware Management, and YOLO Multi-Camera Detection Pipeline.

---

## ⏱️ 10–15 Minute Pitch & Demo Timeline

| Time Marker | Presentation Phase | What You Show / Do on Screen | Key Points to Speak Out Loud |
|---|---|---|---|
| **0:00 – 1:30** | **Hook & System Architecture** | Start on `Landing Page` (`/`), then switch to Architecture Diagram. | "Good morning panel. BananaVision is an edge-deployed computer vision kiosk running on a Mini PC. It solves automated cultivar classification, ripeness grading, and finger counting using multi-camera YOLO vision fused with IoT sensors. My primary ownership covers the Core Security & Authentication, User Governance, Hardware & Station Configuration, and the Multi-Camera YOLO Detection Pipeline." |
| **1:30 – 3:45** | **Authentication & Security Defense** | Show `Login.tsx`, demonstrate Admin login, then Kiosk Operator PIN swap modal. | "Notice how we implement two distinct authentication flows: Full Username/Password for Admins and Fast 4-Digit PIN Swapping for warehouse operators. Under the hood, security is airtight: Argon2/Bcrypt password hashing, token versioning (`tv`) that instantly invalidates stolen JWTs on logout, and memory-backed sliding-window rate limiting (`AUTH-04`) to prevent brute-force attacks on both passwords and kiosk PINs." |
| **3:45 – 6:15** | **User Management & Role Governance** | Open `/admin/users` (`UserManagement.tsx`). Create user, toggle status, reset PIN. | "In User Management, notice our strict RBAC. Admins and Operators have distinct database profile tables (`AdminProfile` and `OperatorProfile`). When an operator is promoted or demoted, the backend reconciles their profile and revokes existing sessions. We implemented an atomic lock protecting the **last active administrator** (`ADMIN-01`) so the system can never be locked out. Temporary credentials trigger a forced first-time password/PIN setup via cryptographic `setup_token`." |
| **6:15 – 8:30** | **Hardware Calibration & System Configuration** | Open `/admin/config` (`SystemConfig.tsx`) and Camera Calibration Modal. | "BananaVision integrates 4 physical USB cameras (Top, Left, Right, Rear). Through `/cameras/discovery` and `/cameras/mapping`, admins can assign hardware device indices with live MJPEG preview feeds. All hardware reconfigurations are protected by an asynchronous `station_lock` so no camera can be remapped mid-scan. We also expose real-time station power controls with administrative recovery authorization." |
| **8:30 – 12:00** | **YOLO Detection & Multi-Camera AI Pipeline (THE CLIMAX)** | Trigger a live/demo scan from Kiosk (`/scan`). Watch WebSocket progress, bounding boxes, and final fused card. | "Here is the heart of BananaVision: our Two-Stage YOLO Architecture. Stage 1 is a base COCO YOLO pre-detector gate that verifies a banana actually exists before triggering inference. Stage 2 is our custom YOLO banana classifier detecting 3 cultivars (Lakatan, Latundan, Cardaba) and 4 ripeness stages across all 4 cameras in parallel. We built custom CV enhancements: 180° rotation fallback to catch occluded fingers, upper ceiling artifact suppression, cluster box elimination, and cross-view cultivar harmonization so the bunch reaches 100% botanical consensus." |
| **12:00 – 13:30** | **Audit Trail & System Traceability** | Open `/admin/activity` (`ActivityLog.tsx`). Show the logs generated during your demo. | "Every single action—from failed logins to configuration updates and scans—is committed to an immutable Activity Log with IP address, actor UUID, timestamp, and metadata. We implemented true server-side pagination and SQL filtering to maintain instant responsiveness even after thousands of operations." |
| **13:30 – 15:00** | **Conclusion & Opening for Questions** | Switch back to Dashboard / Results view. | "In conclusion, BananaVision is not a mock UI; it is a hardened, production-grade system with real database transactions, kernel hardware control, state-of-the-art computer vision, and zero-trust security. I am now open for your questions." |

---

## 🎯 High-Probability Panel Questions & Winning Answers

### Question 1: "Why did you use JWTs instead of traditional server-side cookies/sessions?"
> **Your Answer:**  
> "BananaVision operates as a decoupled Single-Page Application (React + Vite) communicating with a FastAPI asynchronous backend, as well as high-throughput WebSockets for live camera feeds and scan telemetry. JWTs allow stateless token verification at sub-millisecond speeds. However, to solve the classic JWT revocation vulnerability (where a stolen token remains valid until expiry), **we implemented Token Versioning (`token_version`)**. Every user record in PostgreSQL holds an integer `token_version`. When a user logs out, resets their password, or has their role changed, `token_version` increments. The `deps.py` dependency checks this on every single request. If the token's embedded version doesn't match the database, it is rejected instantly."

---

### Question 2: "What stops an attacker from brute-forcing the 4-digit Operator PIN on the Kiosk?"
> **Your Answer:**  
> "A 4-digit PIN only has 10,000 combinations, making rate limiting non-negotiable. In `app/core/rate_limiter.py` and `app/api/v1/auth.py`, we implemented `pin_limiter`. It tracks failed attempts per username using an in-memory sliding window. After 5 failed attempts, the account is temporarily locked for 300 seconds (5 minutes) with an HTTP 429 Too Many Requests response, and an `AUDIT-02` security alert is automatically logged in the audit trail with the client's IP address. This makes brute force mathematically impossible."

---

### Question 3: "Why do you have two YOLO models in the code? Isn't one enough?"
> **Your Answer:**  
> "That was a deliberate architectural decision to ensure reliability. If you feed an empty tray, a coffee mug, or a person's hand into a custom-trained classifier, YOLO will still try to find the closest match and predict 'Lakatan Ripe' with low-to-medium confidence. To prevent this garbage-in-garbage-out failure:
> 1. **Stage 1 (`BananaPreDetector`):** We use a lightweight standard COCO model (`yolo26n.pt`) strictly filtering for COCO Class 46 ('banana'). If no banana is detected in any camera view, the pipeline halts immediately with a user-friendly message: *'No Lakatan, Latundan, or Cardaba detected. Place a supported banana hand on the tray and scan again.'*
> 2. **Stage 2 (`BananaClassifier`):** Only after passing the gate do we run our heavy custom-trained cultivar and ripeness model on the high-resolution multi-camera frames. Each cultivar box must also sit on banana evidence from Stage 1; a box on a foreign object is dropped and the scan is flagged for review."

---

### Question 4: "Bananas overlap heavily. How does your code count individual banana fingers without double counting?"
> **Your Answer:**  
> "Counting fingers on a dense bunch is one of the hardest computer vision challenges because fingers overlap and occlude each other. In `app/services/classification.py`, we developed four custom geometric post-processing algorithms:
> 1. **Intersection over Union (`_box_iou`) and Containment (`_box_containment`):** If one bounding box is >= 85% contained inside another of the same class, it is a sub-box fragment and discarded.
> 2. **Cluster Box Suppression (`_is_cluster_box`):** If a large box encompasses 2 or more smaller individual finger detections, the giant cluster box is removed so only the individual fingers are counted.
> 3. **Calibrated Top Overlap Refinement:** On the Top view, we raise IoU from 0.45 to 0.65 to distinguish tightly packed parallel fingers.
> 4. **180° Rotation Fallback:** Top cameras often miss fingers pointing away from the lens. We flip the image 180°, re-run inference, map the coordinates back to standard coordinates (`img_w - rx2, img_h - ry2`), and deduplicate against existing fingers using spatial axis alignment. This recovers occluded fingers without duplicate counts."

---

### Question 5: "What if Camera 1 detects 'Lakatan' but Camera 2 detects 'Cardaba'? Which one wins?"
> **Your Answer:**  
> "A single harvested banana bunch is biologically homogeneous—it is physically impossible for a bunch to be half Lakatan and half Cardaba. In `classification.py` and `fusion_engine.py`, we use **Weighted Voting Consensus**:
> - Each camera casts confidence-weighted votes for cultivar: $\sum \text{confidence}$. The cultivar with the highest total weight wins.
> - Once the bunch cultivar is established, **Cross-View Cultivar Harmonization** kicks in: any dissenting camera bounding box is harmonized to the consensus cultivar while retaining its individual ripeness grade and spatial coordinates.
> - If the winning cultivar fails to achieve 60% of the total vote weight (`VOTE_CONFLICT_THRESHOLD = 0.60`), the system flags a `conflict_detected` warning requiring manual operator inspection."

---

### Question 6: "Can an admin accidentally deactivate themselves or delete all admins, locking the kiosk forever?"
> **Your Answer:**  
> "No, we engineered the **ADMIN-01 Last Active Admin Safeguard** in `app/api/v1/users.py`. Before executing any demotion or deactivation PATCH request, the backend runs a SQL transaction lock and counts how many other active administrators exist in PostgreSQL. If the count is 0, the transaction aborts with an HTTP 409 Conflict: *'Cannot deactivate or demote the last active administrator'*. Furthermore, the endpoint serializes updates with `with_for_update()` to prevent race conditions when two admins edit concurrently."

---

## 📂 Navigation Index of Your Documentation Suite

To understand each part deeply before your presentation, review the dedicated breakdown files in this folder:

1. [01_AUTH_LOGIN_LOGOUT_SECURITY.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/01_AUTH_LOGIN_LOGOUT_SECURITY.md) — Login, PIN Swap, Rate Limiting, JWT revocation, and Security Tokens.
2. [02_USER_MANAGEMENT_AND_ACCOUNTS.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/02_USER_MANAGEMENT_AND_ACCOUNTS.md) — Create User, Edit, Activate/Deactivate, Last Admin Safeguard, Password & PIN Reset, Role Transitions.
3. [03_PROFILE_MANAGEMENT.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/03_PROFILE_MANAGEMENT.md) — Self-service Avatar update, SQL aggregate statistics, Old credential verification.
4. [04_ACTIVITY_LOGS_AND_AUDITING.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/04_ACTIVITY_LOGS_AND_AUDITING.md) — Audit logging, Server-side pagination, Search, CSV quote-escaping.
5. [05_SYSTEM_AND_SCANNER_CONFIG.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/05_SYSTEM_AND_SCANNER_CONFIG.md) — 4-Camera Hardware Mapping, Live Preview MJPEG generator, Station Lock, System Power.
6. [06_DATA_RETENTION_AND_EXPORT.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/06_DATA_RETENTION_AND_EXPORT.md) — Data retention policy, unreferenced capture cleanup, CSV scan export vs backup.
7. [07_LANDING_PAGE.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/07_LANDING_PAGE.md) — Public Landing Showcase, Responsive navigation, Kiosk vs Admin entrypoints.
8. [08_YOLO_DETECTION_AND_AI_PIPELINE.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/08_YOLO_DETECTION_AND_AI_PIPELINE.md) — Deep Code Breakdown of Pre-Detection, YOLOv26 inference, Rotation Fallback, Geometric Deduplication, and Multi-Camera Fusion.
