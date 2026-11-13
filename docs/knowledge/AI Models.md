# AI Models

Verified against the source on 2026-11-13. Related: [[Frontend]], [[Testing and Validation]],
[[Development Decisions]], [[Non-Banana Detection Audit]] (a proposal written before the
OOD gate merged; the gate already covers its fail-closed verifier and checks every view,
but one banana view still admits a scan by default, so its "Top plus one other view"
proposal stays open).

## Scan pipeline

| Stage | File | Model | Role |
| --- | --- | --- | --- |
| 1. Banana verifier | `backend/app/services/banana_detector.py` | COCO `yolo26n.pt`, class 46 | Is a banana in the frame, and where |
| 2. Cultivar detector | `backend/app/services/classification.py` | Trained 12-class YOLO (`cultivar_ripeness`) | Finger boxes with cultivar and ripeness |
| 3. Fusion | `backend/app/services/fusion_engine.py` | Rules | One result from up to four camera views |
| 4. Shelf life | `backend/app/services/spoilage.py` | Random forest | Estimated days |

`backend/app/services/scan_service.py` runs the stages. The trained cultivar weights
(`backend/app/ml/weights/*.pt`) and their dataset are not in the repository.

## Finger counting (2026-11-13)

Each camera view counts its unique finger boxes; the scan stores the largest view count
(`fusion_engine.py`, unchanged). Decision record: [[Development Decisions]]; bug history:
[[Resolved Bugs]]; tests: [[Testing and Validation]].

### Which YOLO26 head runs (`YOLO_INFERENCE_HEAD`)

A YOLO26 checkpoint carries two detection heads. Ultralytics 8.4.40 (pinned) runs the
NMS-free one-to-one head unless the file stores the choice. NMS and every `iou=` setting
(the calibrated Top 0.65, base 0.45, recovery 0.70) are then skipped, test-time
augmentation does nothing, and the first prediction fuses the other head away. The
audited checkpoints (`e6f4…`, `9680…`) ran with NMS (`model_end2end: false` in their
audit files); the head of the V2 checkpoints is not recorded.

- `one_to_many_nms` (default): the head every count audit measured; IoU settings act.
- `one_to_one`: NMS-free. `checkpoint`: the file's own default (the earlier behaviour).
- `BananaClassifier.load()` fixes the head right after `YOLO(path)`, before warmup, and
  logs it; `inference_head` reports it and `evaluate_ood_gate.py` records it.
- Mechanism proof on the COCO weights:
  `docs/audits/inference-head-check-2026-11-13.json`. Checkpoint default: one-to-one,
  10/10/10 boxes at IoU 0.3/0.7/0.95. NMS head: 9/10/17. A later `end2end=False`
  predict argument cannot switch back. Run `scripts/check_inference_head.py static`
  (safe, no unpickling) or `runtime` on the station weights to see their head.

### Counting rules (each setting `false` restores the earlier behaviour)

| Setting | Problem | Rule |
| --- | --- | --- |
| `YOLO_AXIS_AWARE_ROTATION_DEDUP` | The rotated Top pass merged a lying finger with the one stacked on it | The "same finger column" check compares centres across the finger's long axis |
| `YOLO_HAND_BOX_SPLIT` | A confident whole-hand box hid the side-by-side fingers inside it as "fragments" | A box that hid at least two side-by-side fingers and passes the cluster rule is replaced by them (they count, they do not vote) |
| `YOLO_RIPENESS_OUTLIER_FILTER` | Brown wood boxed "Cardaba Ripe 64 %" next to an unripe hand | A box two or more ripeness stages from a clear, single-cultivar majority is dropped if it is less confident than the best majority box or touches none of its boxes; the scan is flagged. A hand that also has fingers at the stage in between (unripe + semi ripe + ripe) is ripening, so none is dropped |
| `YOLO_RECOVERY_WITHIN_HAND` | The low-threshold second pass (conf 0.25) added a window frame above the hand (29 %) | Second-pass boxes must lie within the hand along the fingers' length, and at most one finger-width beside it |
| `YOLO_SIDE_VIEW_LIP_FILTER` | The second pass added the wooden plate under the hand (26 %) on the Left camera | The low, wide, weak platter-lip filter runs on Left, Right and Rear (was Rear only), in both passes |
| `YOLO_RECOVERY_ADJACENT_RIPENESS` (off) | Mixed-ripeness hands get no second-pass fingers of the neighbouring stage | Measurement only: admit second-pass fingers one stage away |

