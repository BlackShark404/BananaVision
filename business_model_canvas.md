# 🍌 BananaVision — Accurate Business Model Canvas

> **Document Type:** Commercialization Strategy & Enterprise Business Model  
> **System:** BananaVision — Edge IoT Multi-Camera Banana Classification & Spoilage Prediction System  
> **Architecture:** 100% Offline Edge Kiosk (Mini PC + 4-Camera DirectShow Array + Arduino DHT22 Sensor + Grozziie TP870 S Thermal Label Printer)  
> **Target Market:** Banana Packhouses, Consolidators, Commercial Processors, and Supermarket Logistics Centers  
> **Framework:** Alexander Osterwalder 9-Box Business Model Canvas  

---

## 1. Executive Summary

BananaVision automates post-harvest banana inspection by replacing subjective, fatigue-prone human grading with sub-second, multi-camera Edge AI vision. Operating entirely on an on-premise Mini PC kiosk without cloud or internet dependence, the system integrates:
1. **Parallel 4-Camera Vision (Top, Left, Right, Rear):** Captures multi-angle imagery to classify Philippine cultivars (**Lakatan, Latundan, Cardaba**) across 4 maturity stages (**Unripe, Semi-Ripe, Ripe, Overripe**).
2. **Non-Destructive Finger Counting:** Eliminates manual fruit touching by applying 180° rotation fallback, cluster box elimination, and spatial containment filtering to count fingers on dense bunches.
3. **Predictive Spoilage Modeling:** Computes ambient Vapor Pressure Deficit (VPD) via an Arduino DHT22 sensor to predict remaining shelf life (in days) using a Random Forest Regressor.
4. **Physical Batch Traceability:** Immediately prints 40×30 mm adhesive QR prediction labels at the station, encoding scan UUID, cultivar, ripeness, and shelf-life days directly onto crates to power **First-Expired, First-Out (FEFO)** inventory dispatch.

---

## 2. Visual Business Model Canvas (9-Box Osterwalder Grid)

