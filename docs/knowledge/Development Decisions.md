# Development Decisions

Documented architectural, technical, and operational decisions in BananaVision.

## 2026-10-17: Split Camera Cultivars Require Verification

- User evidence shows the same known Lakatan bunch predicted as Lakatan from Top/Right and Latundan from Left/Rear. Higher wrong-view scores can win weighted fusion; the mean winning score is not cross-view agreement. This is a real unresolved recognition failure, not a cultivar name-map swap.
- Fusion now flags a weighted cultivar candidate that lacks a strict majority of complete, valid, unique-camera summaries, even when its scores dominate. The stored candidate, original confidence and box labels remain intact. Existing weighted conflict thresholds still apply when a camera majority exists.
- The kiosk derives the same support check from existing detection summaries. It displays `Uncertain`, names the opposing camera groups, and withholds the main confidence and cultivar-dependent spoilage estimate. No API enum, persistence schema or layout redesign is involved.
- A cultivar-specific human correction remains visible when established by `originalAiResult.cultivar` or explicit cultivar-change history. The general `isOverridden` flag also covers count/ripeness/spoilage changes and therefore cannot, by itself, resolve cultivar disagreement.
- Prepared validation has 137 images but only three inferred filename groups (one per cultivar), not 137 independently identified bunches. Group identities remain uncertain. Neither earlier dataset agreement nor training mAP establishes accuracy on the station screenshots. Follow the station protocol in [[Testing and Validation]] before claiming a model recognition fix.
- The supplied `v26n_run5_khen27_1024` run contains YOLO26n weights matching local `banana_yolov26.pt` (SHA-256 `96808fa8ed706909237197e8db2510dccabfaeceed85a4d1ab5182cd28c95f7b`); the saved input resolution is 800, despite the folder name. On the same prepared VALID inputs its app count MAE is 0.942 versus the default's 0.934; combined-class recall is 88.50% versus 90.36%, with exact-count images 58 versus 55. Neither model reproduces the station cultivar error against these labels. This comparison does not justify replacement or a station accuracy claim. See [supplied-run evidence](../audits/yolo26n-supplied-run-validation-2026-10-17.json); no training, threshold tuning, frozen TEST inference or weight/config replacement occurred.

## 2026-10-17: Cultivar Disagreement and Counting Integrity

- Identical `(x, y, w, h)` boxes with competing classes count as one finger. Original class boxes, scores and voting evidence remain available for review; raw box totals can therefore exceed the finger estimate. Peripheral count extraction uses the same exact-geometry deduplication. Near-overlapping boxes do not establish physical identity.
- Pass-1 cleanup now suppresses only fully contained same-class fragments after YOLO NMS. The former extra IoU/alignment filter removed distinct adjacent and horizontally stacked fingers, overriding the calibrated Top suppression policy. Rotation geometry filtering remains heuristic; a suppressed candidate with a different parsed cultivar/ripeness now triggers conflict review.
- Rear cannot contribute its peripheral boxes again when its count supplies the anchor. Existing cross-view count estimates above every individual camera's count require review: edge position does not prove that fingers are unseen in the other views. This supersedes the earlier claim below that spatial complementarity establishes a true physical total.
- The kiosk displays `Scan Complete - Review Needed` for backend-flagged results. Confidence remains the mean winning-pair model score, not measured accuracy, camera agreement or probability that the physical count is correct. No cultivar relabeling rule, confidence increase or model replacement was introduced.
- On 137 prepared VALID images, cached identical model calls replayed through the revised classifier reduce visible-count MAE from 1.518 to 0.934, with exact counts on 55/137 images (previously 30). Localization precision/recall is 92.12%/93.83%; exact cultivar/ripeness precision/recall is 88.71%/90.36%. Counts improve on 59 images, worsen on 16 and tie on 62. See [audit evidence](../audits/yolo-scan-integrity-2026-10-17.json).
- All 137 image cultivar votes agree with the prepared labels, so these images do not reproduce the reported Lakatan-to-Latundan error. Uncertain bunch grouping, dataset labels and plain backgrounds limit generalization. The user's new scan still needs original offline four-view images and verified labels/physical total before its classification or 17-finger count can be established. See [[Testing and Validation]] and the [dataset audit](../yolo-dataset-audit-2026-10-16.md).

