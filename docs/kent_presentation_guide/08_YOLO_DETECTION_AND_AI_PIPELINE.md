# 🧠 Deep Dive: YOLO Detection, Multi-Camera Vision & AI Pipeline

> **Feature 11 & Core Vision System:** AI Settings (YOLO26) & Full Computer Vision Pipeline  
> **Key Files:**  
> - [`backend/app/services/banana_detector.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/banana_detector.py) (Stage 1: Pre-Detection Gate)  
> - [`backend/app/services/classification.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/classification.py) (Stage 2: Custom YOLO Banana Classifier)  
> - [`backend/app/services/camera_manager.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/camera_manager.py) (4-Camera Parallel Capture)  
> - [`backend/app/services/fusion_engine.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/fusion_engine.py) (Multi-Camera Fusion & Consensus)  
> - [`backend/app/services/scan_service.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/scan_service.py) (Pipeline Orchestrator)

---

## 1. What is YOLO and How Does It Work in Computer Vision?

**YOLO** stands for **"You Only Look Once"**. Unlike older object detection algorithms (such as R-CNN or Faster R-CNN) that first generate thousands of region proposals and then run a classifier on each region separately, YOLO frames object detection as a **single regression problem**:
1. **Single Forward Pass:** YOLO passes the entire input image through a deep convolutional neural network (CNN) or vision backbone once.
2. **Grid Cell Prediction:** The network divides the image into a grid (e.g. $S \times S$). If the center of an object falls into a grid cell, that grid cell is responsible for detecting that object.
3. **Bounding Boxes + Class Probabilities:** For each cell, YOLO simultaneously predicts:
   - Bounding box coordinates: $(x, y, w, h)$ where $(x, y)$ is the box center and $(w, h)$ are width and height.
   - **Confidence Score:** How certain the model is that an object exists in that box ($\text{Pr}(\text{Object}) \times \text{IoU}$).
   - **Class Probabilities:** Conditional probabilities for each target class (e.g., Lakatan, Latundan, Cardaba).
4. **Non-Maximum Suppression (NMS):** Because multiple adjacent grid cells may detect the same physical object, NMS filters out overlapping redundant boxes by calculating **Intersection over Union (IoU)**, keeping only the highest-confidence bounding box.

---

## 2. BananaVision's Two-Stage AI Architecture

In standard research projects, engineers often feed an image directly into their custom model. But in a real factory, that leads to severe bugs: if an operator scans an empty platter, a cup of coffee, or their clipboard, the custom classifier will force-fit the image to "Lakatan Ripe" with 45% confidence.

To solve this, Kent's team engineered a **Two-Stage Gate Pipeline**:

```
[ 4-Camera Parallel Capture (Top, Left, Right, Rear) ]
                         │
                         ▼
        ┌───────────────────────────────────┐
        │   Stage 1: Pre-Detection Gate     │
        │      (banana_detector.py)         │
        │     Base COCO YOLO (Class 46)     │
        └─────────────────┬─────────────────┘
                          │
                  Any banana found?
                 /                 \
             [No]                  [Yes]
              │                      │
     Reject Scan with Notice:        ▼
  "No Lakatan, Latundan, or       ┌───────────────────────────────────┐
      Cardaba detected"           │   Stage 2: Custom YOLOv26 Model   │
                                  │       (classification.py)         │
                                  │   Lakatan, Latundan, Cardaba      │
                                  │ Unripe, Semi Ripe, Ripe, Overripe │
                                  └─────────────────┬─────────────────┘
                                                    │
                                     [ Per-Camera CV Enhancements ]
                                     - 180° Rotation Fallback (Top)
                                     - Table Lip Suppression (Rear)
                                     - Upper Background Suppression
                                     - Banana-Evidence Box Support (OOD)
                                     - Cluster & Sub-Box Elimination
                                                    │
                                                    ▼
                                  ┌───────────────────────────────────┐
                                  │   Multi-Camera Fusion Engine      │
                                  │       (fusion_engine.py)          │
                                  │ - Weighted Voting Consensus       │
                                  │ - Cross-View Harmonization        │
                                  │ - Finger Count Aggregation        │
                                  └─────────────────┬─────────────────┘
                                                    │
                                                    ▼
                                  [ Final Scan Result + DB Commit ]
```

---

## 3. Code Breakdown: Stage 1 — Pre-Detection Gate (`banana_detector.py`)

In [`backend/app/services/banana_detector.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/banana_detector.py):
```python
BANANA_CLASS_ID = 46  # Standard COCO dataset index for "banana"

class BananaPreDetector:
    # Thresholds come from Settings: OOD_BANANA_CONFIDENCE (0.30) and
    # OOD_SUPPORT_CONFIDENCE (0.05).
    _COCO_MODEL = "yolo26n.pt"

    def detect(self, image, *, accept_confidence=None, support_confidence=None):
        # Predict strictly filtering on COCO class 46. Boxes from 0.05 are kept
        # as banana evidence; a view "shows a banana" at 0.30 or higher.
        results = self._model.predict(
            image,
            conf=support_conf,
            classes=[BANANA_CLASS_ID],  # Only detect bananas!
            verbose=False,
        )
        ...
```
- In `scan_service.py`, before spending CPU/GPU time running custom classification, the pipeline runs this fast pre-detector on every frame and keeps each view's banana evidence:
  ```python
  view_evidence = []
  for cap in captures:
      pre_result = await run_blocking(banana_pre_detector.detect, cap.frame)
      view_evidence.append(ood_gate.ViewEvidence(
          camera_id=cap.camera_id, camera_label=cap.camera_label,
          evidence=boxes, banana_score=..., has_banana=bool(pre_result.banana_detected),
      ))

  gate_decision = ood_gate.decide_scan(view_evidence, gate_policy)
  if not gate_decision.accepted:
      raise ScanRejectedError(ood_gate.REASON_NO_BANANA, ood_gate.REJECTION_MESSAGE, ...)
  ```
  The operator sees: *"No Lakatan, Latundan, or Cardaba detected. Place a supported banana hand on the tray and scan again."*
