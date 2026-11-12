# BananaVision — 80:20 Undergraduate Capstone Thesis Defence Preparation Guide

> **Official Title:** *BANANAVISION: AN INTELLIGENT SYSTEM FOR BANANA RIPENESS DETECTION* (**CONFIRMED BY THESIS**, Title Page, PDF p. 1)
> **Researchers:** Khen D. Sorela, Arlon N. Rondina, Kent RG A. Baguio, Lawrence S. Ramirez | **Adviser:** Angelbert P. Maghanoy, Ph.D. | **CTU – Main Campus (BSIT)**
> **Tags:** **[CONFIRMED BY THESIS]**, **[INFERRED]**, **[MISSING OR UNCLEAR]**, **[VERIFY EXTERNALLY]**

---

## SECTION 1: THESIS MAP

- **Central Problem & Claim:** Manual banana grading in Cebu's medium and large enterprises (processing facilities, retail grocery chains, wholesale distributors) is subjective and ignores storage microclimate, contributing to $>20\%$ post-harvest wastage (**CONFIRMED BY THESIS**, Ch. I, pp. 1–3). BananaVision automates cultivar/ripeness grading and shelf-life estimation on a local edge kiosk.
- **Research Objectives:** (1) Build a 4-camera + Arduino DHT22 LED-lit edge kiosk; (2) Train YOLOv26 on **Lakatan, Latundan, and Cardaba** across four ripeness stages; (3) Train a 6-feature Random Forest Regressor (RFR) for days-to-spoilage estimation; (4) Build an Admin/Operator web platform on PostgreSQL; (5) Evaluate classification, RFR MAE, and SUS usability (**CONFIRMED BY THESIS**, Ch. I, pp. 5–6).
- **Methodology & Core Tech:** Agile concurrent engineering; 14-day longitudinal dataset of 4,171 raw images (37,316 annotations; augmented to 10,845; 80/10/10 split) for **YOLO26s**, and 3,964 records (3,150 train / 814 test) for **RFR** using cultivar, ripeness, temperature, humidity, VPD, and treatment (**CONFIRMED BY THESIS**, Ch. III, pp. 53–65).
- **Research Contribution:** Localized Philippine cultivar grading under DA **PNS/BAFPS 8:2004**, paired with VPD-informed spoilage regression and local PostgreSQL traceability.
- **Weakest Points & Panel Focus:** (1) Objective 5's color-histogram benchmark is **MISSING OR UNCLEAR** in Ch. III; (2) Ripeness accounts for $\approx 82\%$ of RFR MDI importance while environmental features contribute $<5\%$ (**CONFIRMED BY THESIS**, Fig. 19, p. 65); (3) Multi-view capture splitting risks scene leakage (**INFERRED**). Philippine BSIT panels focus on objective-to-result alignment, dataset integrity, sensor necessity, and live workflow reliability.

---

## SECTION 2: THE 12 HIGHEST-VALUE DEFENCE QUESTIONS

### Q1. Objective 5 vs. Reported Evaluation Results (Color-Histogram Benchmark & Accuracy)
- **Question:** *"Objective 5 states you will benchmark classification accuracy, precision, and recall against a baseline color-histogram classifier. Where is that comparison table in Chapter III?"*
- **Examiner Perspective:** Internal Examiner
- **Why It Matters:** Panels verify whether every Chapter I objective has a matching result table in Chapter III.
- **What the Examiner Is Testing:** Objective-to-finding alignment.
- **What a Strong Answer Must Prove:** Scope 5.2.1's $\ge 80\%$ target was surpassed across precision, recall, F1, and mAP, while conceding the omitted color-histogram comparison table honestly.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Objective 5 (p. 6); Scope 5.2.1 ($\ge 80\%$ target, p. 8); Ch. III YOLOv26s: **87.12% precision, 89.41% recall, 88.25% F1, 94.11% mAP@50, 87.70% mAP@50–95** (pp. 57–61, Table 13, Figs. 14–17). **MISSING OR UNCLEAR**: Color-histogram table in pp. 56–66.
- **Risk Level:** **High**