## 2026-10-17: Calibrated Top-Camera Overlap Filtering

- The existing checkpoint gains a Top-only NMS IoU 0.65 profile at confidence 0.50 and configured baseline IoU 0.45. Across all 31 prepared validation Top photos, count MAE decreases 1.000 to 0.806 and localization recall increases 93.17% to 97.95%, with unmatched predictions unchanged at 21 and both precision metrics improving. Seven photos improve in count error, three worsen, and 21 tie. See [policy evidence](../audits/yolo-top-overlap-validation-2026-10-17.json).
- Scope is matched by actual checkpoint SHA-256 and normalized configured camera label, independently of filenames and camera IDs. `YOLO_TOP_OVERLAP_REFINEMENT=false` disables the profile. Other checkpoints, custom thresholds and Rear/Left/Right keep configured suppression. The new YOLOv8n candidate, larger input and rotations did not pass validation guards and are not enabled by this change.
- Installed Ultralytics retains predictor arguments between calls. Every classifier call sets the intended IoU, the loaded checkpoint's saved image size, `augment=False`, `agnostic_nms=False` and `max_det=300` explicitly to prevent Top settings leaking into later views. The calibrated profile requires size 640; custom 960/1280 checkpoints retain their saved resolution. No crop, coordinate transform, confidence inflation, model replacement, schema or UI change is involved.
- Verification includes 20 new regressions, 91 passing targeted backend tests after the compatibility fix, and 62 real offline Top-to-Rear predictions matching the frozen 0.65/0.45 references. Test isolation and input/checkpoint hashes are recorded under the training folder's `top-view-experiment-iou065/`; no station hardware or data was used.
- This improves measured per-image visible-instance detection on the prepared validation data; it does not prove recovery of all ten fingers in the user's screenshot or a unique physical bunch count across cameras. Preserve frozen test reports and validate station scenes only with manually supplied offline copies.

## 2026-10-17: Separate YOLOv8 Training on Dataset v13