Fingers restored from a hand box are checked against the rotated Top pass's own repeat
rule, so a finger that pass already found is not counted twice. Off-evidence fragments of
a hand box count as gate interventions only when they change the split's outcome.

Accepted trade-offs (independent review, 2026-11-13): the second pass never admits a box
whose centre lies beyond the confident fingers along their length, so a hidden finger
found only by that pass and hanging lower than every confident finger is missed; the
platter-lip filter can drop a real lying finger scored 0.50–0.60 low in a Left or Right
view (the stored count is the largest view, so another view usually still counts it).

Dropped ripeness outliers are counted in `ClassificationResult.ripeness_outlier_boxes`,
logged, appended to the scan's activity entry ("N boxes with inconsistent ripeness
dropped, flagged for review") and flag the scan, like gate-dropped boxes. Hand-box splits
are counted in `hand_box_splits`. The OOD gate contract still holds (randomized tests).

**Not measured.** No banana weights, photos or GPU were available, so none of these
changes has a measured effect on count accuracy yet. The only real-weights check is the
head mechanism above. The ripeness rule can miss a wood box that overlaps the hand and is
the most confident box; that case needs station background photos as training negatives.

### Measuring and retraining when data arrives

All three run from `backend/` with the backend requirements installed; each `--help` lists
every option.

1. **Get the data.** A teammate attaches the weights (`.pt`), the Roboflow export zip and
   station background photos to a GitHub release, ideally with a `SHA256SUMS` file:
   `python scripts/fetch_training_assets.py github --repo RoronoaZoro1206/BananaVision
   --tag <tag> --dest <new empty dir>` (a private repository needs a token in
   `GITHUB_TOKEN`, sent only as a header and never printed). `local --archive <zip>
   --dest <dir>` handles a file already on disk. Archives are checked against
   `SHA256SUMS` and extracted safely (no absolute paths, `..`, links or special files).
   The script prints the next commands. Roboflow downloads are not built in, because
   Roboflow takes the key in the URL.
2. **Prepare** the export with `scripts/prepare_yolo_dataset.py` (grouped 70/15/15 split).
3. **Measure** visible counts: `python scripts/evaluate_finger_count.py visible --weights W
   --split <prepared>/valid --configs baseline head=one_to_one hand_box_split=off
   ripeness_outlier=off recovery_within_hand=off side_view_lip=off --output report.json`
   (`--gate` adds the banana verifier). It reports MAE, exact, ±1 and bias overall and per
   view, cultivar and size, and paired comparisons with a seeded bootstrap 95 % interval.
   It warns when a configuration cannot act (for example an unregistered checkpoint turns
   the recovery pass off) and refuses the TEST split unless `--frozen-test` is given with
   one configuration. `physical --scans <dir>/<scan>/<View>.jpg --counts counts.csv`
   runs whole scans through the real fusion against counted bunches.
4. **Retrain** on CPU: `python scripts/train_finger_model.py --data <prepared or merged
   negatives> --weights W [--epochs 30 --time HOURS]`, `--resume <last.pt>` to continue
   (refused for a finished run), `--dry-run` to check first. Hue augmentation is off
   (ripeness is colour). Runs go to `backend/runs/` (git-ignored). It prints the new
   weights' SHA-256 and the evaluation command; register the checkpoint in
   `TOP_CALIBRATED_CHECKPOINTS` only after evaluating it.

## Out-of-distribution (OOD) rejection

### Why it was needed

- Stage 2 is closed-set: every box is one of twelve Lakatan/Latundan/Cardaba labels, so
  an unrelated object can only be reported as a supported cultivar. Its training export
  had no background images.