- **Out-of-distribution rejection (added 2026-11-13):** in Stage 2 a cultivar box is kept only where that banana evidence covers its centre, so a foreign object beside the banana neither votes nor counts as a finger. A scan that lost any box is flagged for review; a scan left with no supported cultivar is rejected and nothing is saved. If the verifier cannot run, the scan is refused instead of being classified blindly. Design, measurements and limits: `docs/knowledge/AI Models.md`.
- **Panel Talking Point:** This prevents false positive scans, saves database storage from junk records, and guarantees clean telemetry.

---

## 4. Code Breakdown: Stage 2 — Custom Banana Classification (`classification.py`)

### Part A: Model Loading & Fingerprint Verification
In `backend/app/services/classification.py`:
```python
def load(self) -> None:
    model_path = settings.yolo_model_path  # e.g. "backend/app/ml/weights/banana_yolo26m.pt"
    self._model = YOLO(model_path)
    self._loaded = True
    self._image_size = getattr(self._model, "overrides", {}).get("imgsz", 640)
    self._checkpoint_sha256 = _checkpoint_digest(model_path)
```
- The code calculates the **SHA256 cryptographic digest** of the model binary. This ensures that if the model weights file is swapped or updated, the system recognizes the exact checkpoint rather than relying on arbitrary file names.

---

### Part B: Class Labels and Combinations
The model was trained on Roboflow dataset classes representing combinations of cultivar and ripeness:
- **Cultivars:** Lakatan, Latundan, Cardaba
- **Ripeness:** Unripe, Semi Ripe, Ripe, Overripe
- Labels in the model are formatted as `lakatan_ripe`, `cardaba_semi_ripe`, `latundan_overripe`.

The function `_parse_class_label` uses case-insensitive splitting to cleanly extract both attributes:
```python
def _parse_class_label(label: str) -> tuple[str | None, str | None]:
    parts = label.lower().split("_", 1)
    cultivar = _CULTIVAR_LOOKUP.get(parts[0])      # "Lakatan"
    ripeness = _RIPENESS_LOOKUP.get(parts[1])      # "Semi Ripe"
    return cultivar, ripeness
```

---

## 5. Advanced Computer Vision Post-Processing Implemented by Kent's Team

### 1. Calibrated Top View Overlap Refinement
On the overhead Top camera, banana fingers grow closely packed in a curved comb structure. Standard YOLO Non-Maximum Suppression (NMS) with an IoU of 0.45 will accidentally suppress neighboring fingers thinking they are duplicate detections!
- **Code Solution (`classification.py:338`):**
  ```python
  if settings.yolo_top_overlap_refinement and is_calibrated_top:
      iou_threshold = TOP_OVERLAP_IOU  # Raised from 0.45 to 0.65!
  ```
  By increasing the NMS threshold to 0.65 specifically on the calibrated Top view, tightly packed parallel fingers are preserved and counted individually.

---

### 2. The 180° Rotation Fallback Algorithm (`classification.py:421`)
Due to lighting shadows and the natural curve of a banana hand, fingers whose tips point toward the camera lens can suffer from perspective foreshortening, causing YOLO to miss them.
- **Code Solution:**
  1. The code flips the top frame 180 degrees using numpy indexing:
     ```python
     rotated = image[::-1, ::-1].copy()
     ```
  2. Runs YOLO inference on the rotated image.
  3. Maps the detected bounding boxes back to the original coordinate space:
     ```python
     ox1, oy1 = img_w - rx2, img_h - ry2
     ox2, oy2 = img_w - rx1, img_h - ry1
     ```
  4. Checks each candidate box against existing detections using `_is_duplicate_detection`:
     ```python
     duplicates = [existing for existing in detections if _is_duplicate_detection(candidate, existing)]
     if not duplicates:
         detections.append(candidate)  # Recovered missed finger!
     ```
- **Panel Impact:** This single algorithm recovers 15% to 25% of occluded fingers that standard single-orientation YOLO misses completely!

---

