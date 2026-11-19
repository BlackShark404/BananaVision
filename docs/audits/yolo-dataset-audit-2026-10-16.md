# YOLO dataset and finger-count audit — 2026-10-16

The user supplied `D:\Banana_Ripeness.v13i.yolo26` to investigate a bunch they
counted as 19 fingers, reported as 12 by BananaVision. This audit reads the export and
the repository's default weight file offline. It does not use station captures,
cameras, the database, `.env`, or the running station. Source images, labels and
weights are unchanged.

## Dataset coverage

| Split | Images | Annotation boxes | Largest annotation count in one image |
| --- | ---: | ---: | ---: |
| Train | 6,668 | 59,920 | 17 |
| Validation | 417 | 3,675 | 16 |
| Test | 416 | 3,642 | 15 |
| Total | 7,501 | 67,237 | 17 |

All images have corresponding label files. No malformed YOLO rows were found:
rows have a class ID from 0–11 and four normalized coordinates with positive
width and height. This format check does not establish annotation completeness
or semantic correctness. All 12 cultivar/ripeness combinations occur; none of
Lakatan, Latundan or Cardaba is absent.

The inspected annotations generally describe individual visible fingers. No
image has 19 supplied labels. This is **not a model count limit**, and does not
prove that no photographed bunch physically contains 19 fingers: hidden fruit
and annotation omissions are separate issues.

## Confirmed label defects and policy questions

Two training label files contain an extra background-sized box at line 7:

```text
train/labels/B4_Latundan1_NoneChemical_02570_top_jpg.rf.995e92959d649ecc59efa0066dfece83.txt
10 0.5 0.5 0.85 1

train/labels/B4_Latundan1_NoneChemical_02570_top_jpg.rf.b17c29c829489476c6a031ff4acd8f56.txt
10 0.5 0.5 0.75 1
```

Class 10 is `latundan_semi_ripe`. These boxes cover 85% and 75% of the entire
image, including mostly background. The other six rows describe the visible
fingers. These specific extra rows should be removed in a reviewed training
copy; they do not establish the cause of every live error.

One named capture also contradicts its cultivar labels:
`B2_Latundan3_CH_01131` contains 65 Lakatan boxes across seven exported files,
while the remaining images under `B2_Latundan3_CH` contain 981 Latundan boxes.
The filename or the labels could be wrong. The training copy quarantines these
seven files pending human review instead of guessing a replacement class.

Some sparse examples box a yellow fruit but omit a separate, visibly degraded
fruit. One validation example is:

```text
valid/images/B1_Latundan3_NoneChemical_00957_left_jpg.rf.c11751f4712ce9e2bb83923648d1aa8b.jpg
```

Its only annotation is class 8, `latundan_overripe`. The intended policy for
severely degraded fruit is unknown. Review that policy before adding labels:
counting all physical fingers and labeling only eligible fruit produce
different targets. Wide boxes around curved fruit are not automatically errors.

## Related scenes cross dataset splits

Removing the `_jpg.rf.<hash>` suffix and one trailing camera suffix (`_top`,
`_left`, `_right`, `_back`) creates 1,049 named capture groups. Under this rule,
411/417 validation images and 411/416 test images have another view of the same
named capture in training. This is evidence inferred from filenames, not proof
of exact pixel duplication or independently verified physical identities.

For example, `B1_Lakatan1_NoneChemical_00079` has augmented back/top images in
training and left/right images in test. Performance on these related scenes may
overstate generalization to a new bunch or station. A future training export
should split by verified physical bunch identity before augmentation and keep
all related sessions, views and sequential captures in the same split. Filename
capture groups alone do not establish that identity. The user is unsure whether
the same bunch has other filename prefixes, so any inferred grouping must state
that uncertainty rather than claim proven independence.

The inspected dataset samples use a light plain background, often with black
portrait-image padding and space around the fruit. User-provided live screenshots
show close framing, a wooden table, other background objects and substantial
overlap. This visual difference is a plausible generalization issue; it is not
measured proof of the cause. Representative labeled offline station images are
needed to measure live-like accuracy.

## Model and overlap filtering

The audited repository default is
`backend/app/ml/weights/banana_yolo26m.pt`. Its stored metadata records a
September 12, 2026 checkpoint, 640-pixel training size, an `epochs=300` training
setting and Ultralytics
8.4.148. The supplied dataset export is dated October 15. Dates alone cannot
establish whether training content changed. The running station's model choice
was not inspected. A newer `best.pt`, if available, should be evaluated separately
before considering replacement. On October 17, SHA-256 verification established
that `backend/app/ml/banana_yolov8n.pt` contains exactly the same checkpoint as
this default file. Its internal architecture is `yolo26m.yaml`, scale `m`, with
21,791,392 parameters and all 12 trained classes. The YOLOv8 filename is therefore
misleading; the existing-model results below apply to both copies. Neither file
was renamed, replaced or modified during this check.

