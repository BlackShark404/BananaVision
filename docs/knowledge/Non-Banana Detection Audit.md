# Non-Banana Detection Audit

Status: proposal for later implementation. Nothing in this note is implemented yet.

Date: 2026-11-13

Scope: the scan pipeline from capture through persistence. This audit explains why non-banana objects can receive cultivar and ripeness labels, then proposes a layered fix. It does not cover general system health, authentication or inventory behavior.

Related notes: [[Development Decisions]], [[Resolved Bugs]], [[Testing and Validation]].

## Problem

A non-banana object placed on the inspection platter can produce a normal BananaVision result: cultivar, ripeness, confidence, finger count, spoilage estimate and sometimes an automatic printed label. The operator may see a low-confidence or flagged scan, but the record still looks like a banana prediction.

The existing geometry filters suppress specific observed artifacts (saucer lip, door frames, ceiling fixtures). That approach works only for artifacts already seen and measured. It does not give the system a general way to say "this is not a banana".

## Method

This audit is a read-only trace of the current source code. It also inspected the class names stored inside the local checkpoints `backend/app/ml/weights/banana_yolov26s.pt` and `backend/app/ml/weights/banana_yolov26sv_3.pt` with `torch.load`. It did not read station captures, the station database or the live cameras. Proposed thresholds are starting points and require calibration on station frames and an isolated negative fixture set.

## Current pipeline

1. `camera_manager.capture_all()` captures all configured views.
2. `banana_pre_detector.detect()` runs COCO YOLO on frames until one frame reports a banana.
3. `banana_classifier.predict()` runs the custom 12-class detector on every frame.
4. `fusion_engine.fuse()` combines per-camera cultivar and ripeness votes.
5. `scan_service` computes spoilage and persists the scan.

### Verified model constraint

Both local custom checkpoints expose exactly these 12 classes:

```text
cardaba_overripe, cardaba_ripe, cardaba_semi_ripe, cardaba_unripe,
lakatan_overripe, lakatan_ripe, lakatan_semi_ripe, lakatan_unripe,
latundan_overripe, latundan_ripe, latundan_semi_ripe, latundan_unripe
```

There is no `background`, `not_banana` or `unknown` class. The detector is closed-set: it always assigns the best-fitting banana class to anything that survives confidence and NMS filtering. Suppressing a false label therefore cannot be solved by tuning the model's softmax alone.

## Findings

### F1. The pre-detector gate fails open

`BananaPreDetector.detect()` returns `banana_detected=True` when the COCO model is missing (`backend/app/services/banana_detector.py:115`) and when inference raises (`backend/app/services/banana_detector.py:132`). `startup.py` loads `yolo26n.pt` at boot, but a fresh offline station without the cached weight degrades into accepting every scan. `/health` reports `banana_pre_detector_loaded: false` (`backend/app/main.py:128`), but the scan path does not check that flag.

### F2. One camera admits the whole scan

`scan_service.py:139-146` stops checking frames at the first camera that reports a banana. A single peripheral false positive admits the scan even if the authoritative Top view contains no banana.

### F3. Any complete view can vote at any confidence

`FusionEngine.fuse()` accepts a camera as a full vote when cultivar and ripeness are present and `confidence > 0` (`backend/app/services/fusion_engine.py:125-139`). There is no minimum detection count, no median confidence requirement and no spatial coherence requirement. One box at the detector cutoff is enough.

### F4. The Top anchor needs only one box at 50 percent

`top_anchor_eligible` requires `confidence >= 50.0` and `finger_count >= 1` (`backend/app/services/fusion_engine.py:152-160`). A single false box in the overhead view can therefore anchor the cultivar for the entire scan. The same anchor is used to suppress competing peripheral evidence (`backend/app/services/fusion_engine.py:196`).

### F5. Background filters are narrow geometric patches