```
┌─────────────────────────┬─────────────────────────┬─────────────────────────┬─────────────────────────┬─────────────────────────┐
│     KEY PARTNERS        │     KEY ACTIVITIES      │   VALUE PROPOSITIONS    │  CUSTOMER RELATIONSHIPS │    CUSTOMER SEGMENTS    │
│                         │                         │                         │                         │                         │
│ • Department of         │ • 2-Stage YOLO & AI R&D │ • Objective, Bias-Free  │ • Dedicated On-Site     │ • Banana Packhouses &   │
│   Agriculture (DA-BAR,  │   (Pre-detector gate +  │   Ripeness & Quality    │   Commissioning &       │   Consolidators         │
│   BPI, DOST-PCAARRD)    │   3-cultivar classifier)│   Grading (Sub-second)  │   Optical Calibration   │   (Intake quality check │
│                         │                         │                         │                         │   & supplier payouts)   │
│ • Banana Growers Assocs │ • Multi-Angle Rig &     │ • Cultivar-Specific     │ • Tiered Hardware &     │                         │
│   & Co-ops (PBGEA)      │   Kiosk Assembly        │   Accuracy (Lakatan,    │   Software SLAs         │ • Banana Processors     │
│                         │                         │   Latundan, Cardaba)    │   (Guaranteed repairs)  │   (Chips: Unripe vs.    │
│ • Hardware & Sensor     │ • Packhouse On-Site     │                         │                         │   Puree/Sauce: Ripe)    │
│   OEMs (Mini PC, USB    │   Commissioning         │ • Non-Destructive Multi-│ • Continuous Model      │                         │
│   Cameras, Grozziie)    │                         │   Angle Finger Counting │   Retraining & Weight   │ • Supermarket & Retail  │
│                         │ • Proprietary Image     │   (Rotation fallback)   │   Updates               │   Distribution Centers  │
│ • Packhouse Sorting     │   Dataset Annotation    │                         │                         │   (Shelf-life control & │
│   Line Integrators      │                         │ • Predictive Shelf-Life │ • Intuitive Operator    │   FEFO dispatch)        │
│                         │ • Software Governance,  │   Estimation (VPD-based │   Enablement (4-digit   │                         │
│ • Post-Harvest Academic │   Zero-Trust Auth &     │   FEFO Inventory Mgmt)  │   PIN swap & Demo mode) │ • Banana Exporters      │
│   Research Institutions │   Audit Trail Trace     │                         │                         │   (Phytosanitary &      │
│                         │                         │ • Instant Physical QR   │                         │   finger count compl.)  │
│                         ├─────────────────────────┤   Carton Label Printing │                         │                         │
│                         │      KEY RESOURCES      │   (UUID & Spoilage days)├─────────────────────────┤ • Agri Co-ops & Trading │
│                         │                         │                         │        CHANNELS         │   Centers (Bagsakan)    │
│                         │ • Proprietary Multi-    │ • 100% Offline Edge     │                         │   (Fair grading trust)  │
│                         │   Angle Image Dataset   │   Autonomy (Zero Cloud/ │ • Direct B2B Enterprise │                         │
│                         │                         │   Internet required)    │   Field Sales           │                         │
│                         │ • Trained Weights & IP  │                         │                         │                         │
│                         │   (YOLO & Spoilage RFR) │                         │ • On-Site Pilot Trials  │                         │
│                         │                         │                         │   (2-4 Week Live PoC)   │                         │
│                         │ • Edge Hardware Assets  │                         │                         │                         │
│                         │   (Mini PC, 4 Cameras,  │                         │ • DA & DOST Extension   │                         │
│                         │   Sensors, Printer)     │                         │   & Demo Programs       │                         │
│                         │                         │                         │                         │                         │
│                         │ • Core Software Stack   │                         │ • Packhouse Equipment   │                         │
│                         │   (FastAPI, React, SQL) │                         │   Integrators & VARs    │                         │
│                         │                         │                         │                         │                         │
│                         │ • CV & Agri Engineers   │                         │ • Agri Expos (Agrilink) │                         │
├─────────────────────────┴───────────┬─────────────┴─────────────────────────┴───────────┬─────────────┴─────────────────────────┤
│            COST STRUCTURE           │                                                   │            REVENUE STREAMS            │
│                                     │                                                   │                                       │
│ • Hardware Bill of Materials (BOM)  │                                                   │ • Turnkey Hardware Kiosk Sales (CapEx)│
│   (Mini PC, 4 Cameras, Arduino,     │                                                   │   Direct sale of physical station     │
│   DHT22 sensor, TP870 S printer)    │                                                   │                                       │
│                                     │                                                   │ • Software License & AI Support (SaaS)│
│ • R&D & Model Training Compute      │                                                   │   Annual/monthly recurring license    │
│   (Cloud GPU instances for YOLO runs│                                                   │                                       │
│                                     │                                                   │ • Installation & Commissioning Fee    │
│ • Image Dataset Collection & Pomological Annotation                                     │   On-site setup & operator training   │
│                                                                                         │                                       │
│ • Field Deployment, Travel & Calibration Expenses                                       │ • Annual Maintenance Contracts (AMC)  │
│                                                                                         │   Hardware calibration & SLA support  │
│ • Warranty Reserve, Spare Parts Buffer & Support Salaries                               │                                       │
│                                                                                         │ • Consumables (40x30mm thermal labels)│
│                                                                                         │                                       │
│                                                                                         │ • Custom ERP Integrations & Models    │
└─────────────────────────────────────────────────────────────────────────────────────────┴───────────────────────────────────────┘
```

---

## 3. The 9 Building Blocks — Deep Dive

### 3.1 Key Partners
*Strategic alliances that optimize supply chain, credibility, and deployment:*

- **Department of Agriculture (DA) & Attached Agencies:**  
  *Entities:* DA-BAR (Bureau of Agricultural Research), BPI (Bureau of Plant Industry), DOST-PCAARRD.  
  *Value:* Accreditation of BananaVision as an approved post-harvest modernization technology, access to government research grants, and integration into municipal agricultural extension programs.
