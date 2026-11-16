# BananaVision: remaining bounding-box and finger-count errors

Analyze and fix the remaining banana detection and counting errors in this repository. Inspect the images in `debug-screenshots/2026-11-15/` and trace the current implementation before editing. Follow `AGENTS.md`, read the latest resume point in `TASK_PROGRESS.txt`, and preserve the recent counting improvements.

## Problem

Recent changes improved counting, and some scans now match the physical count exactly. However, I still observe overcounts of about 2 bananas and undercounts of about 2–3, especially with Lakatan. Some visible bananas receive no individual box, some boxes poorly isolate individual fingers, and some detections identify the platform or surrounding background. Latundan and Cardaba generally look better to me, but the screenshots show remaining failures there too.

The goal is to count distinct physical banana fingers accurately while rejecting non-banana objects. Preserve cases that already work. Do not force agreement by changing only the displayed number or hiding bad boxes.

## Screenshot evidence

These are displayed estimates and per-camera counts, not independently verified physical counts. Camera order below is Top / Left / Right / Rear.

| Sample | Camera counts | Modal header total | Final estimate shown |
| --- | --- | --- | --- |
| Latundan Unripe, images 01–05 | 11 / 9 / 10 / 11 | 41 | 15 |
| Latundan Ripe, images 06–09 | 11 / 8 / 8 / 9 | 36 | Not supplied |
| Lakatan Unripe, images 10–13 | 10 / 8 / 9 / 11 | 38 | 22 |
| Lakatan Ripe, images 14–18 | 11 / 8 / 7 / 12 | 38 | 14 |
| Cardaba Unripe, images 19–22 | 14 / 9 / 8 / 4 | 35 | Not supplied |
| Cardaba Ripe, images 23–26 | 11 / 8 / 8 / 10 | 37 | Not supplied |

The modal total adds counts across overlapping camera views. It is not the number of unique physical bananas. A per-camera count can also legitimately be lower because fingers are occluded.

Inspect these examples closely:

- `03-latundan-unripe-left.png`: a 38% “Latundan Ripe” box covers the upper-right doorway/panel, detached from the fruit. Investigate this background detection.
- `06-latundan-ripe-top.png`, `14-lakatan-ripe-top.png`, and `23-cardaba-ripe-top.png`: suspicious lower-left boxes cover substantial beige platform/front trim or wood, sometimes with partial fruit overlap. Establish whether each box represents a real partial finger, a duplicate fragment, or background. Some background inside an axis-aligned banana box is normal.
- `17-lakatan-ripe-right.png`: several visible lower-right banana bodies/tips lack individual boxes. Fruit also extends beyond the upper and left frame boundaries. Separate visible missed fingers from fruit that the camera cannot see.
- `11-lakatan-unripe-top.png`, `12-lakatan-unripe-left.png`, and `18-lakatan-ripe-rear.png`: closely packed, curved, diagonal, and overlapping fingers create ambiguous boxes. Determine whether any finger is merged with another or counted twice. Rectangle overlap alone does not prove duplication.
- `22-cardaba-unripe-rear.png`: only four detections appear despite several visible upper/middle fingers remaining unboxed. This is an important additional failure case beyond Lakatan.
- `27-empty-platform-top-reference.png`: the empty Top-view setup shows the wooden background, circular platform, and beige front strip. It has no detection overlay. Use it as a background reference; it does not prove that an empty-platform inference produced false detections. This screenshot is not a calibrated mask for every camera or placement.

## Investigation

First verify which revision, model checkpoint, inference head, and non-secret inference settings produced the screenshots, if that information is available. Do not assume historical screenshots ran the current code. Check source code against documentation; some older notes describe maximum-view counting, while the current fusion code also estimates two-tier hands.

Trace these stages separately:

1. **Detector:** raw YOLO boxes, scores, rotation/recovery passes, NMS, and original-image coordinate transforms. Establish whether missing fingers were ever proposed and whether background boxes originate in the main or recovery pass.
2. **Per-camera processing:** banana-evidence/OOD and colour checks, platter/background rejection, cluster splitting, duplicate suppression, and the final unique finger count. Identify the exact rule that rejects a real finger or accepts a false one.
3. **Multi-camera fusion:** trace upper/lower-tier assignments and contributions to the final estimate. Check whether background boxes or repeated evidence cause overcounting, and whether weak views or tier rules cause undercounting. Do not sum all views or assume the largest view always equals the physical total.
4. **Storage/API/UI:** verify `counts_as_finger`, stored `finger_count`, displayed boxes, camera/image association, and overlay scaling/cropping agree. Determine whether any apparent localization error comes from rendering rather than inference.

Relevant starting points:

- `backend/app/services/classification.py`: `_unique_box_detections`, `_is_cluster_box`, `_is_duplicate_detection`, `_is_platter_lip`, `_is_recovery_duplicate`, and `BananaClassifier.predict`.
- `backend/app/services/fusion_engine.py`: `_estimate_multi_camera_fingers`, `_split_horizontal_tiers`, and `_count_top_second_tier`.
- `backend/app/services/scan_service.py`, `backend/app/schemas/scan.py`, and `frontend/src/types/index.ts`.
- `frontend/src/lib/detectionBoxes.ts`, `frontend/src/components/BoundingBoxOverlay.tsx`, and `frontend/src/pages/Kiosk.tsx`.
- Relevant tests and `docs/knowledge/Resolved Bugs.md` / `docs/knowledge/AI Models.md`.

Use stage-by-stage offline diagnostics where original clean frames and matching metadata exist. Screenshot crops with labels and translucent fills are not equivalent to raw camera frames. Do not train on these overlays or report inference on them as a clean-frame benchmark. Distinguish visual evidence, reproducible code defects, and unresolved hypotheses. If true physical counts are unavailable, identify the precise annotations needed; do not invent them or reuse historical counts without matching the sample.

## Fix and validation requirements

Make the smallest evidence-supported fix and add meaningful regression coverage. Avoid arbitrary +2/−2 corrections, hard-coded expected hand sizes, blanket confidence increases, or aggressive overlap/colour filters. Real fingers may be low-confidence, tightly overlapping, partly visible, edge-clipped, pale, shaded, or brown. Preserve current correct cases across all three cultivars and single/two-tier hands.

Use existing isolated fixtures and offline assets only. Never test against the live station database, captures, or physical cameras. Preserve UI layout, API contracts, Manila-time handling, and the existing estimated-count convention. Stay on `main`; do not stage, commit, push, deploy, or retrain without authorization.

Report:

1. An image-by-image evidence table with filenames, observed defects, and uncertainty.
2. Proven root causes by pipeline stage, with relevant source locations.
3. The scoped fix and why it preserves already-correct cases; distinguish any model/camera limits requiring separate work.
4. Before/after box precision/recall and count error where annotations support them, including exact-count rate, overcounts, and undercounts by cultivar/view. Evaluate empty-background false positives and final multi-camera counts separately.
5. Exact verification results and unavailable evidence. Run relevant backend/frontend tests, type checks, configured lint, and build for implementation changes. Update project knowledge and progress only when justified by verified changes.

If the available evidence cannot establish a safe fix, deliver the proven diagnosis, an offline reproduction/annotation plan, and the exact missing inputs instead of speculative threshold changes or a claim of completion.