The Rear table-lip filter (`backend/app/services/classification.py:426`) and the peripheral background filter (`backend/app/services/classification.py:437`) only reject boxes in the upper 22 percent of the frame, slender vertical pillars touching the top edge, and elongated low-confidence bottom boxes. A door jamb or platter-adjacent artifact inside the lower frame is accepted. The documented real case is a door jamb labeled `Lakatan Overripe` at 76 percent ([[Resolved Bugs]], item 10, 2026-10-19).

### F6. Harmonization rewrites the evidence

When fusion reports no cultivar conflict, `scan_service.py:239-260` rewrites every per-camera `detected_cultivar` and every bounding-box `cls` value to the consensus cultivar. A spurious box in a dissenting view is stored as the winning cultivar and ripeness. The review UI then shows a confident banana label, and the original evidence is lost. This is the mechanism that makes the system appear to "blindly label" objects.

### F7. Detection cutoff is coupled to the review threshold

`scan_service.py:104-106` sets the detector cutoff to `min(review_threshold, yolo_confidence_threshold)`. The default is 0.50, but an admin who lowers the review threshold also lowers the detector cutoff. The test suite explicitly asserts a 0.30 cutoff when review is 30 (`backend/tests/test_detection_sensitivity.py`). Lower review thresholds therefore admit weaker non-banana boxes into voting.

### F8. Flagging does not prevent persistence or output

`auto_flagged` only sets the scan flag (`backend/app/services/fusion_engine.py:246-249`). The scan is still persisted, spoilage is still predicted, and the label can still be printed. The only hard abort is `fused.cultivar == "Unknown" or fused.ripeness == "Unknown"` (`backend/app/services/scan_service.py:228`), which requires zero usable votes.

### F9. Training has no negative examples

`backend/scripts/prepare_yolo_dataset.py:138` rejects an empty label file as an explicit background-image review failure. The supplied export covers only the 12 banana classes, and the preparation script refuses empty-label images, so background frames are not part of the training copy. The detector never learned what "no banana" looks like in the station domain.

### F10. Rejected scans delete the evidence needed for retraining

The failure path calls `remove_scan_captures` (`backend/app/services/scan_service.py:425`). The frames that should become negative training data are deleted.

## Proposed fix

The design is layered. P0 stops the current failure mode without retraining. P1 improves the model so it generalizes beyond the patches. P2 removes the largest remaining source of false positives.

### P0. Evidence gate and fail-closed guard

Goal: no scan may produce a cultivar/ripeness label without sufficient, spatially coherent banana evidence in the authoritative views.

1. Make the pre-detector explicit.
   - Add `available: bool` and `reason: str | None` to `PreDetectionResult`.
   - Treat a missing model or inference exception as unavailable, not as banana present.
   - Abort the scan with an operator-facing message when the guard is unavailable. Keep a development override, but make production fail closed.
   - Keep `/health` reporting, and do not rely on it as the only signal.

2. Require corroboration across views.
   - Pass the gate when the Top view sees a COCO banana and at least one other view sees one.
   - When Top is offline or unconfigured, require at least two peripheral views.
   - Record the per-view gate result in the scan event log for diagnosis.
   - Use a minimum COCO banana area (for example 1.5 percent of the frame) and raise the COCO confidence threshold from 0.30 to a calibrated value (start at 0.45).

3. Add per-view plausibility before voting.
   - Implement one helper, for example `_view_evidence_is_plausible(detections, frame_shape)`, used by classification and fusion.
   - Starting rules, all tunable:
     - At least two detections with median confidence >= 0.60, or one detection with confidence >= 0.80 and area >= 3 percent of the frame.
     - Median box aspect ratio within a banana-finger range, and median area within a sane range.
     - Compact cluster: the union of detection boxes covers at most 60 percent of the frame, and the maximum distance between box centers is at most 50 percent of the frame diagonal. A banana hand is compact; scattered background fixtures are not.
   - A view that fails plausibility keeps its raw boxes for review but cannot vote for cultivar or ripeness and does not contribute to finger count.
   - If no view passes, abort with a specific "no banana detected" error and do not persist a scan row.