- **Banana Growers Associations & Cooperatives:**  
  *Entities:* PBGEA (Pilipino Banana Growers and Exporters Association), Mindanao banana federations, agrarian reform farmer cooperatives.  
  *Value:* Direct access to commercial packing facilities, bulk fruit availability for continuous model testing, and collective purchasing agreements.
- **Hardware & Component OEMs:**  
  *Entities:* Industrial USB camera manufacturers (DirectShow/UVC compliant), embedded microcontroller makers (Arduino), sensor fabricators (DHT22), and direct thermal printer OEMs (Grozziie TP870 S).  
  *Value:* Bulk component purchasing discounts, stable hardware supply, and long-term driver support.
- **Packinghouse Automation & Conveyor Integrators:**  
  *Value:* Engineering contractors who design mechanical sorting conveyors and packing tables, allowing BananaVision to be bundled directly into packhouse sorting lines.
- **Academic & Research Institutions (Pomology Labs):**  
  *Value:* Academic partners (e.g., UPLB, USM) providing ground-truth pomological validation for cultivar genetics, natural vs. ethephon ripening profiles, and shelf-life decay curves.

---

### 3.2 Key Activities
*Core operational, engineering, and service work required to deliver value:*

- **Computer Vision & Spoilage AI Engineering:**
  - Developing and maintaining the **Two-Stage Detection Architecture**:
    - *Stage 1:* Pre-detection gate (`banana_detector.py`) filtering for COCO Class 46 ("banana") to reject empty trays or foreign items before inference.
    - *Stage 2:* Multi-cultivar classification (`classification.py`) detecting Lakatan, Latundan, and Cardaba across Unripe, Semi-Ripe, Ripe, and Overripe states.
  - Engineering post-processing algorithms: **Cluster Box Elimination**, **180° Rotation Fallback** (detecting occluded fingers pointing away from top camera), and **Cross-View Cultivar Harmonization**.
  - Calibrating the **Random Forest Spoilage Regressor** (`spoilage.py`) using real-time Vapor Pressure Deficit (VPD) and intake treatment metadata.
- **Edge Hardware Assembly & Optical Calibration:**
  - Fabricating and assembling the 4-camera DirectShow array (Top, Left, Right, Rear) with 15 FPS DirectShow MJPG acquisition.
  - Tuning diffuser hoods and LED illumination to prevent table-edge glare and shadow artifacts.
- **Packhouse On-Site Commissioning:**
  - Physical kiosk placement, optical focus alignment, local LAN network configuration, and Grozziie printer integration.
- **Dataset Expansion & Pomological Annotation:**
  - Curation of multi-angle high-resolution images across lighting conditions, seasons, and defect profiles with expert manual labeling.
- **Software Governance & Security Hardening:**
  - Maintaining zero-trust authentication, token versioning (`tv`) session revocation, brute-force PIN rate limiters, immutable audit logging, and atomic last-admin protections.

---

### 3.3 Key Resources
*Crucial tangible, digital, and human assets:*

- **Proprietary AI Models & Code IP:**
  - Custom YOLO weights (`.pt`) trained on Philippine banana cultivars.
  - Random Forest Spoilage predictor (`spoilage_rfr.joblib`).
  - Multi-camera weighted voting fusion engine (`fusion_engine.py`).
- **Proprietary Multi-Camera Banana Dataset:**
  - Thousands of synchronized 4-view image sets with verified ground-truth annotations (bounding boxes, cultivars, ripeness grades, finger counts, and temperature/humidity readings).
- **Physical Hardware Assets:**
  - Rugged edge Mini PC running the local backend and database.
  - 4-Camera optical rig with diffused industrial LED lighting.
  - Arduino microcontroller and DHT22 temperature/humidity sensor.
  - Grozziie TP870 S direct thermal label printer (40 × 30 mm).
  - Industrial touch-screen kiosk monitor and mounting chassis.