- Before 2026-11-13 the scan passed when any one camera saw a banana, and Stage 2 then
  ran on all four views. Any cultivar box in any view voted and counted as a finger.
- The verifier failed open: if it could not run, every scan went straight to Stage 2.

### What the gate does (`backend/app/services/ood_gate.py`)

1. **Scan gate.** `OOD_MIN_BANANA_VIEWS` views (default 1) must show a banana at
   `OOD_BANANA_CONFIDENCE` (0.30). Otherwise the scan is rejected before Stage 2. Only
   captured frames count, so a camera without a frame lowers the requirement; the fusion
   engine flags such a scan for review as a missing capture.
2. **Box support.** A cultivar box is kept only when banana evidence at
   `OOD_SUPPORT_CONFIDENCE` (0.05), grown by `OOD_SUPPORT_MARGIN` (25 % per side), covers
   its centre in the same frame. An unsupported box is treated as if the model had
   never emitted it: it is skipped in the first pass, the rotated Top pass and the
   occluded-finger recovery pass before any rule that compares it with other boxes
   (duplicates, sub-boxes, clusters, orientation). Only filters that judge a box on its
   own run first (Rear table lip and upper background; in the recovery pass also the
   minimum size and the primary label), and a box they drop is not counted as a gate
   change. The result is exactly
   what the classifier reports for the remaining boxes. Tests pin that contract on
   300 random frames.
3. **No silent change.** If any box was dropped, the saved scan is flagged for review.
   If no supported cultivar remains, the scan is rejected and nothing is stored.
4. **Fail closed.** A verifier that cannot run refuses the scan (HTTP 503).
   `OOD_GATE_FAIL_OPEN=true` restores the earlier pass-through.

`OOD_BOX_SUPPORT_FILTER=false` disables step 2 only.

### Contract

- HTTP 422 from `POST /api/v1/scans/trigger`: `detail` (string, unchanged type) plus
  `code: "ood_rejected"`, `status: "rejected"`, `is_ood: true`,
  `reason: "no_banana" | "no_target_cultivar"`.
- `scan:failed` WebSocket event: `error` plus the same four fields.
- Activity log action `scan_rejected` records the reason and per-view banana scores.
  Captures of a rejected scan are removed, as for any failed scan. A saved scan that
  lost boxes says so in its `scan_created` detail.
- Faults are not rejections: `ood_gate_unavailable` (verifier cannot run) and
  `capture_unavailable` (no camera frame) answer HTTP 503 with `is_ood: false` and
  write no `scan_rejected` row.
- Kiosk state: see [[Frontend]].

### Open-source data (Open Images V7; images CC BY 2.0, annotations CC BY 4.0)

`backend/scripts/prepare_ood_dataset.py` builds and downloads three disjoint pools. The
pinned manifest is `backend/scripts/ood/open_images_ood_manifest.json`; images are never
committed.

| Pool | Source split | Images | Use |
| --- | --- | --- | --- |
| `train_negatives` | validation | 998 | Background images for retraining |
| `calibration` | validation (+ train bananas) | 1284 | Choosing gate thresholds |
| `benchmark` | test (+ train bananas) | 1654 | Held-out evaluation only |

- **Near-OOD** (24 classes): lemon, mango, orange, apple, pear, squash, zucchini,
  cucumber, bell pepper, carrot, hot dog, croissant, cheese and similar.
- **Far-OOD** (24 classes): person, hand, face, car, chair, table, laptop, phone, book,
  bottle, building, tree, dog, cat, poster, box and similar.
- **Banana**: generic banana photos, a proxy positive for the verifier only.
- Leakage guards: every pool is disjoint by image ID and by file hash. Benchmark
  negatives also come from a different official split (test) than training and
  calibration negatives (validation). Banana positives of calibration and benchmark
  share the train split and are separated by image ID and file hash only.
- One training negative showed an unlabeled banana bunch and is excluded by name
  (`EXCLUDED_TRAIN_NEGATIVES`). Re-inspect high-scoring negatives after any rebuild.

### Measured results (held-out benchmark)

Full report: `docs/audits/ood-gate-evaluation-2026-11-13.json`.