4. Decouple detection cutoff from review threshold.
   - Keep the detector cutoff at a floor such as 0.45 to 0.50.
   - Let the review threshold only control `flagged` and related UI.
   - Update the configuration contract and tests so lowering review confidence cannot lower detection sensitivity.

5. Preserve audit truth in stored detections.
   - Add `original_cls` and `harmonized` metadata to each bounding-box dictionary.
   - Never rewrite a box that failed the plausibility gate.
   - Consider keeping the original per-camera `detected_cultivar` in a new column or in detection metadata instead of overwriting it. At minimum, the bbox metadata must retain the original label.
   - Harmonize only boxes that passed the gate and belong to the winning physical bunch.

6. Retain rejected evidence.
   - Move rejected scan captures to a quarantine directory instead of deleting them.
   - Apply the existing retention policy so the quarantine cannot grow without bound.
   - Use this set for P1 negative training after human review.

Suggested new settings (names are illustrative, not fixed):

```text
YOLO_PRE_GATE_REQUIRE_TOP=true
YOLO_PRE_GATE_MIN_CONFIDENCE=0.45
YOLO_PRE_GATE_MIN_AREA_RATIO=0.015
YOLO_EVIDENCE_MIN_DETECTIONS=2
YOLO_EVIDENCE_MIN_MEDIAN_CONFIDENCE=0.60
YOLO_EVIDENCE_SINGLE_MIN_CONFIDENCE=0.80
YOLO_EVIDENCE_SINGLE_MIN_AREA_RATIO=0.03
YOLO_EVIDENCE_MAX_CLUSTER_RATIO=0.60
YOLO_REJECTED_CAPTURE_QUARANTINE=true
```

### P1. Negative data and retraining

1. Collect 500 to 2,000 station-domain negatives:
   - Empty platter, all four views, multiple lighting conditions.
   - Hands entering the frame, tools, packaging, other fruits, cups and bottles.
   - Door frames, walls, ceiling fixtures and other known artifacts.
2. Label them as background images with empty label files.
3. Change the dataset preparation policy so verified background images are allowed and recorded in the manifest, instead of always raising `PreparationError`.
4. Train with roughly 5 to 10 percent background images mixed into the training split. Keep all views and augmentations of one physical bunch in the same split, as the existing grouped policy already requires.
5. Recalibrate after training:
   - Register the new checkpoint hash and saved `imgsz` in `TOP_CALIBRATED_CHECKPOINTS`.
   - Re-run the 168-image Top-view cultivar regression.
   - Run the negative fixture suite and report the false-accept rate.

Expected effect: the detector learns objectness for the station domain and stops firing on door frames, platter hardware and background texture. This is the durable fix; P0 only rejects low-evidence false positives.

### P2. Platter ROI calibration

Add a per-camera normalized polygon or ellipse for the usable platter area. Store it with the camera slot configuration and let an admin draw it once from a live preview. Reject detections whose center or dominant area falls outside the ROI before voting. This is the strongest zero-retraining defense for peripheral camera backgrounds, but it needs a calibration UI and a configuration migration.

### P3. Optional crop verifier

If negatives alone do not reduce false accepts enough, train a small binary crop classifier (banana versus not banana) on the detector's proposals. Use station crops plus hard negatives. Reject crops below a calibrated probability before counting. This is a separate model and should be justified by measured residual error from P0 and P1.

## Verification plan

Do not use live station captures for automated tests. Build an isolated fixture set under the test tree or a disposable directory.

### Negative fixture set

At least 100 frames, all four views, containing:

- Empty platter.
- Hands and arms.
- Tools, cups, bottles, packaging.
- Other yellow or elongated fruit.
- Door frames, walls, ceiling fixtures and platter hardware.
- Mixed lighting and shadows.

### Positive regression set

- The existing 168 Top-view validation and test images.
- A small set of station-like positive fixtures for peripheral views.
- At least one green Cardaba and one green Lakatan case, because COCO banana is yellow-biased.