- **Software Stack:**
  - FastAPI asynchronous backend with WebSocket live event streaming.
  - React 19 / TypeScript / Vite responsive touch frontend.
  - Local PostgreSQL database with automated Alembic migrations.
- **Domain Talent:**
  - Computer vision researchers, embedded IoT engineers, agribusiness solution managers, and full-stack software engineers.

---

### 3.4 Value Propositions
*The core benefits and operational advantages BananaVision provides:*

1. **Objective, Bias-Free Quality Grading:**  
   Eliminates human visual inspection errors, operator fatigue, and disputes between growers and packhouses by delivering standardized, reproducible AI grading.
2. **Sub-Second Multi-View Cultivar & Ripeness Classification:**  
   Parallel 4-camera inference classifies cultivar (Lakatan, Latundan, Cardaba) and ripeness stage in seconds directly on the packing line.
3. **Non-Destructive Automated Finger Counting:**  
   Accurately counts individual banana fingers on tightly bunched hands using parallel multi-view capture, containment filtering, and 180° rotation fallback without damaging fruit.
4. **VPD-Driven Predictive Shelf-Life (FEFO Inventory):**  
   Incorporates ambient temperature, humidity, and Vapor Pressure Deficit (VPD) to estimate remaining shelf life in days. Allows packhouses to practice **First-Expired, First-Out (FEFO)** inventory management, significantly reducing post-harvest shrinkage.
5. **Physical Box-Level Traceability via Instant QR Labels:**  
   Immediately prints 40 × 30 mm adhesive thermal labels encoding scan UUID, cultivar, ripeness grade, and predicted shelf-life days directly onto crates.
6. **100% Offline Edge Resilience:**  
   Requires zero internet connection. Functions continuously on a local Mini PC and LAN in rural agricultural packing facilities.

---

### 3.5 Customer Relationships
*How BananaVision acquires, supports, and retains clients:*

- **Dedicated On-Site Commissioning & Calibration:**  
  Hands-on installation, optical alignment, and baseline calibration tailored to the specific packhouse lighting and line geometry.
- **Tiered Service Level Agreements (SLAs) & Hardware Support:**  
  Guaranteed response times, scheduled camera/sensor recalibration, and rapid hardware hot-swaps.
- **Continuous Model Evolution:**  
  Quarterly or seasonal AI weight updates incorporating regional variations, new cultivars, or subtle seasonal color shifts.
- **Intuitive Operator Enablement:**  
  Minimal onboarding friction using fast 4-digit PIN swapping, dedicated Kiosk mode, and interactive demo simulation modes for new staff.

---

### 3.6 Channels
*How BananaVision markets, sells, and delivers its system:*

- **Direct B2B Enterprise Field Sales:**  
  Direct consultative sales to commercial banana plantation operators, packhouse owners, food processing corporate buyers, and supermarket supply chain directors.
- **Supervised On-Site Pilot Trials (Proof-of-Concept):**  
  Deploying trial kiosks for 2 to 4 weeks on live packing lines to demonstrate tangible waste reduction, throughput acceleration, and grading consistency.
- **Government Agriculture Programs & Extension Channels:**  
  Showcasing BananaVision through DA-BAR, DOST, and regional trade expos as an accredited post-harvest modernization technology.
- **Agri-Tech Distributors & Sorting Line OEMs:**  
  Partnering with manufacturers of packinghouse washing, sorting, and conveyor lines to bundle BananaVision as the intelligent inspection module.
- **Industry Expos & Conventions:**  
  Live interactive hardware demonstrations at major agricultural trade fairs (e.g., Agrilink, Food & Hotel Philippines, National Banana Congress).

---

### 3.7 Customer Segments
*Target enterprises and commercial beneficiaries:*

1. **Banana Packing Houses & Consolidators:**  
   *Core Need:* Rapid intake grading of incoming truck deliveries from multiple smallholder farmers to automate supplier payouts and batch sorting.