- The user authorized training YOLOv8 on `D:\Banana_Ripeness.v13i.yolo26`. Training uses a separate CUDA environment and dataset copy under `D:\BananaVision-Training\v13-yolov8-20261016`; application dependencies, weights and station configuration are unchanged.
- Existing checkpoint identity was verified on October 17: `backend/app/ml/banana_yolov8n.pt` and `backend/app/ml/weights/banana_yolo26m.pt` have identical SHA-256 `e6f4e6825a642063dfd80e0b4251920e022ce85649d477ebde75a00a852f8b89`. Internal metadata identifies `yolo26m.yaml`, scale `m`, 21,791,392 parameters and the expected 12 trained classes. Filenames do not establish architecture; the existing-model benchmark applies to both copies. A fresh YOLOv8 run is a comparison candidate, not evidence that the trained checkpoint needs replacement.
- The copy removes two confirmed background-box rows and quarantines one seven-file capture with contradictory cultivar names/labels. Other labels are preserved. Source data remains intact.
- Conservative aliases merge 90 filename prefixes into 19 cultivar/ordinal groups. The user could not confirm physical identities; this grouping can merge unrelated fruit and cannot prove independence if bunches were renumbered. All matching groups remain in one split, and held-out files come only from the original unaugmented export splits.
- The prepared split contains 5,262 training, 137 validation and 137 test images, with all 12 classes represented in each. Some validation classes have few labels; per-class results and the grouping uncertainty must accompany aggregate metrics.
- The existing YOLO26 comparison supports NMS 0.65 as a calibration candidate, with lower average count error but more positive count bias. It is not a live accuracy claim or a production setting change. Calibrate the new model on validation data and reserve test data for the frozen comparison.
- The bounded training launcher completed successfully: 78 total epochs, early stopping after 20 epochs without improvement, best checkpoint at epoch 58. Automatic evaluation finished at 04:58 AM on October 17 (Asia/Manila). Validation retained NMS 0.45; 0.65 exceeded the predeclared precision-loss limits. Settings were frozen before test evaluation.
- On 137 prepared test images, existing YOLO26m versus new YOLOv8n count MAE is 0.832 versus 0.905, combined-class recall 89.46% versus 84.42%, and exact-count images 54 versus 60. The candidate's count MAE is worse in all four views; top-view combined-class recall is 89.05% versus 78.45%. Retain the existing model; no application model or station setting was changed. These offline results do not establish station accuracy, and the old model may have seen related training images.
- Independent review verified checkpoint/manifest and held-out image/label hashes, identical test inputs/configuration/matching, calibration timing and recomputed saved-prediction metrics. The [comparison summary](../audits/yolov8-v13-training-comparison-2026-10-17.json) preserves metrics and artifact hashes. Further accuracy work requires a manually supplied offline copy of four-view station-style photos with verified bunch totals/cultivar/ripeness and per-view visible-finger labels; do not extend training blindly or tune against this test set.
- The candidate remains available for testing. A later isolated smoke test using the existing app Python runtime loaded all 12 classes and ran four validation images successfully; Top/Left/Right/Rear counts 13/10/8/11 match the saved predictions. `candidate-app-runtime-smoke.json` preserves evidence. The training folder also contains `visual_comparison.html`, an offline interactive review of both models on all 137 validation photos, with view/variety/count-error filters and box/label overlays. This provides visible test results without changing the app's active model or treating dataset metrics as live accuracy.
- See [dataset audit](../yolo-dataset-audit-2026-10-16.md) for evidence and counting limitations. Generic COCO weights must be fine-tuned before they can provide the app's 12 cultivar/ripeness labels.

## 2026-10-16: Live Detection and Result Review

- YOLO retains candidates at `min(YOLO_CONFIDENCE_THRESHOLD, saved confidence_threshold / 100)`. The model setting defaults to 0.50; the saved review setting defaults to 85%. Lower saved settings remain supported.
- Fusion uses the saved setting for confidence review, alongside camera support and conflict checks. A confident box score does not establish agreement across camera views.
- Both thresholds are snapshotted before processing the camera views. Original box confidence scores are retained.
- The configuration response reports the effective saved detection cutoff as read-only `detection_confidence_threshold` in percent. The settings slider controls review; its helper identifies the **current** saved detection cutoff.
- Kiosk scan results expose the existing review flag in the result title. No database schema or model weight change is required.
- Finger count currently means the maximum per-camera YOLO box count, assuming one detection per finger. There is no matching of physical fingers across views. Do not sum view counts or infer a correction multiplier from a reported total; validate per-view detection recall and whole-bunch count error separately. Large overlapping rectangles alone do not establish incorrect training annotations.
- See [[Resolved Bugs]] for the filtering and label-pair regressions. Real-world accuracy still requires labeled offline fixtures; synthetic tests establish pipeline behavior only.

## 2026-10-16: Loading States & Data Consistency

### 1. Distinction Between Initial Load, Action, and Background Refresh
- **Decision**: Initial data loads for structured views (KPIs, tables, details) must render skeleton placeholders to match final layouts. Continuous actions (calibration, printing, backup, intake) display spinners/badges while disabling triggers. Background refreshes preserve the previous valid snapshot rather than blanking the screen.
- **Rationale**: Prevents visual flicker, prevents premature "0 records found" flashes, and provides smooth user experience on mobile and kiosk interfaces.

### 2. Snapshot Retention on Failed Refresh
- **Decision**: When a background refresh or polling fails (network dropout or temporary server unavailability), the frontend retains the previous valid data snapshot, displaying an inline `<Alert>` with explicit Retry rather than replacing the entire view with an error screen or zero counts.
- **Rationale**: Operators and supervisors can still reference active scan details and inventory while attempting recovery.

