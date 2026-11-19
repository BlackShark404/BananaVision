# BananaVision - Capstone Project Summary

## 1. Executive Summary

BananaVision is an intelligent, edge-deployed computer vision kiosk and post-harvest management system designed for the Philippine banana industry. Operating at agricultural packing houses and sorting stations, it automates cultivar classification, ripeness grading, individual finger counting, and shelf-life prediction using a synchronized multi-camera vision array paired with environmental IoT sensing. 

The system replaces manual, subjective visual inspection with standardized artificial intelligence, providing immediate quality verification, automated QR code batch labeling, and end-to-end inventory traceability.

---

## 2. Problem Statement

Post-harvest banana sorting in traditional agricultural facilities suffers from key operational bottlenecks:

- **Subjective and Inconsistent Grading:** Manual inspection relies on human visual judgment, which varies significantly between workers and degrades over long shifts due to visual fatigue.
- **Cultivar and Ripeness Misclassification:** Differentiating between closely related commercial cultivars (such as Lakatan, Latundan, and Cardaba) across varying ripeness stages (Unripe, Semi-Ripe, Ripe, Overripe) is error-prone.
- **Unpredictable Shelf Life:** Visual appearance alone does not account for environmental storage conditions (temperature and humidity), leading to premature spoilage, poor inventory planning, and financial losses.
- **Lack of Traceability:** Traditional sorting stations rarely record batch-level provenance or inspection evidence, making it difficult for downstream buyers, retailers, and distributors to verify produce quality.

---

## 3. The BananaVision Solution

BananaVision introduces an all-in-one physical inspection kiosk powered by edge computing:

1. **Multi-Angle Vision Rig:** An enclosure housing four synchronized high-resolution USB cameras (Top, Left, Right, and Rear) captures every angle of a banana bunch in a single scan cycle, eliminating blind spots and perspective foreshortening.
2. **Two-Stage AI Pipeline:** 
   - *Stage 1 (Pre-Detection Gate):* A lightweight COCO YOLO model checks if a banana bunch is present on the inspection platter, preventing accidental scans of empty trays or foreign objects.
   - *Stage 2 (Classification and Detection):* A custom-trained YOLO model detects individual banana fingers, determines the cultivar (Lakatan, Latundan, Cardaba), and grades the ripeness stage (Unripe, Semi-Ripe, Ripe, Overripe) with bounding box visualization.
3. **Multi-Camera Fusion and Spatial Deduplication:** A custom consensus algorithm merges the multi-camera detections using confidence-weighted voting to establish a unified bunch-level cultivar. Geometric algorithms (IoU deduplication, cluster box suppression, and 180-degree rotation fallback) count banana fingers accurately without double-counting occluded fruit.
4. **Environmental Spoilage Prediction:** An Arduino-connected DHT22 sensor captures real-time ambient temperature and relative humidity. A Random Forest regression model combines visual ripeness with Vapor Pressure Deficit (VPD) to predict remaining shelf life in days.
5. **Instant Batch Labeling:** An integrated thermal label printer (Grozziie TP870 S) generates 40mm x 30mm adhesive labels containing human-readable grading data and a scannable QR code.
6. **Public Verification:** Downstream buyers or consumers can scan the printed QR code with any smartphone camera to verify cultivar, ripeness, harvest date, and spoilage estimates on a public tracking page without needing an account.

---

## 4. System Architecture