2. **Commercial Banana Processors & Food Manufacturers:**  
   *Core Need:* Strict maturity separation (e.g., banana chip producers requiring 100% Stage 1 Unripe bananas; puree, baby food, and catsup makers requiring Stage 3 Ripe bananas).
3. **Supermarket Chains & Retail Logistics Distribution Centers:**  
   *Core Need:* Standardized freshness verification at warehouse intake, shelf-life estimation, and reduction of retail display rot.
4. **Commercial Banana Exporters:**  
   *Core Need:* Stringent quality compliance, exact finger counts, and traceable QR labels for export cartons bound for foreign markets.
5. **Agricultural Cooperatives & Trading Centers ("Bagsakan"):**  
   *Core Need:* Transparent, objective grading to build trust between farmers and consolidators.

---

### 3.8 Cost Structure
*Operational and capital expenses required to build and maintain the business:*

- **Hardware Bill of Materials (BOM) & Kiosk Assembly:**  
  Rugged Mini PC units, 4 DirectShow-compatible USB cameras, Arduino boards, DHT22 sensors, Grozziie TP870 S printers, power supplies, mounting arms, and industrial enclosures.
- **R&D & Engineering:**  
  Software development (FastAPI backend, React frontend), computer vision model architecture, and cloud GPU compute for training runs.
- **Data Operations & Annotation:**  
  Collecting thousands of real-world multi-camera banana images across light intensities, field conditions, and defect stages; expert manual annotation.
- **Field Deployment, Travel & Commissioning:**  
  Technician travel to regional packing facilities, physical mounting, electrical wiring, and on-site staff training.
- **Warranty, Replacement Parts & Technical Support:**  
  Buffer stock for immediate camera/sensor replacement, remote telemetry support, and administrative overhead.

---

### 3.9 Revenue Streams
*Sustainable monetization models:*

1. **Hardware Kiosk Sales (CapEx Model):**  
   Turnkey purchase of the complete BananaVision hardware inspection station (Mini PC, 4-camera rig, sensors, printer, and frame).
2. **Software Licensing & AI Subscription (SaaS / OpEx Model):**  
   Recurring annual/monthly station software license covering the multi-camera inference pipeline, WebSocket kiosk telemetry, administrative dashboards, and continuous model accuracy updates.
3. **Setup, Calibration & Commissioning Fees:**  
   One-time professional fee for on-site station deployment, optical calibration, network integration, and operator training.
4. **Annual Maintenance Contracts (AMC) & Support SLAs:**  
   Paid ongoing support covering annual sensor recalibration, preventative maintenance, optical cleaning, and priority hardware replacement.
5. **Consumables & Hardware Accessories:**  
   Ongoing recurring revenue from sales of custom 40×30 mm thermal label rolls, replacement sensors, and auxiliary cameras.
6. **Custom Enterprise Integration & Bespoke Model Training:**  
   Professional services fees for integrating BananaVision with enterprise ERPs (SAP, NetSuite) and training models on additional banana cultivars (e.g., Saba, Morado, Cavendish).

---

## 4. Gap Matrix: Original Draft vs. Accurate BMC