### Metrics

| Metric | Target |
| --- | --- |
| Negative false-accept rate (any cultivar/ripeness label) | 0 out of 100 initially; <= 1 percent long term |
| Positive cultivar accuracy on the 168-image Top set | 168 / 168 unchanged |
| Positive finger-count change | Within +/-1 per scan |
| False rejects per cultivar | Measured and reported; green Cardaba must not regress silently |
| Scan latency | No material increase from the extra gate |

### Required checks before calling implementation complete

- Targeted backend tests for classification, fusion, scan trigger, scan writes and configuration.
- New tests for: fail-closed guard, single-camera rejection, one-box rejection, harmonization metadata and rejected-capture quarantine.
- `ruff check backend/app backend/tests`.
- Frontend tests, `npm run typecheck`, `npm run build`, `npm run lint` if any UI or contract changes.
- Review the scoped diff and confirm no station data, captures or secrets were touched.

## Risks and tradeoffs

- Green and unripe fruit: COCO banana is trained mostly on yellow bananas. A strict COCO gate can reject valid unripe Cardaba. Keep COCO as corroborating evidence and calibrate the gate on the station's own images; do not make COCO the only judge.
- Single-finger scans: if the product supports scanning one detached finger, a minimum of two detections would reject it. Decide this explicitly. The one-detection-with-high-confidence rule is the fallback.
- Top camera availability: requiring Top every time blocks scans when that camera is offline. The fallback is two independent peripheral views, not a single view.
- Retraining cost: a new checkpoint changes the SHA-based Top calibration. Rotation fallback and TTA recovery must be re-verified, not assumed.
- ROI setup: one-time admin work per camera, plus storage and migration.
- Fail-closed availability: a missing COCO weight now blocks scans. Bundle the weight with the installer and surface a clear admin error so the station does not silently degrade.
- Harmonization: preserving original labels may make the UI show mixed cultivars even when the scan-level consensus is correct. The scan-level label should remain the bunch consensus; only the per-detection provenance changes.

## Files likely touched

- `backend/app/services/banana_detector.py`
- `backend/app/services/classification.py`
- `backend/app/services/fusion_engine.py`
- `backend/app/services/scan_service.py`
- `backend/app/services/capture_cleanup.py`
- `backend/app/config.py`
- `backend/app/main.py` (health and readiness contract, if enforced)
- `backend/app/schemas/` (only if the gate result or rejection reason becomes part of the API)
- `backend/scripts/prepare_yolo_dataset.py` (P1 background-image policy)
- `backend/tests/` (new negative-gate, fusion and scan tests)
- `frontend/src/pages/Kiosk.tsx` (clear "No banana detected" state, if the error message is not sufficient)
- `frontend/src/pages/admin/` (ROI calibration in P2; optional "Mark as not banana" review action)

## Open decisions

1. Reject versus quarantine: should a failed scan leave no record, or persist an "Unverified" record with no spoilage prediction for audit purposes?
2. Single-finger scans: supported or not? This sets the minimum evidence rule.
3. Fail-closed policy: block scans when the COCO guard is unavailable, or degrade to the classifier evidence gate with a visible warning?
4. ROI storage: normalized polygon in the database, or a station-local calibration file? The database keeps backup and restore coherent; a local file is simpler but must be included in backups.
5. Whether P1 negatives should include only background-only frames or also hard negatives with partial bananas (a hand holding one finger, a peeled banana, a plantain).

## Acceptance criteria

P0 is complete when:

- A non-banana object in any single peripheral view cannot produce a persisted scan.
- A single low-confidence box cannot establish a cultivar or ripeness.
- The pre-detector cannot fail open in production.
- Lowering the review threshold does not lower the detection cutoff.
- Stored detections preserve their original label and reveal whether they were harmonized.
- Rejected captures are retained for review rather than deleted.

P1 is complete when the retrained checkpoint meets the negative false-accept target without regressing the 168-image Top-view cultivar set, and the new calibration hash is registered.