The user confirmed that v13 had not been trained before the separate run and
requested training YOLOv8 on this export. This produces a comparison candidate;
it does not establish that retraining is necessary to fix the live pipeline.
Generic COCO weights are a training starting point; they do not provide the
12 custom banana classes before fine-tuning. See the official
[YOLOv8 documentation](https://docs.ultralytics.com/models/yolov8) and
[training reference](https://docs.ultralytics.com/modes/train).

The model head reports `end2end=False`, so conventional non-maximum suppression
(NMS) applies. The application's default overlap threshold is 0.45. As a
diagnostic, running class-aware greedy NMS on the *supplied annotation boxes*
would remove 171/3,675 validation annotations at 0.45, versus 8 at 0.65. Equal
annotation scores and row order were used. These are not model predictions or
accuracy measurements: they only show that the labels contain overlapping
objects that merit an actual inference comparison. Increasing the threshold
could also retain duplicate predictions.

The completed inference comparison used all 417 original validation images,
the repository default YOLO26 model, confidence 0.50 and image size 640. Test
images were not used for this parameter comparison. Unsuppressed candidates
(`iou=1`, `max_det=10000`) were replayed through the installed class-aware NMS;
seven direct baseline predictions matched the replay. Matching used maximum
cardinality one-to-one assignments at box IoU >= 0.50, with localization-only
and exact combined-class results computed separately.

| Metric | NMS 0.45 | NMS 0.65 |
| --- | ---: | ---: |
| Mean absolute count error, fingers/image | 0.938 | 0.844 |
| Images with exact annotation count | 161/417 | 188/417 |
| Localization precision | 92.47% | 92.39% |
| Localization recall | 92.95% | 97.06% |
| Exact combined-class precision | 87.95% | 87.93% |
| Exact combined-class recall | 88.41% | 92.38% |
| Signed count bias, predictions minus labels/image | +0.046 | +0.446 |

Count error improved in 76 images, worsened in 50 and stayed equal in 291.
All four camera groups and 10/12 dominant-class groups improved in aggregate;
Cardaba Ripe and Cardaba Overripe count error increased. Visual inspection of
six changed examples confirmed restored adjacent annotated fingers, alongside
remaining duplicate/localization errors. NMS 0.75 had slightly worse count error
than 0.65 and added mostly unmatched predictions.

This supports 0.65 as a candidate to evaluate for the new model. It does not
prove a fix for live 19-finger counting, and no production NMS setting was
changed by this audit. See the
[full benchmark summary](yolo-v13-overlap-validation-2026-10-16.json).

## Completed YOLOv8n comparison - 2026-10-17

The separate YOLOv8n run completed 78 total epochs, including the initial saved
epoch before resume. Early stopping ended the run after 20 epochs without
validation improvement; the best checkpoint is from epoch 58. Training and the
automatic comparison finished successfully, with no training stderr errors.
The candidate remains at
`D:\BananaVision-Training\v13-yolov8-20261016\runs\yolov8n_v13_b16\weights\best.pt`.

Validation selected NMS IoU 0.45 at confidence 0.50. Raising NMS IoU to 0.65
slightly lowered validation count MAE (0.985 to 0.971), but reduced localization
precision by 0.86 percentage points and exact combined-class precision by 0.51
points, exceeding the predeclared 0.50-point limits. The choice was frozen before
test inference. No test result was used to adjust the model or thresholds.

The frozen comparison used the same 137 prepared test images and 1,252 labels,
image size 640, confidence 0.50, class-aware NMS IoU 0.45 and one-to-one matching
at box IoU >= 0.50 for both models:

| Prepared test metric | Existing YOLO26m | New YOLOv8n |
| --- | ---: | ---: |
| Mean absolute count error, fingers/image | 0.832 | 0.905 |
| Exact annotation-count images | 54/137 | 60/137 |
| Localization precision | 94.00% | 93.10% |
| Localization recall | 93.85% | 91.61% |
| Exact combined-class precision | 89.60% | 85.80% |
| Exact combined-class recall | 89.46% | 84.42% |

The candidate improves absolute count error on 31 images, worsens it on 32 and
ties on 74. Its average count error is higher in all four camera groups. Top-view
combined-class recall drops from 89.05% to 78.45%. Cardaba semi-ripe recall drops
from 87.91% to 60.44%, while Cardaba ripe precision drops from 81.32% to 61.16%.
The extra exact-count images therefore do not establish an overall improvement.

Independent offline checks verified actual checkpoint, manifest, held-out image
and label hashes; identical test configurations, class ordering, matching rules
and ground-truth inputs; and validation-before-test calibration timing. Recomputing
aggregate, per-view, per-group, dominant-class and all 12 exact-class metrics from
the saved predictions found no discrepancies. This comparison review used saved
test predictions. See the [durable comparison summary](yolov8-v13-training-comparison-2026-10-17.json)
for full precision, recall, count metrics and artifact hashes. The original
per-image reports and `TRAINING_RESULTS.md` remain in the separate training folder.

Retain the existing model: this candidate has not demonstrated an overall upgrade
on these images. The old model's original training provenance is uncertain and
may include related images, so this is not proof of a fair unseen-data ranking.
Neither comparison establishes performance on station scenes. No application
weights, inference settings, dependencies or station records were changed.
Extending this run solely because of the test results would also compromise the
test's role as a held-out comparison.

### Visual review and application-runtime compatibility

The trained candidate is preserved and has been tested with BananaVision's
existing Python interpreter, without importing the application. A fresh isolated
working/config directory and CPU-only inference were used for four preselected
validation photos (the first photo for each camera view). All 12 classes loaded;
outputs were finite; Top/Left/Right/Rear prediction counts were 13/10/8/11,
matching the candidate's saved validation counts. Input and checkpoint hashes were
unchanged. This verifies loading/inference compatibility, not live accuracy or
physical bunch totals. The report is `candidate-app-runtime-smoke.json` under the
separate training folder; versions were Ultralytics 8.4.40 and PyTorch 2.11.0.

`visual_comparison.html` in that folder provides an offline visual comparison of
all 137 validation photos. Both models use the same embedded photo; controls
filter by view, cultivar and whether candidate absolute count error is lower,
higher or tied. Prediction labels/confidences, annotation overlays, unmatched
annotations and unmatched predictions remain visible for inspection. These are
saved predictions, not a live camera feed. The page labels this as validation
data, whose aggregate metrics differ from the frozen test comparison above.
No photos are uploaded, and opening the HTML changes no application setting.
`visual-comparison-manifest.json` records its source-report/model/image provenance.

## Top-view overlap refinement - 2026-10-17

After the user supplied a new top-view screenshot with roughly ten visible
fingers but only four/five detections, a bounded experiment compared larger input
size 960 and 90/270-degree rotations against the frozen baseline. All 31 prepared
validation Top photos (293 labels) were used for both checkpoints. None of those
alternatives passed the predeclared count-error, recall and precision guards.
They were not added to the application.

A single 640-pixel pass with NMS IoU 0.65 passed all guards for the existing
YOLO26m checkpoint at confidence 0.50. This retains more overlapping candidate
boxes; it does not split a broad group box into guessed fingers. The same change
failed the guards for the new YOLOv8n candidate and is not applied to that model.
Only prepared validation images were used; the frozen test reports were preserved.

| Top validation metric | Existing model NMS 0.45 | Existing model NMS 0.65 |
| --- | ---: | ---: |
| Mean absolute count error | 1.000 | 0.806 |
| Localization precision | 92.86% | 93.18% |
| Localization recall | 93.17% | 97.95% |
| Exact combined-class precision | 88.10% | 88.64% |
| Exact combined-class recall | 88.40% | 93.17% |
| Matched annotations / unmatched predictions | 273 / 21 | 287 / 21 |

Count error improves on seven photos, worsens on three and ties on 21. Undercount
photos decrease from eight to three, while overcount photos increase from ten to
14; signed bias rises from +0.032 to +0.484. The aggregate improvement is not a
guarantee for every image. See the [full policy evidence](yolo-top-overlap-validation-2026-10-17.json).

The application now passes the configured camera label into the classifier and
enables IoU 0.65 only for normalized `Top`, the calibrated checkpoint fingerprint,
confidence 0.50, saved input size 640, configured baseline IoU 0.45, and enabled
`YOLO_TOP_OVERLAP_REFINEMENT` (default true). Unknown/new checkpoints and custom
thresholds use the existing configured IoU. Finger count remains the retained box
count. Rear, Left and Right keep their configured IoU, with explicit input size,
augmentation, class-aware suppression and maximum detections on every call:
the installed Ultralytics predictor retains prior arguments between calls.
Box coordinates and BGR pixels remain unchanged. The
[Ultralytics inference reference](https://docs.ultralytics.com/modes/predict/#inference-arguments)
documents the suppression and input-size options; behavior was also checked in
the installed library.

Synthetic regressions exercise neighboring overlapping fingers, Top-to-Rear
argument reset, profile guards, file fingerprinting, original coordinates and
camera-label routing when Top is not CAM-001. The supplied screenshot has not
been run through the changed classifier: an original offline copy is still needed
to establish whether its ten visible fingers are all detected.

The real application classifier also passed 62 offline predictions: all 31 Top
photos followed immediately by the same frame labeled Rear. Counts/classes match
the 0.65/0.45 references respectively, with boxes within 0.1 pixel and confidence
within 0.001. This used an isolated CPU application environment. A compatibility
review additionally preserves each custom checkpoint's saved input resolution and
keeps non-640 inputs outside the calibrated profile; targeted tests cover this,
unreadable fingerprints and all existing classification/scan contracts.

### User retest: the reported Top scene remains unresolved

The user's subsequent kiosk screenshot still shows five Top detections, including
broad boxes spanning several visible fingers. This confirms that the proposed
overlap adjustment has not established a fix for this scene; its activation in
that running process has not been independently verified. The validation results
above remain offline measurements and do not identify the cause of every group box.

A separate empty test folder, `D:\BananaVision-Training\top-camera-test`, was
prepared. The user was asked to save the captured Top result photo there using
the browser's **Save image as** action and provide its filename/known variety.
The viewer renders boxes in a separate SVG layer, so saving the base result image
provides original pixels for an exact-frame comparison. No station capture file,
database or physical camera was accessed, and no additional inference setting
was changed following this retest report.

## Counting semantics and next data needed

As of the October 17 counting-integrity fix, `classification.py` counts unique
exact box geometries per image while preserving competing class boxes for review.
Its pass-1 fragment cleanup preserves distinct overlapping neighbors retained by
the configured NMS. Conflicting duplicate class hypotheses require review, even
when the selected model score is high. Raw box badges can exceed finger counts.

`fusion_engine.py` optionally estimates additional fingers from peripheral box
positions. If Rear supplies the count anchor, its own peripheral boxes are not
added again. Any estimate above every individual view's count is flagged for
review; disabling `MULTI_CAMERA_FINGER_FUSION` uses the maximum per-camera count.
There is still no cross-camera correspondence for individual physical fingers.
Adding camera counts would count some fingers repeatedly; a multiplier would
not be justified by one reported total. Even perfect per-view detection can
return 12 for a physical total of 19 when each individual camera sees at most
12 fingers. The difference of seven does not, by itself, prove seven detector
misses; per-view visible-object labels are needed to separate detection error
from occlusion and the limitations of taking the maximum view count.

For a defensible 19-finger evaluation, keep untouched test bunches with known
physical totals and annotate visible fingers in each offline camera image.
Report per-view misses/duplicates separately from whole-bunch count error.
Completely hidden fingers cannot be established from an individual 2D view.
The current export and screenshots do not establish that a parameter change
will recover exactly seven missing fingers.

The [October 17 integrity audit](yolo-scan-integrity-2026-10-17.json)
compares the resumed checkout with the corrected application postprocessing on
all 137 prepared VALID images using cached identical model calls. Visible-count
MAE decreases from 1.518 to 0.934; 55 images have exact visible counts. Count error
improves on 59 images, worsens on 16 and ties on 62. These figures are per-image
visible-label metrics, not physical bunch counts or live-station accuracy.
No frozen TEST image was rerun or used to select this change.

All validation image cultivar decisions agree with the existing dataset labels;
the reported Lakatan-to-Latundan station error is not reproduced by this set.
Dataset label correctness, uncertain bunch grouping and background differences
remain material limitations. Wrong combined-class spatial matches still have
an average model score of approximately 80.8%; confidence is not an accuracy
measurement. Investigating the new 17/18-finger scan requires original offline
images from all four views, verified cultivar/ripeness and physical total, and
visible-instance annotations to separate missed, repeated and hidden fingers.

### Supplied YOLO26n Run and Cross-View Cultivar Conflict

The later supplied `v26n_run5_khen27_1024` training run saves input size 800 and
the expected 12 classes. Its `best.pt` matches local `banana_yolov26.pt`, not the
audited default YOLO26m weights. The [application comparison](yolo26n-supplied-run-validation-2026-10-17.json)
uses the same 137 prepared VALID images without frozen TEST inference or tuning.
Candidate versus default visible-count MAE is 0.942 versus 0.934; combined-class
recall is 88.50% versus 90.36%. Exact-count images are 58 versus 55. Both match
all image cultivar labels in this set, so neither comparison establishes a fix
for the station Lakatan-to-Latundan error or an overall replacement benefit.

These 137 validation images occupy just three inferred filename groups, with
uncertain physical identities. The user evidence instead shows a known Lakatan
bunch split between Top/Right Lakatan predictions and Left/Rear Latundan
predictions, some above 90% score. Fusion now requires review when the weighted
candidate lacks a strict camera majority; the kiosk exposes the split as
`Uncertain` and withholds confidence/spoilage from the main result card.
This is uncertainty disclosure, not an improvement to trained recognition.
Follow the [station cultivar protocol](../knowledge/Testing%20and%20Validation.md#station-cultivar-recognition-protocol)
for trusted labels, physical-bunch splits and untouched station evaluation.