| Measure | Near-OOD | Far-OOD |
| --- | --- | --- |
| Frames | 670 | 708 |
| Frame rejection, earlier rule | 96.72 % | 99.86 % |
| Frame rejection, with box support | 97.31 % | 100 % |
| Object boxes that still pass box support | 7.3 % (116/1588) | 0.16 % (2/1215) |
| AUROC, banana vs group | 0.971 | 0.981 |
| FPR at 95 % TPR | 5.52 % | 0.28 % |

- Generic banana frames accepted at 0.30: 90.07 % (245/272). Annotated banana boxes
  kept by box support: 94.92 % (542/571).
- Banana vs all OOD: AUROC 0.976, AUPR 0.936, FPR at 95 % TPR 2.83 % (threshold 0.149).
- Simulated scan with one banana view and three unrelated views: OOD object boxes
  admitted fell from 11 069 to 475 (95.7 % removed).
- Simulated scan with four unrelated views: 6.55 % passed the scan gate; 5.35 % still
  held a supported OOD box. The any-camera rule compounds single-frame errors, and box
  support alone does not fix a lookalike that fools the verifier.

### Stage 2 on the benchmark (laptop run, 2026-11-13)

`evaluate_ood_gate.py pipeline` on a team laptop, default policy, confidence 0.50, each
OOD image scored as a one-camera Top scan. Report:
`docs/audits/ood-pipeline-ood-pool-2026-11-13.json`; the counts follow from its rates.
The manifest's benchmark pool lists 672 near-OOD and 710 far-OOD images. Downloads that
failed were skipped: 2 near and 3 far on the laptop (670 and 707 here), 2 near and 2 far
on the machine of the held-out benchmark above (670 and 708).

| OOD images that end with a cultivar | No gate | Earlier gate | OOD gate |
| --- | --- | --- | --- |
| Near-OOD (670 images) | 76.42 % (512) | 3.28 % (22) | 2.99 % (20) |
| Far-OOD (707 images) | 61.24 % (433) | 0.14 % (1) | 0.00 % (0) |
| Both (1 377 images) | 68.63 % (945) | 1.67 % (23) | 1.45 % (20) |

- This confirms the root cause: with no gate, Stage 2 names a cultivar on most
  non-banana photos.
- The banana verifier does almost all of the rejection. Box support removes 3 more
  images; the 20 remaining near-OOD images pass the verifier as bananas.
- Weights: `banana_yolo26s.pt` (20,341,509 bytes, SHA-256 starting `d1acd351`). It is
  not in `TOP_CALIBRATED_CHECKPOINTS`, so `top_paths.active` was false and the Top
  refinement, rotated pass and finger recovery did not run.
- No labeled split was given, so the effect on real bananas is not part of this run.

### Real bananas through the gate (laptop run, 2026-11-13)

Same script with `--id-split` on the test split of the Roboflow export
`Banana_Ripeness.v17i.yolo26`: 416 photos with one labeled cultivar (Cardaba 134,
Lakatan 155, Latundan 127) in 337 scans. Weights: `best.pt` of training run
`v26s_run2_zick` (SHA-256 starting `fe9359d5`). Report:
`docs/audits/ood-pipeline-labeled-split-2026-11-13.json`.

| Real banana photos | No gate | Earlier gate | OOD gate |
| --- | --- | --- | --- |
| End with a cultivar | 416/416 (100 %) | 409/416 (98.32 %) | 408/416 (98.08 %) |
| Finger boxes | 3 534 | 3 467 | 3 453 |
| Wrong cultivar | 0 | 0 | 0 |
| Cardaba with a cultivar | 134/134 | 130/134 | 129/134 |
| Lakatan with a cultivar | 155/155 | 153/155 | 153/155 |
| Latundan with a cultivar | 127/127 | 126/127 | 126/127 |

| Rear view only (95 photos) | No gate | Earlier gate | OOD gate |
| --- | --- | --- | --- |
| End with a cultivar | 95/95 | 92/95 | 91/95 |
| Finger boxes | 973 | 939 | 925 |

