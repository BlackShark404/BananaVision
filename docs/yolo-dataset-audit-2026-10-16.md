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
before considering replacement. The user subsequently confirmed that v13 has
not been trained yet and explicitly requested training YOLOv8 on this export.
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

## Counting semantics and next data needed

`classification.py` counts retained YOLO boxes per image. `fusion_engine.py`
selects the maximum per-camera count, and the API/UI preserve that number.
There is no cross-camera correspondence for individual physical fingers.
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