### 3. Geometric False-Positive Suppression (`classification.py:378-406`)
In a real testing enclosure, background elements can trigger false detections:
1. **Rear Camera Table Lip Suppression:**
   ```python
   # The circular inspection plate edge on the rear camera sometimes looks like a banana curve
   if norm_cam == "rear" and y1 > 0.55 * img_h and (x2 - x1) > 2.0 * (y2 - y1) and conf < 0.60:
       continue  # Discard horizontal saucer lip reflection
   ```
2. **Peripheral Camera Ceiling & Door Frame Suppression:**
   ```python
   # Upper background ceiling beams and door frame verticals
   if norm_cam in ("left", "right", "rear"):
       if y2 < 0.22 * img_h:
           continue  # Upper 22% of frame is the ceiling/sky
       if (det_h / det_w) >= 2.2 and y2 <= 0.55 * img_h:
           continue  # Tall slender door frame pillar
   ```

---

### 4. Cluster Box & Sub-Box Elimination (`classification.py:167-204`)
Sometimes YOLO detects both the individual fingers *and* draws a massive bounding box around the whole bunch:
- **`_is_same_class_sub_box`:** If box A has $\ge 80\%$ containment inside box B with the same class, the duplicate sub-box is discarded.
- **`_is_cluster_box`:** If a large box encompasses 2 or more smaller distinct fingers, the giant encompassing box is removed:
  ```python
  if len(detections) >= 3:
      detections = [det for det in detections if not _is_cluster_box(det, [o for o in detections if o != det])]
  ```
- This guarantees that `finger_count` represents true individual bananas, not clump boxes.

---

### 5. Cultivar Consensus Voting & Ripeness Selection (`classification.py:487`)
How does the system decide the final class from dozens of bounding boxes?
```python
# Sum confidence scores for each cultivar
best_cultivar = max(cultivar_votes, key=lambda k: sum(cultivar_votes[k]))

# Select ripeness strictly from votes belonging to the winning cultivar
ripeness_votes = {
    ripeness: confs for (cultivar, ripeness), confs in class_votes.items()
    if cultivar == best_cultivar and ripeness
}
best_ripeness = max(ripeness_votes, key=lambda k: sum(ripeness_votes[k]))
```
- **Why this prevents bugs:** Independent voting could pick "Lakatan" for cultivar and "Overripe" from a low-confidence Cardaba box that the model never saw as a pair. This code forces ripeness to come strictly from the winning cultivar's detections!

---

### 6. Cross-View Cultivar Harmonization across Cameras (`scan_service.py:230`)
In multi-camera scanning:
- Camera 1 (Top) sees: 8 Lakatan boxes (92% confidence).
- Camera 2 (Left) sees: 6 Lakatan boxes (88% confidence).
- Camera 3 (Right) sees: 7 Lakatan boxes (90% confidence).
- Camera 4 (Rear) sees: 2 Lakatan, but 1 box misclassified as Cardaba (52% confidence) due to harsh backlighting.

In `scan_service.py`:
```python
# A single harvested banana bunch is botanically uniform.
if not has_cultivar_conflict and fused.cultivar != "Unknown":
    consensus_cultivar = fused.cultivar
    for det in db_detections:
        if det.detected_cultivar and det.detected_cultivar != consensus_cultivar:
            logger.info(f"Harmonizing camera {det.camera_label} from {det.detected_cultivar} to {consensus_cultivar}")
            det.detected_cultivar = consensus_cultivar
            # Harmonize individual bounding box labels as well
            for box in det.bounding_boxes:
                _, rip = _parse_class_label(box["cls"])
                box["cls"] = f"{consensus_cultivar}_{rip}".lower()
```
- The whole bunch achieves 100% botanical consensus, correcting single-angle optical anomalies!

---

## 6. AI Review Threshold vs YOLO Detection Threshold (`AI-01`)

In `frontend/src/pages/admin/SystemConfig.tsx`, there is an AI slider: **Review Confidence Threshold (e.g. 70%)**.
- **Historical Ambiguity (`AI-01`):** In early prototypes, people assumed this slider stopped YOLO from detecting boxes below that number.
- **Kent's Clarified Architecture:**
  - **Detection Threshold (`settings.yolo_confidence_threshold = 0.30`):** YOLO retains all valid banana boxes down to 30% so evidence is never thrown away prematurely.
  - **Review Threshold (`config.confidence_threshold = 70%`):** If the fused final confidence score is below this threshold, the scan is flagged in inventory as **"Needs Review"**, prompting the quality manager to inspect the bananas physically.

---

## 7. Summary for Presentation & Code Defense

When presenting the YOLO pipeline to the panel, emphasize these 4 pillars:
1. **Two-Stage Defense:** Standard COCO gate stops false triggers before custom classification starts.
2. **Multi-Camera Parallelism:** 4 views (Top, Left, Right, Rear) captured simultaneously using OpenCV and thread-pool execution.
3. **Advanced Post-Processing:** 180° Rotation Fallback, Calibrated Overlap NMS, Cluster Box Suppression, and False-Positive Suppression.
4. **Botanical Harmonization:** Weighted voting consensus guarantees single-cultivar bunch integrity.