- **Per cultivar:** precision stays 1.0 for all three. Cardaba carries most of the loss
  (5 of the 8 photos without a cultivar; 4 of 7 under the earlier gate). The gate never
  reads the cultivar label; the difference comes from the verifier's banana scores on
  those photos. Green or atypical Cardaba hands on the station have not been measured.
- **Scan gate:** 330 of 337 scans accepted. The 7 rejected scans hold one photo each,
  and the earlier gate rejects them too, because both use the same verifier rule.
- **Cost of the OOD gate over the earlier gate:** 1 more photo without a cultivar
  (a Cardaba) and 14 fewer finger boxes (0.40 %), all in the Rear view. The totals for
  Top, Left and Right are identical in both.
- **The verifier is weakest on Rear photos.** Below acceptance (0.30): Top 0/99,
  Left 2/94, Right 2/128, Rear 6/95. The 3 such frames inside an accepted scan are all
  Rear frames. The report does not say which Rear photos lost boxes.
- **Limits of this run:** this checkpoint is not in `TOP_CALIBRATED_CHECKPOINTS` either
  (`top_paths.active` false). The test photos may overlap its training data, so the
  perfect no-gate score may read high. The scan-gate decisions come from the verifier
  alone and are unaffected by that; the box-level differences (photos without a
  cultivar, finger boxes) are measured on this checkpoint's boxes and may differ on
  unseen photos. Most scans are a single photo, and fusion is not simulated. The report
  does not count flagged scans: at least one accepted scan lost boxes (one Rear photo
  lost all of them). If that photo were the only view of its scan, the station would
  reject the scan instead of flagging it; the report cannot tell. The finger-box
  figures are totals, so they show the net change only.
- **Against the criteria set before the run: not met.** They asked that recall and
  `finger_boxes` do not drop and that `scans_accepted` equals `scans`. Measured: 330 of
  337 scans accepted (the earlier gate rejects the same 7), one more photo without a
  cultivar, 14 fewer finger boxes.
- **Decision:** no code or threshold change, because the extra cost is small, limited
  to the Rear totals, and thresholds are not tuned on a test split. Whether that cost
  is acceptable on the station is the team's call.

### Limits

- **Not measured:** any result on a registered Top-calibrated checkpoint, how many real
  scans the gate would flag for review, and four-camera fusion.
  For the first, run `evaluate_ood_gate.py pipeline` with the
  weights the station runs (`YOLO_MODEL_PATH`) at confidence 0.50; the report's
  `top_paths.active` must be true, or the Top refinement, rotated pass and finger
  recovery did not run. It groups the prepared files of one capture into a scan, applies
  the scan gate over its views, classifies each view with its own camera label and
  evidence, and reports each view. Fusion across views is not simulated, and dataset
  photos are still not station captures.
- **Unsupported banana cultivars pass.** COCO "banana" covers every variety, and Stage 2
  has no "other banana" class. Rejecting them needs labeled examples and retraining.
- **Strong lookalikes pass the verifier:** yellow watermelon slices 0.90, mango slice
  0.89, yellow squash 0.84. Their own evidence then supports their boxes. The fix is
  retraining Stage 2 with the hard negatives.
- **Weak on unusual bananas:** peeled or sliced fruit and green bunches on the plant
  scored 0.09 to 0.21. Unripe hands on the station have not been measured.
- Thresholds were calibrated on open-source photos, not station captures.
- The gate adds one verifier inference per camera view (about 65 ms each on a 4-core
  CPU here); the earlier code stopped at the first view that showed a banana.

### Retraining with negatives (not run yet)

```bash
python scripts/prepare_ood_dataset.py merge-negatives \
    --dataset <prepared dataset> --ood ood-data --output <new directory> --ratio 0.10
```

The copy gains background images with empty label files in `train` only; Ultralytics
8.4.40 counts an empty label file as a background image. Validation and test splits stay
byte-identical, so before/after detector metrics remain comparable. After training,
recalibrate `TOP_CALIBRATED_CHECKPOINTS` for the new checkpoint hash and repeat both
evaluation modes.