```text
[ Physical Kiosk Station ]
  ├── 4x USB Cameras (Top, Left, Right, Rear)
  ├── Arduino Uno + DHT22 (Temperature & Humidity)
  ├── Grozziie TP870 S (Thermal Label Printer)
  └── Touchscreen Kiosk Display

[ Station Mini PC / Edge Node ]
  ├── Backend Server (FastAPI + Python 3.12)
  │     ├── Two-Stage YOLO Object Detection (PyTorch + CUDA/CPU)
  │     ├── Random Forest Spoilage Model (scikit-learn)
  │     ├── Multi-Camera Consensus Fusion Engine
  │     ├── Windows DirectShow Camera Manager & GDI Print Worker
  │     └── Native WebSockets (Real-time telemetry & scan events)
  ├── Database (PostgreSQL + SQLAlchemy Async ORM)
  │     └── 18 relational tables (Users, Scans, Detections, Intakes, Audits)
  └── Frontend Web Application (React 19 + TypeScript + Vite + Tailwind CSS)
        ├── Kiosk Mode (Fullscreen touch interface for station operators)
        └── Management Portal (Role-based administrative dashboard)
```

---

## 5. User Roles and Workflows

### A. Station Operator (Warehouse / Kiosk Mode)
- **Fast Authentication:** Quick 4-digit PIN login with automatic lockout protection against brute-force attempts.
- **One-Touch Scan:** Places the banana bunch on the tray, selects the delivery batch, and taps "Scan Now".
- **Live Progress:** Watches real-time WebSocket progress through capturing, detection, and analysis stages.
- **Inspection Verification:** Reviews the fused classification card, confidence rating, finger count, and multi-camera bounding boxes.
- **Accept or Flag:** Accepts the verified scan into inventory or flags questionable batches for administrator review.
- **Label Printing:** Generates instant adhesive QR labels for crates or banana bunches.

### B. Administrator (Management & Quality Control)
- **Dashboard & Analytics:** Monitors real-time scan volume, cultivar distributions, ripeness breakdowns, and inventory levels.
- **Quality Control (QC):** Reviews flagged scans, examines per-camera evidence, and can manually override classifications with complete change history tracking.
- **User Governance:** Manages user accounts, assigns roles (Admin vs. Operator), generates temporary credentials, and enforces strict security policies.
- **Hardware Calibration:** Configures camera slots, maps physical USB devices, tests live preview feeds, and adjusts detection confidence thresholds.
- **Data & Station Control:** Manages data retention policies, exports CSV reports, performs full system backups with SHA-256 validation, and executes graceful system shutdowns or restarts.

### C. Downstream Buyer / Consumer (Public Tracking)
- Scans the printed QR code using a mobile device to open `/track/:scanId`.
- Instantly verifies produce authenticity, classification grade, and estimated days until spoilage without logging in.

---

## 6. Key Innovations and Engineering Highlights

1. **Two-Stage Failure Prevention:** Uses a general COCO model as an admission gate before running specialized classification, ensuring the system never classifies empty trays or non-banana objects.
2. **Solving Occlusion and Overlap:** Implements 180-degree rotation fallback and calibrated IoU thresholds to accurately count fingers in dense, overlapping bunches.
3. **Biological Consensus Harmonization:** Prevents impossible mixed-cultivar results by enforcing confidence-weighted voting across camera views while preserving individual ripeness observations.
4. **Environmental Shelf-Life Modeling:** Enhances simple image classification by integrating physics-based Vapor Pressure Deficit (VPD) and temperature into empirical spoilage regression.
5. **Hardened Security Architecture:** Features JSON Web Tokens with database token versioning (instant session revocation on logout), memory-backed sliding-window rate limiters, and safeguards preventing the deactivation of the last active administrator.

---

## 7. Business and Impact Value

- **Quality Consistency:** Replaces human estimation with repeatable, objective computer vision grading.
- **Food Waste Reduction:** Accurate spoilage predictions enable First-Expired, First-Out (FEFO) inventory management, ensuring produce reaches consumers before spoiling.
- **Market Transparency:** QR-based traceability builds buyer trust between local banana growers, packaging facilities, and retail supermarkets.
- **Cost-Effective Edge Deployment:** Built on standard, accessible commercial hardware (USB webcams, Mini PC, thermal printer) rather than expensive proprietary sorting machines, making it viable for local packing stations in developing agricultural economies.