### 3. Review Queue Scope
- **Decision**: Review links must not pre-filter by `status=Flagged`. They must navigate using `attention=review` alone.
- **Rationale**: Low-confidence or unclassified scans require manual inspection even if not yet formally marked as "Flagged". Filtering by `status=Flagged` inadvertently hid scans that needed review.

## 2026-10-17: Analytics & AI Metric Isolation

### AI Model Confidence Isolation from Mutable Scans
- **Decision**: In `backend/app/services/analytics.py:85-92`, confidence metrics strictly query `ScanOriginalAiResult` (via outer join) rather than mutable `scans` table columns. If a scan was overridden by an operator and lacks an original AI prediction record, it evaluates to `None` and is excluded from model confidence metrics.
- **Rationale**: Prevents human manual overrides or quality control corrections from contaminating AI model metrics. Analytics reflects genuine machine-learning model performance.
- **Role Isolation**: Scoped strictly by role: Operators are isolated to their own scans (`OperatorProfile.account_id == user.id`), whereas Admins view station-wide aggregates.
- **Zero-Count Safety**: Guarded denominators prevent division-by-zero across all metrics when `total_scans == 0`, presenting `"―"` gracefully without NaN or errors.
- **Operator Performance Metrics**: Surfaced backend `flag_rate` (as `Flag Rate (%)`) and `overridden_scans` (as `QC Overrides`) columns for Administrator users in the Operator Performance Table (`Analytics.tsx`), providing supervisory visibility into operator defect flags and manual correction counts.

## 2026-10-17: Scan Classification Overrides & Spoilage Recalculation

### Strict Finger Count Validation & Environmental Spoilage
- **Decision**: In `backend/app/schemas/scan.py`, `ScanOverrideRequest.finger_count` enforces `Field(default=None, ge=1)` with a Pydantic field validator rejecting `< 1` or `null`. In `QualityControl.tsx` and `ScanDetail.tsx`, form submission is blocked and the Save Changes button disabled when `fingerCount` is empty or `< 1`. Changing cultivar or ripeness passes ambient `temperature` and `humidity` to `getSpoilageDays()`.
- **Rationale**: Eliminates the previous silent fallback `parseInt(...) || 0`, which caused non-numeric or cleared inputs to persist 0-finger bunches and pollute downstream batch statistics. Dynamically recalculating shelf-life estimates with environmental factors ensures operational spoilage predictions remain accurate after quality control overrides.

## 2026-10-17: Review Notes Validation & Recovery UX

### Review Note Error Layout & Whitespace Stripping
- **Decision**: In `frontend/src/pages/admin/QualityControl.tsx`, note loading failure alerts wrap the error message and inline Retry action in `flex items-center justify-between gap-3 text-sm text-muted-foreground`. In backend Pydantic models, `ScanNoteCreate` inherits `Reason` constraints (`strip_whitespace=True, min_length=1`), strictly rejecting whitespace-only notes with HTTP 422.
- **Rationale**: Prevents text overlapping or colliding against button borders on error displays during network recovery, and guarantees audit trail integrity by preventing empty or whitespace-only administrative notes.

## 2026-10-17: Top Camera 180° Rotation Fallback

### Guarded Two-Pass Detection for Top Camera Finger Recall
- **Decision**: In `backend/app/services/classification.py`, when `is_calibrated_top` is met (camera label "Top", calibrated checkpoint SHA `e6f4e6825...`, 640 input resolution, conf 0.50, and base IoU 0.45) and `yolo_top_rotation_fallback` is enabled (default `True` in `backend/app/config.py`), inference executes a second pass on a 180°-rotated frame (`image[::-1, ::-1].copy()`). Remapped bounding boxes `(W - rx2, H - ry2, W - rx1, H - ry1)` with IoU <= 0.40 against pass-1 detections are retained and appended.
- **Rationale**: Resolves severe undercounting on the Top camera view where orientation-dependent finger cluster geometry caused the detector to miss ~half the prominent foreground fingers. Rotating 180° exposes complementary finger orientations without retraining or modifying weights. The strict guards ensure non-Top camera views, custom models, and uncalibrated thresholds remain completely unaffected with zero behavioral changes.

