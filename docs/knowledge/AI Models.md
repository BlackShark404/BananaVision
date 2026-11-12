# AI Models

Verified against the source on 2026-11-13. Related: [[Frontend]], [[Testing and Validation]],
[[Development Decisions]].

## Scan pipeline

| Stage | File | Model | Role |
| --- | --- | --- | --- |
| 1. Banana verifier | `backend/app/services/banana_detector.py` | COCO `yolo26n.pt`, class 46 | Is a banana in the frame, and where |
| 2. Cultivar detector | `backend/app/services/classification.py` | Trained 12-class YOLO (`cultivar_ripeness`) | Finger boxes with cultivar and ripeness |
| 3. Fusion | `backend/app/services/fusion_engine.py` | Rules | One result from up to four camera views |
| 4. Shelf life | `backend/app/services/spoilage.py` | Random forest | Estimated days |

`backend/app/services/scan_service.py` runs the stages. The trained cultivar weights
(`backend/app/ml/weights/*.pt`) and their dataset are not in the repository.

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
   `OOD_BANANA_CONFIDENCE` (0.30). Otherwise the scan is rejected before Stage 2.
2. **Box support.** A cultivar box is kept only when banana evidence at
   `OOD_SUPPORT_CONFIDENCE` (0.05), grown by `OOD_SUPPORT_MARGIN` (25 % per side), covers
   its centre in the same frame. An unsupported box is treated as if the model had
   never emitted it: it is skipped in the first pass, the rotated Top pass and the
   occluded-finger recovery pass before any other rule sees it. The result is exactly
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

| Rear view only (95 photos) | No gate | Earlier gate | OOD gate |
| --- | --- | --- | --- |
| End with a cultivar | 95/95 | 92/95 | 91/95 |
| Finger boxes | 973 | 939 | 925 |

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
  perfect no-gate score may read high; the gate comparison is unaffected. Most scans
  are a single photo, and fusion is not simulated. The report does not count flagged
  scans: at least one accepted scan lost boxes (one Rear photo lost all of them). The
  finger-box figures are totals, so they show the net change only.
- **Decision:** no code or threshold change. Thresholds are not tuned on a test split.

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