### Q2. Do Temperature, Humidity, and VPD Actually Improve Shelf-Life Prediction?
- **Question:** *"In Figure 19, encoded ripeness stage accounts for 82% of RFR feature importance, and ripeness, treatment, and cultivar reach 95%. Since VPD, temperature, and humidity contribute only 5%, does the DHT22 sensor matter?"*
- **Examiner Perspective:** Sceptical but Fair Examiner / Technical Subject Specialist
- **Why It Matters:** Challenges whether the IoT sensor adds real predictive value (Concern #5).
- **What the Examiner Is Testing:** Understanding of Mean Decrease in Impurity (MDI) vs. physical microclimate influence.
- **What a Strong Answer Must Prove:** Ripeness sets the **macro bracket** (Unripe 6–9d vs. Overripe 1–2d); temperature, humidity, and VPD provide **within-stage refinement**. Narrow open-air thermal range lowers global tree-split MDI.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Fig. 19 (p. 65) reports $\approx 82\%$ MDI for ripeness and $\approx 95\%$ for top 3 features, noting low MDI does not mean zero physical effect; Limitation 4 (p. 10) notes open-air bounds. **[VERIFY EXTERNALLY]**: Magnus-Tetens VPD equation.
- **Risk Level:** **High**

### Q3. Shelf-Life Ground Truth and Validating RFR Without Waiting for Live Scan Decay
- **Question:** *"How did you establish ground-truth remaining days for your 3,964 RFR samples, and how can you defend RFR accuracy today without waiting 10 days for a scanned banana to rot?"*
- **Examiner Perspective:** Methodology Examiner
- **Why It Matters:** Explains longitudinal target derivation and modular validation (Concerns #6, #7).
- **What the Examiner Is Testing:** Target derivation (`spoilage_days`) and two-stage validation.
- **What a Strong Answer Must Prove:** Ground truth came from tracking batches over **14 days** to terminal spoilage. RFR takes 6 tabular features (not pixels), so testing on 814 held-out rows (**MAE = 0.7205d, RMSE = 0.9822d, $R^2 = 0.9552$**) validates regression while YOLO + DHT22 automate inputs.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Ch. III (pp. 54–55, 63–64; Fig. 18): **3,964 samples (3,150 train / 814 test)**, 300 trees, `max_depth=20`, `min_samples_split=5`, `min_samples_leaf=2`, **MAE = 0.7205d, RMSE = 0.9822d, $R^2 = 0.9552$**, P10–P90 coverage **46.8%** (width **1.31d**). **MISSING OR UNCLEAR**: Numerical peel-spotting cutoff beyond DA **PNS/BAFPS 8:2004** charts.
- **Risk Level:** **High**

### Q4. Multi-View Capture Splitting and Data Leakage Risk
- **Question:** *"You captured 4,171 images from four cameras over 14 days and augmented them to 10,845 with an 80/10/10 split. Were all views and days of each physical banana hand kept in the same split?"*
- **Examiner Perspective:** Methodology Examiner / Technical Subject Specialist
- **Why It Matters:** Sharing views of the same bunch across splits inflates test mAP@50 (**94.11%**) compared to unseen bunches.
- **What the Examiner Is Testing:** Group-level vs. image-level splitting in multi-camera datasets.
- **What a Strong Answer Must Prove:** Explain the 80/10/10 class-stratified split and concede that physical-bunch-isolated splitting is needed for unseen-bunch benchmarking.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Scope 5.1.1–5.1.4 (p. 8), Definition of Terms (p. 14), Ch. III (p. 54): 4,171 raw images, 37,316 annotations, augmented to 10,845, 80/10/10 split. **INFERRED** (`docs/yolo-dataset-audit-2026-10-16.md`): 411/417 validation and 411/416 test images share filename capture prefixes with training views.
- **Risk Level:** **High**

### Q5. Why Combine Vision, IoT Sensors, RFR, and an Enterprise Web Platform? (Scope Defence)
- **Question:** *"Why combine a 4-camera kiosk, DHT22 sensor, YOLO detection, RFR regression, thermal QR printing, and an inventory/QC web dashboard, and how did you keep the scope manageable?"*
- **Examiner Perspective:** Internal Examiner / External Examiner
- **Why It Matters:** Addresses Concern #1 (system cohesion and scope control).
- **What the Examiner Is Testing:** Functional integration vs. scope creep.
- **What a Strong Answer Must Prove:** **Cameras + YOLO** grade cultivar/ripeness, **DHT22 + RFR** estimate shelf life, and **PostgreSQL + Web App + QR** drive **FEFO/FIFO** and **Admin QC**—bounded to one manual-loading station, 3 cultivars, no gas sensors/conveyors.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Objectives 1–4 & Limitations 1–5 (pp. 5–10); Figs. 94 & 98 (pp. 146, 170).
- **Risk Level:** **Medium**

### Q6. Cultivar Ground Truth (Lakatan, Latundan, Cardaba — Not Saba) & Semi-Ripe Confusion
- **Question:** *"How did you label Lakatan, Latundan, and Cardaba, and why did `lakatan_semi_ripe` drop to 73.84% recall and `cardaba_semi_ripe` to 78.22% precision?"*
- **Examiner Perspective:** Methodology Examiner
- **Why It Matters:** Addresses Concerns #4 and #6; ensures no team member says "Saba" when the thesis trains **Cardaba** (**CONFIRMED BY THESIS**, p. 2, Table 13, p. 59).
- **What the Examiner Is Testing:** Labeling rigor and class-specific error analysis (Fig. 16).
- **What a Strong Answer Must Prove:** Labels followed DA **PNS/BAFPS 8:2004** charts (p. 54). **Semi-Ripe** is a gradual transition (green-to-yellow Lakatan tips; thick angular Cardaba peel), causing adjacent-stage confusion in Fig. 16 (`lakatan_semi_ripe` diagonal **0.74**).
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Ch. III (p. 54), Table 13 (p. 59), Fig. 15 (p. 60), Fig. 16 (p. 61).
- **Risk Level:** **Medium**

### Q7. Multi-Camera Consensus Fusion and Finger Counting Under Occlusion
- **Question:** *"When four cameras scan a bunch at once, how do you resolve conflicting cultivar or ripeness predictions, and how do you count fingers without multiplying the count by four?"*
- **Examiner Perspective:** Technical Subject Specialist
- **Why It Matters:** Explains how per-camera YOLO outputs become one unified batch record.
- **What the Examiner Is Testing:** Multi-camera fusion and geometric deduplication.
- **What a Strong Answer Must Prove:** Confidence-weighted voting across 4 views yields one cultivar/ripeness consensus (with Top priority and conflict flags). Finger counts are **never summed across views**; IoU/containment filtering, cluster suppression, and 180° Top rotation select the **maximum single-view visible count**.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Ch. III Pipeline (p. 55) & Tech Stack (p. 171). **INFERRED** (`classification.py`, `fusion_engine.py`): Max-view visible finger counting, Top-view priority, and geometric suppression rules.
- **Risk Level:** **High**

### Q8. Why YOLOv26s and Random Forest Regression Over Alternatives?
- **Question:** *"Why choose YOLOv26s and Random Forest Regression instead of a standard CNN classifier or a linear/neural regressor?"*
- **Examiner Perspective:** Technical Subject Specialist
- **Why It Matters:** Addresses Concern #3 (algorithm selection justification).
- **What the Examiner Is Testing:** Fit between algorithms, edge hardware, and data types.
- **What a Strong Answer Must Prove:** CNNs cannot count fingers (`FINGER_COUNT`); **YOLOv26s** (9.96M params, NMS-free) detects 12 classes + boxes in **27.56 ms**. **RFR** (`300 trees, max_depth=20`) models non-linear categorical + continuous interactions (**$R^2 = 0.9552$, MAE = 0.7205d**).
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Ch. II RRL citing Xu et al. (2026), Lin et al. (2026), Sapkota & Karkee (2025, 2026) (pp. 16–18); Ch. III YOLOv26s (p. 57) and RFR (p. 63).
- **Risk Level:** **Medium**

### Q9. Why Exclude Ethylene / Volatile Gas Sensors (MQ-Series / E-Nose)?
- **Question:** *"Since ethylene gas drives banana ripening, why use only a DHT22 temperature/humidity sensor instead of an MQ-series gas sensor?"*
- **Examiner Perspective:** External Examiner
- **Why It Matters:** Common agricultural IoT question; explicitly justified in Chapter I.
- **What the Examiner Is Testing:** Hardware suitability for open-air warehouse environments.
- **What a Strong Answer Must Prove:** Gas sensors require sealed chambers and drift in open-air warehouses; DHT22 temperature, humidity, and VPD reliably measure open-air thermal/moisture stress.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Ch. I Rationale (pp. 4–5), Limitation 2 (p. 9), Ch. II RRL (pp. 30–31).
- **Risk Level:** **Low**

### Q10. Manuscript Contradiction: "Active Internet Required" vs. "Local LAN Non-Cloud PostgreSQL"
- **Question:** *"Pages 3 and 8 say 'An active internet connection is required... The system does not support offline operation,' while Table 42 on page 173 says 'Internet Connection: Optional' and PostgreSQL is local on the Mini PC. Which is it?"*
- **Examiner Perspective:** Internal Examiner / Sceptical but Fair Examiner
- **Why It Matters:** Resolves a direct wording contradiction inside the manuscript.
- **What the Examiner Is Testing:** Grasp of the actual network topology.
- **What a Strong Answer Must Prove:** YOLOv26s, RFR, FastAPI, and PostgreSQL 17 run **locally on the Ryzen Mini PC** (no cloud). "Online connection" in Ch. I means the **local Wi-Fi/LAN** between browser clients and the Mini PC.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Scope 4.2.1 (p. 8) & Definition of Terms (p. 14) vs. Figs. 96–97 (pp. 168–169) & Table 42 (p. 173).
- **Risk Level:** **Medium**

### Q11. End-to-End Hardware-to-Database Data Flow and Human-in-the-Loop QC
- **Question:** *"Trace the exact data flow from tapping 'Scan Now' on the kiosk to PostgreSQL storage, and explain how human Quality Control overrides work."*
- **Examiner Perspective:** Technical Subject Specialist
- **Why It Matters:** Proves full-stack technical ownership (Concerns #8, #11).
- **What the Examiner Is Testing:** End-to-end integration across hardware, FastAPI, ML models, and PostgreSQL tables.
- **What a Strong Answer Must Prove:** Operator PIN (`OPERATOR_PROFILE`, Table 19) + `DELIVERY_INTAKE` (`TREATMENT`: Natural/Ethephon, Table 25) $\to$ FastAPI triggers 4 cameras (`C100 4K EMEET` + LED) + Arduino `DHT22` (`SENSOR_READING`, Table 23) $\to$ Stage 1 pre-detector gate (**INFERRED**, `banana_detector.py`) $\to$ YOLOv26s per-view detection (`SCAN_DETECTION`, Table 29) + fusion $\to$ VPD + 6-feature RFR (`SCAN_CLASSIFICATION`, Table 27) $\to$ Original AI locked in `SCAN_ORIGINAL_AI_RESULT` (Table 30), while flags (`SCAN.FLAGGED`, Table 26) and Admin QC overrides log revisions in `SCAN_EVENT` (Table 33).
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Ch. III Pipeline (p. 55), Workflows Figs. 21–24 (pp. 74–78), Tables 16–39 (pp. 148–167), Table 43 (pp. 174–177).
- **Risk Level:** **Medium**

### Q12. Acceptance Testing ($n=5$ Pilot) and SUS Negative-Item Coding Corrections
- **Question:** *"Your usability evaluation used 5 respondents from one enterprise with a 94.00 mean SUS score. Is $n=5$ sufficient, and were any survey responses adjusted?"*
- **Examiner Perspective:** Methodology Examiner / Sceptical but Fair Examiner
- **Why It Matters:** Tests transparency regarding pilot scope and the SUS correction record.
- **What the Examiner Is Testing:** Statistical honesty and research integrity.
- **What a Strong Answer Must Prove:** Limitation 5 (p. 10) defines a **3–5 user pilot** ($n=5$: 2 Admins, 3 Operators at one wholesale enterprise). Odd items averaged **4.60–4.80/5.00** unmodified; even items (2, 4, 6, 8, 10) used documented once-only coding corrections ($5 \to 1, 4 \to 2$), yielding mean SUS **94.00 (SD = 5.76)**.
- **Thesis Evidence to Use:** **CONFIRMED BY THESIS**: Limitation 5 (p. 10), Ch. III (p. 67), `docs/Acceptance_Testing.md` (Tables 46–47), and `docs/SUS_Response_Correction_Record.md`.
- **Risk Level:** **High**

---

## SECTION 3: THE 5 MOST DANGEROUS QUESTIONS

### 1. **[Overlaps with Q2]** — RFR Feature Importance (82% Ripeness vs. <5% Sensor Weight)
- **Vulnerability Exposed:** Panelists may argue RFR is a ripeness/treatment lookup table ($95\%$ cumulative MDI) and the DHT22 sensor is unnecessary.
- **Safest Answer Strategy:** Agree with Figure 19; explain that ripeness sets the **macro bracket** (Unripe 7–10d vs. Overripe 1–2d), dominating global tree splits, while temperature, humidity, and VPD refine predictions **within** each stage.
- **What to Concede:** Open-air collection (Limitation 4, p. 10) had narrow thermal variance, lowering environmental MDI; P10–P90 interval coverage (**46.8%**, Fig. 18c) needs calibration.
- **What to Hold Firm On:** Figure 19 (p. 65) states low MDI does not mean zero physical effect; the 6-feature RFR achieved **MAE = 0.7205d** and **$R^2 = 0.9552$** on 814 test rows.
- **What Not to Say:** Never claim temperature/humidity is the #1 statistical predictor in your RFR or claim cold-storage testing.

### 2. **[Overlaps with Q3]** — No End-to-End Live Longitudinal Decay Validation on the Final Kiosk
- **Vulnerability Exposed:** YOLOv26s and RFR were evaluated on separate datasets (p. 54), and the station can use rule-based fallbacks or cached sensor values if hardware/models fail (**INFERRED**, `spoilage.py`, `scan_service.py`).
- **Safest Answer Strategy:** Defend **modular two-stage validation**: Stage 1 (YOLOv26s) is validated on 12-class recognition (**87.12% precision, 89.41% recall**), and Stage 2 (RFR) is validated on 814 longitudinal decay records (**MAE = 0.7205d**). Automating feature extraction via YOLO + DHT22 preserves the RFR's validated tabular mapping.
- **What to Concede:** A live scan is a point-in-time snapshot that cannot track downstream storage changes; upstream YOLO errors propagate into RFR unless corrected by Admin QC; end-to-end longitudinal station trials remain future work.
- **What to Hold Firm On:** RFR was trained on real 14-day longitudinal observations to support **FEFO/FIFO stock prioritization** with human-in-the-loop QC.
- **What Not to Say:** Never claim you waited 14 days watching demo scans rot on the finished kiosk, or present fallback rules as RFR outputs.

### 3. **[Overlaps with Q4]** — Multi-View / Augmentation Split Overlap (Data Leakage Risk)
- **Vulnerability Exposed:** Partitioning 10,845 augmented multi-angle images 80/10/10 without physical-bunch isolation allows different angles/days of the same hand to appear in both train and test sets (**INFERRED**, `docs/yolo-dataset-audit-2026-10-16.md`).
- **Safest Answer Strategy:** Describe the 4,171 raw captures, 37,316 annotations, and 80/10/10 class-stratified split across all 12 classes.
- **What to Concede:** Splitting was stratified by class at the image level rather than isolated by physical bunch ID before augmentation, which can inflate test mAP@50 (**94.11%**) relative to unseen bunches in new lighting.
- **What to Hold Firm On:** All 4,171 images and 37,316 boxes were manually gathered and labeled locally under DA **PNS/BAFPS 8:2004** with multi-camera consensus and QC safeguards.
- **What Not to Say:** Never claim the 416 test images are 416 independent bunches or claim 100% accuracy on unseen fruit.

### 4. **[Overlaps with Q1]** — Missing Color-Histogram Baseline Table in Chapter III
- **Vulnerability Exposed:** Objective 5 (p. 6) and Chapter III (p. 53) mention benchmarking YOLOv26s against a baseline color-histogram classifier, but Chapter III omits that comparison table.
- **Safest Answer Strategy:** Present the full Chapter III metrics (**87.12% precision, 89.41% recall, 88.25% F1, 94.11% mAP@50**, Table 13, Fig. 16), all surpassing Scope 5.2.1's $80\%$ requirement.
- **What to Concede:** Color-histogram thresholding was the conceptual baseline motivating YOLO, and a side-by-side color-histogram table was omitted from Chapter III.
- **What to Hold Firm On:** All target metrics in Scope 5.2.1 ($\ge 80\%$ precision and recall) were achieved and documented.
- **What Not to Say:** Never fabricate color-histogram accuracy numbers during Q&A.

### 5. **[Overlaps with Q12]** — SUS Pilot Sample ($n=5$) and Negative-Item Coding Corrections
- **Vulnerability Exposed:** Raw Google Forms responses had 4s and 5s on negatively worded even items (2, 4, 6, 8, 10) before researcher-documented coding inversion ($5 \to 1, 4 \to 2$) produced the **94.00** SUS score.
- **Safest Answer Strategy:** Explain that the pilot followed Limitation 5 ($n=5$ evaluators: 2 Admins, 3 Operators at one wholesale enterprise) and transparently reference the documented coding correction for positive-acquiescence on even items.
- **What to Concede:** $n=5$ at one enterprise is a pilot sample, and the **94.00** score relies on the documented even-item coding correction rather than unmodified raw exports.
- **What to Hold Firm On:** Unmodified odd-item ratings (**4.60–4.80/5.00**) and written evaluator comments were consistently positive.
- **What Not to Say:** Never claim industry-wide statistical generalization from 5 respondents, and never hide the coding correction if asked about the raw workbook.

---

## SECTION 4: TOP 5 SPOKEN ANSWER SCAFFOLDS

### Scaffold 1 — Defending RFR Shelf-Life Validation Without Waiting for Live Demo Bananas to Rot
- **Question Reference:** **Q3**
- **Direct Answer:** "Panel, we did not need to wait ten days during our final system demo to validate the Random Forest Regressor because the RFR was trained and tested on empirical longitudinal decay data gathered over a 14-day observation period."
- **Evidence From Thesis:** "As documented in Chapter III on pages 54 and 63, we tracked Lakatan, Latundan, and Cardaba batches across 14 days from intake until terminal spoilage while recording concurrent DHT22 temperature and humidity readings. That produced 3,964 structured records—3,150 for training and 814 for testing—using six features: encoded cultivar, ripeness stage, temperature, humidity, Vapor Pressure Deficit, and ripening treatment. On the 814 held-out test samples, our RFR achieved a Mean Absolute Error of 0.7205 days, an RMSE of 0.9822 days, and an $R^2$ of 0.9552. Because the RFR takes those six tabular values rather than raw pixels, YOLOv26s and the DHT22 sensor simply automate input collection during a live scan."
- **Limitation or Qualification:** "We openly acknowledge that a kiosk scan is a point-in-time ambient snapshot—it cannot predict if a buyer later moves the fruit into cold storage, and its P10-to-P90 interval coverage of 46.8% still requires calibration."
- **Connection to Research Contribution:** "Operationally, this gives warehouse managers an objective baseline for First-Expired, First-Out stock prioritization alongside Admin Quality Control overrides."
- **Final Sentence to Say Aloud:** *"Our 14-day longitudinal dataset validates the regression math offline, while our live kiosk automates feature extraction to guide daily warehouse prioritization."*

### Scaffold 2 — Defending the DHT22 Sensor When Ripeness Has 82% Feature Importance
- **Question Reference:** **Q2**
- **Direct Answer:** "That observation matches Figure 19 on page 65 of our thesis: encoded ripeness stage accounts for roughly 82% of Mean Decrease in Impurity, and together with treatment and cultivar reaches about 95%, while VPD, temperature, and humidity account for the remaining 5%. However, that does not mean the DHT22 sensor is unnecessary."
- **Evidence From Thesis:** "In tree-based regression across all four stages, physiological ripeness sets the macro shelf-life bracket—for instance, an unripe Cardaba lasts around 7 to 10 days, whereas an overripe banana lasts 1 to 2 days regardless of room temperature. That large gap naturally dominates global impurity splits. Within any single ripeness bracket, however, ambient temperature, relative humidity, and Vapor Pressure Deficit provide the fine-grained adjustment that shifts remaining shelf life."
- **Limitation or Qualification:** "As noted in Limitation 4 on page 10 and page 65, because our 14-day training data was collected in open-air ambient conditions rather than heated or refrigerated chambers, the temperature and humidity range was narrower, which reduces its apparent split importance in the forest."
- **Connection to Research Contribution:** "Capturing live DHT22 telemetry at every scan ensures the system accounts for ambient heat and moisture stress in Cebu's open-air warehouses."
- **Final Sentence to Say Aloud:** *"Visual ripeness tells BananaVision which shelf-life bracket the fruit starts in, while the DHT22 sensor and VPD refine how fast it moves through that bracket."*

### Scaffold 3 — Defending Cultivar & Ripeness Detection and Intermediate Stage Errors
- **Question Reference:** **Q6**
- **Direct Answer:** "We established ground-truth ripeness labels for our 4,171 original images and 37,316 bounding-box annotations using the Department of Agriculture's PNS/BAFPS 8:2004 visual color charts across our three local cultivars—Lakatan, Latundan, and Cardaba."
- **Evidence From Thesis:** "As shown in Table 13 on page 59 and the confusion matrix in Figure 16 on page 61, our YOLOv26s model achieved an overall precision of 87.12%, recall of 89.41%, F1-score of 88.25%, and mAP@50 of 94.11%. Distinct stages like `latundan_unripe` reached 98.55% mAP@50, whereas `lakatan_semi_ripe` recorded our lowest recall at 73.84% and `cardaba_semi_ripe` recorded 78.22% precision."
- **Limitation or Qualification:** "This drop happens because ripening is a continuous biological gradient, not four discrete steps. While unripe green and overripe brown-spotted peels are visually distinct, semi-ripe bananas sit on the borderline where green tips fade into yellow, and Cardaba has a thick, angled peel that changes color less uniformly."
- **Connection to Research Contribution:** "To prevent borderline semi-ripe misclassifications from corrupting inventory, we paired YOLOv26s with four-camera confidence-weighted fusion, operator flagging on the kiosk, and an Admin Quality Control override module."
- **Final Sentence to Say Aloud:** *"Where biological transition stages blur visual boundaries, BananaVision pairs multi-angle consensus with human-in-the-loop quality control so warehouse records stay accurate."*

### Scaffold 4 — Explaining Multi-Camera Fusion and Finger Counting Under Occlusion
- **Question Reference:** **Q7**
- **Direct Answer:** "When our four cameras—Top, Left, Right, and Rear—capture a banana hand simultaneously, our backend does not simply add the four detections together, because that would quadruple the finger count and allow conflicting cultivar labels."
- **Evidence From Thesis:** "Instead, as described in Chapter III on page 55 and implemented in our classification and fusion services, each camera image is processed by YOLOv26s at 27.56 milliseconds per image. For cultivar and ripeness, the fusion engine applies confidence-weighted voting across all four views so the bunch reaches a single biological consensus. If cross-camera agreement falls below our conflict threshold, the scan is flagged for review."
- **Limitation or Qualification:** "For finger counting, since the four 2D webcams do not share a 3D depth map, we apply IoU and containment filtering, suppress cluster boxes, run a 180-degree rotation fallback on the top view, and take the maximum visible finger count from the clearest view. We state clearly that this estimates visible fingers, as deeply occluded back-row fingers cannot be seen by 2D cameras alone."
- **Connection to Research Contribution:** "This gives enterprise operators a fast, repeatable visible-finger estimate and unified batch grade in a single scan without expensive industrial 3D scanners."
- **Final Sentence to Say Aloud:** *"Multi-view weighted voting enforces biological consensus for the bunch, while maximum-view geometric filtering prevents cross-camera double counting."*

### Scaffold 5 — Justifying System Scope and Explaining the End-to-End Architecture
- **Question Reference:** **Q5** (with **Q11** data flow)
- **Direct Answer:** "Our components belong together because post-harvest grading in a wholesale warehouse is a single continuous workflow: identifying what arrived, estimating how long it will last in current storage, labeling the batch, and tracking it in inventory."
- **Evidence From Thesis:** "As shown in our Block Diagram on page 146 and IoT Architecture on page 170, when an operator logs into the touchscreen kiosk with a 4-digit PIN and triggers a scan, the Ryzen Mini PC captures four LED-lit camera views and reads temperature and humidity from the Arduino-connected DHT22 sensor. YOLOv26s classifies cultivar and ripeness; those outputs join temperature, humidity, VPD, and delivery treatment in the RFR model to estimate remaining days before spoilage. Everything is saved locally in our PostgreSQL database, printed on a Grozziie thermal label, and broadcast via WebSockets to the Admin and Operator dashboards."
- **Limitation or Qualification:** "To keep this scope manageable for an undergraduate capstone, we bounded the system in Chapter I pages 9 to 10: three local cultivars, a stationary manual-loading chamber rather than a conveyor belt, and no volatile gas sensors."
- **Connection to Research Contribution:** "By keeping inference and database storage on the local Mini PC over the facility's Wi-Fi network, BananaVision delivers an affordable, end-to-end quality control station tailored to Cebu's banana enterprises."
- **Final Sentence to Say Aloud:** *"Every hardware sensor and software module in BananaVision serves one disciplined goal: turning a raw banana batch into a graded, shelf-life-prioritized inventory record in seconds."*

---

## SECTION 5: ONE-PAGE DEFENCE PREPARATION SHEET

- **Thesis in One Sentence:** BananaVision is an edge-deployed IoT and computer vision kiosk integrating a 4-camera YOLOv26s detector, an Arduino DHT22 sensor, a 6-feature Random Forest Regressor, and a local PostgreSQL web platform to automate ripeness grading and shelf-life estimation for Lakatan, Latundan, and Cardaba bananas (**CONFIRMED BY THESIS**, Abstract, p. ii).
- **Contribution in One Sentence:** The study delivers a localized post-harvest grading and FEFO decision-support station calibrated for three Philippine banana cultivars under DA **PNS/BAFPS 8:2004** standards, pairing multi-angle optical consensus with VPD-informed spoilage regression and auditable human-in-the-loop quality control (**CONFIRMED BY THESIS**, pp. 4–5, 53–55).
- **Method Defence in One Sentence:** We trained YOLOv26s on 4,171 multi-angle images (37,316 annotations, augmented to 10,845; **87.12% precision, 89.41% recall, 94.11% mAP@50**), trained RFR on 3,964 14-day longitudinal records (**MAE = 0.7205d, RMSE = 0.9822d, $R^2 = 0.9552$**), and evaluated pilot usability with five wholesale enterprise users (**94.00 mean SUS, SD = 5.76**) (**CONFIRMED BY THESIS**, pp. 54–65; `docs/Acceptance_Testing.md`).
- **Main Limitation in One Sentence:** BananaVision is a single-station, manually loaded prototype limited to Lakatan, Latundan, and Cardaba under open-air ambient conditions, where RFR outputs serve as point-in-time FEFO estimates (with 82% MDI weight on ripeness and 46.8% P10–P90 interval coverage) rather than guarantees across changing downstream storage (**CONFIRMED BY THESIS**, pp. 9–10, 63–65).

### Three Questions to Practise First
1. **Q3 (Scaffold 1):** How RFR shelf-life ground truth was collected over 14 days (3,964 samples; MAE = 0.7205d) and why modular validation defends live scans without waiting 10 days during the defence.
2. **Q2 (Scaffold 2):** Why DHT22 and VPD remain valid within-stage modifiers even though encoded ripeness stage accounts for $\approx 82\%$ of RFR MDI importance in Figure 19.
3. **Q6 (Scaffold 3):** Why our three cultivars are **Lakatan, Latundan, and Cardaba** (not Saba), how DA **PNS/BAFPS 8:2004** guided labeling, and why `lakatan_semi_ripe` (73.84% recall) and `cardaba_semi_ripe` (78.22% precision) had the highest confusion.

### Three Concepts We Must Define Clearly
1. **Vapor Pressure Deficit (VPD in kPa):** Difference between saturation and actual air vapor pressure from temperature and relative humidity ($0.61078 \times \exp(\frac{17.27T}{T+237.3}) \times (1 - \frac{RH}{100})$), measuring air drying pull on the peel (**CONFIRMED BY THESIS**, p. 15).
2. **Two-Stage Modular Pipeline & Multi-Camera Consensus:** Stage 1 (`YOLOv26s`) determines cultivar, ripeness, and max-view visible finger count across 4 views via confidence-weighted voting; Stage 2 (`RFR`) combines encoded cultivar and ripeness with `temperature`, `humidity`, `VPD`, and `treatment` (`Natural` vs. `Ethephon`) to estimate remaining days (**CONFIRMED BY THESIS**, p. 55).
3. **Mean Decrease in Impurity (MDI) vs. Physical Causality:** MDI measures variance reduction across tree splits in a specific dataset; ripeness dominates ($\approx 82\%$) because it separates 10-day unripe fruit from 1-day overripe fruit, while microclimate variables refine predictions within each stage (**CONFIRMED BY THESIS**, p. 65).

### Three Claims We Must Avoid Overstating
1. **Do NOT claim RFR predicts exact rotting hours regardless of future storage:** Frame it as an **ambient baseline estimate for FEFO/FIFO prioritization**.
2. **Do NOT claim 3D total finger counting or 100% unseen-bunch generalization:** State that finger counting uses **maximum single-view visible count**, and acknowledge image-level multi-view split overlap.
3. **Do NOT overstate the $n=5$ SUS pilot or claim a tabulated color-histogram benchmark:** State that the **94.00 SUS score** is from a 5-user pilot at one enterprise (with documented negative-item coding corrections) and that the color-histogram table in Objective 5 was omitted from Chapter III.

### Three Wider-Field Knowledge Areas to Verify Externally
1. **PNS/BAFPS 8:2004 (Philippine National Standard for Fresh Bananas)** **[VERIFY EXTERNALLY]**: Review official DA color index charts and defect tolerances for Lakatan, Latundan, and Cardaba.
2. **Climacteric Banana Physiology, VPD Transpiration, and Ethephon Ripening** **[VERIFY EXTERNALLY]**: Review how exogenous Ethephon accelerates respiration and why higher VPD increases peel moisture loss.
3. **Ultralytics YOLOv26 Architecture & Checkpoint Variants** **[VERIFY EXTERNALLY]**: Review `MuSGD` and NMS-free inference (Sapkota & Karkee, 2025, 2026) and be ready to explain any difference between the thesis's `YOLOv26s` training report (9.96M parameters, $1024 \times 1024$) and station weight files (`banana_yolo26m.pt` / `banana_yolov26n.pt`).