## 2026-10-17: Multi-Camera Spatial Complementarity Finger Fusion

### Heuristic Multi-Tier Count Estimate (Review Required)

The counting-integrity audit above supersedes any interpretation of this heuristic as verified cross-camera identity matching. The synthetic 19-finger example demonstrates arithmetic on an assumed arrangement; it does not validate a physical total.
- **Decision**: In `backend/app/services/fusion_engine.py`, replaced the naive `max(finger_counts)` bottleneck with a multi-camera spatial complementarity model (`_fuse_finger_counts` and `_extract_novel_peripheral`), enabled via `multi_camera_finger_fusion: bool = True` in `backend/app/config.py`:
  1. **Anchor View:** Takes the Top camera view count ($N_{\text{top}}$) as the primary cluster tier.
  2. **Lateral Outer Flanks:** Inspects Left ($rel_x \le 0.35$) and Right ($rel_x \ge 0.65$) camera detections to identify novel peripheral fingers extending beyond Top's 2D perspective.
  3. **Inner Concavity/Underside Tier:** Inspects the Rear camera ($rel_y \ge 0.55$) to detect fingers situated along the inner lower tier occluded from above.
  4. **Strict Bounding Theorem:** Fused count is strictly bounded: $\max_{k}(c_k) \le N_{\text{fused}} \le \sum_{k} c_k$. If disabled, uncalibrated, or single-camera, it seamlessly falls back to $\max(c_k)$.
- **Rationale**: Different viewpoints can expose occluded fingers. Taking `max()` can undercount, while taking `sum()` can repeat sightings. Peripheral positions provide a heuristic estimate (e.g. 10 Top + 3 Left + 3 Right + 3 Rear = 19), but without cross-camera correspondence those additions may include already counted fingers. Bounds between maximum and sum do not prove accuracy; the current result requires operator review when it exceeds every per-view count.

## 2026-10-17: YOLO Bounding Box Deduplication & Containment Refinement

### Robust Spatial Deduplication for Rotation Fallback and Relaxed Top NMS
- **Decision**: In `backend/app/services/classification.py`, introduced `_box_containment(a, b)` and `_is_duplicate_detection(candidate, existing, iou_thresh)`:
  1. **Containment Filtering (IoM):** Calculates intersection over the smaller box area. If $\text{IoM} \ge 0.75$, the candidate is suppressed as a nested/partial fragment of an already boxed finger.
  2. **Longitudinal Axis Alignment:** If $\text{IoM} \ge 0.45$ and the horizontal center displacement $\Delta x \le 0.25 \cdot \min(w_a, w_b)$, the detection is classified as the same physical finger column and suppressed.
  3. **Multi-Pass & Self-Deduplication:** In pass 2 (rotation fallback), candidates are checked against all accepted detections (both pass 1 and previously accepted pass 2 novel fingers) to prevent cascading duplicates. In pass 1, same-class nested boxes surviving relaxed NMS are suppressed while preserving multi-class conflict detection.
- **Rationale**: Real elongated, curved banana fingers frequently produce partial segment detections in 180°-rotated passes or under relaxed Top NMS ($\text{IoU} = 0.65$). Because the sub-box area is small, standard $\text{IoU}$ often fell to $0.30 - 0.38 \le 0.40$, allowing redundant duplicate boxes to be drawn on the same finger (e.g. Finger 3 having both $76\%$ and $52\%$ boxes, and Finger 4 having both $71\%$ and $64\%$ boxes), inflating Top detections from 9 to 11 and artificially boosting fused estimates from 17 to 20 during progressive fruit removal. Combining containment with longitudinal axis alignment prevents double-counting while preserving distinct side-by-side neighbor fingers.