| Canvas Building Block | Original Draft (User's Image) | Revised & Accurate Model | Rationale & Why This Matters |
| :--- | :--- | :--- | :--- |
| **Key Partners** | Hardware & Sensor Suppliers, **Cloud Hosting Providers** | DA Agencies (DA-BAR, BPI, DOST), Agri Co-ops (PBGEA), Hardware OEMs (Cameras, Mini PCs, Printers), Packhouse Integrators, Research Labs | **Cloud Hosting Providers is inaccurate** because BananaVision runs 100% offline on an edge Mini PC over LAN. Agriculture agencies and packinghouse equipment integrators are vastly more critical partners. |
| **Key Activities** | AI Model Training, System Development, Hardware Assembly, Usability Testing, **YOLO26small System Development** | 2-Stage YOLO & Spoilage R&D, Edge Kiosk Fabrication & Assembly, Packhouse On-Site Commissioning, Ground-Truth Annotation, Security & Audit Governance | **"YOLO26small System Development" is awkwardly specific, redundant, and technically strange.** Replaced with professional R&D, calibration, deployment, and governance activities. |
| **Key Resources** | **Manual Dataset**, Hardware Infrastructure, Software Infrastructure | Proprietary Cultivar & Ripeness Dataset, Edge Vision & IoT Rig (Mini PC, 4 Cameras, Arduino, Printer), Proprietary ML Weights (`.pt`/`.joblib`), Core Codebase & IP, Domain Talent | "Manual Dataset" was vague and undersold the asset. Clarified the tangible hardware components, software IP, and specialized human capital. |
| **Value Propositions** | Reduced Post-Harvest Losses, **Instantaneous Batch Classification**, Cultivar-Specific Accuracy, Optimized Inventory Management | Objective Quality Grading, Sub-second Multi-view Classification, Non-Destructive Multi-angle Finger Counting, Predictive Shelf Life (VPD/FEFO), Physical QR Label Traceability, 100% Offline Edge Autonomy | Clarified that inspection is rapid unit-by-unit scanning of intake batches, and highlighted BananaVision's true superpowers: finger counting, VPD spoilage prediction, QR printing, and offline resilience. |
| **Channels** | **Role-Based Web Dashboard**, Field Demonstrations, DA Partnerships | Direct B2B Enterprise Sales, Supervised On-Site Pilot Trials, Government Agribusiness Extension, Agri-Tech Integrators, Industry Expos | **A web dashboard is NOT a business channel; it is the software product UI / touchpoint.** Real channels are how the product is sold and distributed (B2B sales, pilot trials, VARs). |
| **Customer Relationships** | Supervised Pilot Testing, On-Site Training, Responsive Support | Dedicated On-Site Commissioning, Tiered SLAs & Hardware Maintenance, Continuous Model Updates, Intuitive Operator Enablement (PIN swap/Demo mode) | Expanded from generic "support" to enterprise B2B support models (SLAs, model retraining, calibration). |
| **Cost Structure** | Hardware Procurement, **Software & Local Server Hosting**, Development & Maintenance | Hardware BOM & Assembly, ML R&D & Compute, Data Operations & Annotation, Field Deployment & Travel, Support & Warranty Reserves | "Software & Local Server Hosting" is contradictory; local servers don't pay hosting fees. Clarified physical BOM, GPU training compute, dataset curation, and deployment travel. |
| **Revenue Streams** | System Setup & Installation Fee, Technical Support & Maintenance Fee | Hardware Kiosk Sales (CapEx), Software & AI Subscription (SaaS), Commissioning Fees, Annual Maintenance Contracts (AMC), Consumables (Labels), Enterprise ERP Integrations | The original draft missed the primary revenue drivers: Hardware station sales (CapEx), recurring software licensing (SaaS), and continuous consumable sales (label rolls). |

---

## 5. Strategic Defense Guide for Presentation Panels & Investors

When presenting this canvas to a thesis panel, government grant committee, or agribusiness investor:

1. **Emphasize the Edge Advantage Over Cloud AI:**  
   Most agricultural packhouses in Davao, Bukidnon, and provincial trading centers have spotty cellular/broadband coverage. BananaVision’s local Mini PC architecture eliminates cloud dependency, latency, and subscription downtime risks.
2. **Clarify the Hybrid Revenue Model (CapEx + SaaS):**  
   Agribusinesses prefer owning physical hardware assets (CapEx), while recurring software licenses (SaaS) and continuous thermal label consumables generate strong Customer Lifetime Value (LTV) and predictable annual recurring revenue (ARR).
3. **Connect AI Features Directly to Packhouse ROI:**  
   - **Sub-Second Classification:** Accelerates intake truck turnover.
   - **VPD Spoilage Prediction:** Enforces First-Expired, First-Out (FEFO) inventory rotation, directly cutting post-harvest shrinkage.
   - **Thermal QR Labeling:** Attaches a physical digital identity to every carton, ensuring dispute-free compliance with supermarket buyers and exporters.
