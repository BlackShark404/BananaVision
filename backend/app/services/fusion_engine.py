"""
Multi-camera fusion engine.

Merges YOLO detections from 4 cameras into a single authoritative
classification using confidence-weighted majority voting.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings
from app.services.classification import (
    TOP_OVERLAP_CONFIDENCE,
    VOTE_CONFLICT_THRESHOLD,
    ClassificationResult,
    Detection,
    _unique_box_detections,
)

logger = logging.getLogger(__name__)


@dataclass
class CameraDetection:
    """A single camera's classification result."""
    camera_id: str
    camera_label: str
    cultivar: str | None
    ripeness: str | None
    confidence: float
    finger_count: int
    detections_count: int


@dataclass(frozen=True)
class Observation:
    """Something fusion noticed about the views: a stable code and a plain sentence.

    Observations are recorded with the scan's activity entry. They never flag a scan: the
    only auto-flag rule is a confidence below the saved review threshold.
    """
    code: str
    text: str


NO_LABEL = "no_label"
CULTIVAR_CONFLICT = "cultivar_conflict"
RIPENESS_CONFLICT = "ripeness_conflict"
WEAK_PAIR_SUPPORT = "weak_pair_support"
VIEW_CONFLICT = "view_conflict"
INSUFFICIENT_VIEWS = "insufficient_views"
MISSING_CAPTURES = "missing_captures"
COUNT_VIEWS_DIFFER = "count_views_differ"


def _percent(value: float) -> str:
    return f"{value:g}"


def _below_threshold(confidence: float, threshold_percent: float) -> str:
    return (
        f"Confidence {_percent(confidence)}% is below the "
        f"{_percent(threshold_percent)}% threshold"
    )


def _cameras(labels: list[str]) -> str:
    """'Left camera's', 'Top and Rear cameras'' for a sentence about those views."""
    names = [label or "unnamed" for label in labels]
    if len(names) == 1:
        return f"{names[0]} camera's"
    return f"{', '.join(names[:-1])} and {names[-1]} cameras'"


@dataclass
class FusedResult:
    """Merged classification from all cameras."""
    cultivar: str
    ripeness: str
    confidence: float
    finger_count: int
    camera_count: int
    conflict_detected: bool = False
    auto_flagged: bool = False
    cultivar_conflict: bool = False
    per_camera: list[CameraDetection] = field(default_factory=list)
    # Set exactly when auto_flagged is true: the confidence is below the review threshold.
    flag_reason: str | None = None
    # What else fusion noticed (camera disagreements, missing views, different counts).
    # Recorded for the activity log; never a reason to flag.
    observations: list[Observation] = field(default_factory=list)


class FusionEngine:
    """
    Confidence-Weighted Majority Voting fusion for multi-camera detections.

    Strategy:
        1. Weight each complete camera classification by detection confidence
        2. Select cultivar with the highest total weight
        3. Select ripeness only from cameras supporting that cultivar
        4. Estimate finger count from available camera views
        5. Final confidence = mean confidence of the winning observed pair
        6. Auto-flag only a confidence below the review threshold. Conflicts, no
           cultivar camera majority, missing captures, insufficient supporting views and
           different finger counts between views are reported as observations.
    """

    CONFLICT_THRESHOLD = VOTE_CONFLICT_THRESHOLD
    MIN_CONFIDENCE = 0.50  # Minimum final confidence before review is required

    def fuse(
        self, results: list[tuple[str, str, ClassificationResult]], *,
        expected_camera_count: int | None = None,
        review_confidence_threshold: float = MIN_CONFIDENCE,
    ) -> FusedResult:
        """
        Merge classification results from multiple cameras.

        Args:
            results: List of (camera_id, camera_label, ClassificationResult) tuples
            expected_camera_count: Configured camera count from the scan snapshot.
            review_confidence_threshold: Minimum final confidence in (0, 1].

        Returns:
            FusedResult with final classification
        """
        if not 0 < review_confidence_threshold <= 1:
            raise ValueError("Review confidence threshold must be in (0, 1]")

        if not results:
            return FusedResult(
                cultivar="Unknown",
                ripeness="Unknown",
                confidence=0.0,
                finger_count=0,
                camera_count=0,
                auto_flagged=True,
                flag_reason=_below_threshold(0.0, review_confidence_threshold * 100),
                observations=[Observation(MISSING_CAPTURES, "No camera returned a result")],
            )

        cultivar_weights: dict[str, float] = {}
        cultivar_view_counts: dict[str, int] = {}
        pair_confs: dict[tuple[str, str], list[float]] = {}
        pair_cameras: dict[tuple[str, str], set[str]] = {}
        finger_counts: list[int] = []
        per_camera: list[CameraDetection] = []
        seen_cameras: set[str] = set()
        per_view_conflict = False
        conflicted_views: list[str] = []

        top_camera_result: ClassificationResult | None = None
        for camera_id, camera_label, result in results:
            # A repeated view must not count as independent camera evidence.
            if camera_id in seen_cameras:
                continue
            seen_cameras.add(camera_id)
            if (camera_label or "").strip().casefold() == "top" and top_camera_result is None:
                top_camera_result = result
            cam_det = CameraDetection(
                camera_id=camera_id,
                camera_label=camera_label,
                cultivar=result.cultivar,
                ripeness=result.ripeness,
                confidence=result.confidence,
                finger_count=result.finger_count,
                detections_count=len(result.detections),
            )
            per_camera.append(cam_det)

            finger_counts.append(result.finger_count)
            # Partial/invalid classifications cannot establish a complete label.
            if not (
                result.cultivar and result.ripeness
                and math.isfinite(result.confidence) and 0 < result.confidence <= 100
            ):
                continue
            conf = result.confidence / 100.0
            cultivar_weights[result.cultivar] = (
                cultivar_weights.get(result.cultivar, 0) + conf
            )
            cultivar_view_counts[result.cultivar] = (
                cultivar_view_counts.get(result.cultivar, 0) + 1
            )
            pair = (result.cultivar, result.ripeness)
            pair_confs.setdefault(pair, []).append(result.confidence)
            pair_cameras.setdefault(pair, set()).add(camera_id)
            view_has_cultivar_conflict = (
                result.cultivar_conflict
                if hasattr(result, "cultivar_conflict")
                else result.conflict_detected
            )
            per_view_conflict = per_view_conflict or view_has_cultivar_conflict
            # Keep stage/duplicate review signals without making the cultivar uncertain.
            per_view_conflict = per_view_conflict or result.conflict_detected
            if view_has_cultivar_conflict or result.conflict_detected:
                conflicted_views.append((camera_label or camera_id or "").strip())

        # Check for authoritative Top view anchor:
        # Top camera is mounted overhead looking directly down at the flat inspection
        # platter without perspective foreshortening or cluttered room background.
        settings = get_settings()
        anchor_top = getattr(settings, "top_camera_cultivar_anchor", True)
        top_anchor_eligible = (
            anchor_top
            and top_camera_result is not None
            and top_camera_result.cultivar
            and top_camera_result.cultivar != "Unknown"
            and math.isfinite(top_camera_result.confidence)
            and top_camera_result.confidence >= 50.0
            and top_camera_result.finger_count >= 1
            and not getattr(top_camera_result, "cultivar_conflict", False)
        )

        if top_anchor_eligible and top_camera_result is not None:
            best_cultivar = top_camera_result.cultivar
        else:
            best_cultivar = self._select_winner(cultivar_weights) or "Unknown"

        ripeness_weights = {
            ripeness: sum(confs) / 100.0
            for (cultivar, ripeness), confs in pair_confs.items()
            if cultivar == best_cultivar
        }
        best_ripeness = self._select_winner(ripeness_weights) or "Unknown"

        # Check for conflicts
        total_valid_views = sum(cultivar_view_counts.values())
        winning_views = cultivar_view_counts.get(best_cultivar, 0)

        # When Top anchor is active:
        # A split among peripheral cameras does not invalidate the overhead anchor,
        # unless a competing cultivar has a strict camera majority (> 50% of valid views).
        # However, if the overhead Top view detects a multi-finger hand (>= 4 fingers)
        # with strictly higher confidence than the competing peripheral cultivar's
        # average confidence (where side views only see foreshortened tips), the
        # overhead morphology anchor prevails.
        has_competing_majority = any(
            count * 2 > total_valid_views
            and not (
                top_camera_result is not None
                and top_camera_result.finger_count >= 4
                and (top_camera_result.confidence / 100.0) > (cultivar_weights.get(cult, 0.0) / count)
            )
            for cult, count in cultivar_view_counts.items()
            if cult != best_cultivar
        )
        if top_anchor_eligible:
            no_camera_majority = has_competing_majority
            cultivar_conflict = has_competing_majority
        else:
            # A high score cannot turn a split of independent camera labels into
            # cultivar agreement. Keep the weighted candidate and its raw score,
            # but require review when it lacks a strict majority of valid views.
            no_camera_majority = (
                len(cultivar_view_counts) > 1
                and winning_views * 2 <= total_valid_views
            )
            cultivar_conflict = (
                self._has_conflict(cultivar_weights, best_cultivar) or no_camera_majority
            )

        ripeness_conflict = self._has_conflict(ripeness_weights, best_ripeness)
        conflict_detected = cultivar_conflict or ripeness_conflict or per_view_conflict

        # Confidence describes the observed pair, not two unrelated marginal votes.
        winning_pair = (best_cultivar, best_ripeness)
        winning_confs = pair_confs.get(winning_pair, [])
        if top_anchor_eligible:
            cultivar_total = cultivar_weights.get(best_cultivar, 0.0)
            pair_conflict = (
                cultivar_total > 0
                and sum(winning_confs) / 100.0 < cultivar_total * self.CONFLICT_THRESHOLD
            )
        else:
            pair_conflict = (
                sum(winning_confs) / 100.0
                < sum(cultivar_weights.values()) * self.CONFLICT_THRESHOLD
            )
        conflict_detected = conflict_detected or pair_conflict

        final_confidence = (
            round(sum(winning_confs) / len(winning_confs), 1) if winning_confs else 0.0
        )

        # Estimate total hand fingers across views using 2D vertical tier separation
        # when a two-tier hand's lower row is occluded from the overhead Top camera.
        baseline_max_fingers = max(finger_counts, default=0)
        final_fingers = self._estimate_multi_camera_fingers(results, finger_counts)

        expected = expected_camera_count if expected_camera_count is not None else len(per_camera)
        supporting_views = len(pair_cameras.get(winning_pair, set()))
        insufficient_views = supporting_views < min(2, expected)
        missing_captures = len(per_camera) < expected
        # Each camera sees a different part of the hand, so different positive counts (or
        # lower-tier fingers added by multi-view fusion) are normal; the count is shown as
        # an estimate.
        count_views_differ = (
            len({count for count in finger_counts if count > 0}) > 1
            or final_fingers > baseline_max_fingers
        )

        # The one auto-flag rule: confidence below the saved review threshold. A result
        # without a label has confidence 0, so it is below any threshold.
        threshold_percent = review_confidence_threshold * 100
        auto_flagged = final_confidence < threshold_percent
        flag_reason = (
            _below_threshold(final_confidence, threshold_percent) if auto_flagged else None
        )

        # Everything else is an observation for the activity log, not a flag.
        observations: list[Observation] = []
        labelled = best_cultivar != "Unknown" and best_ripeness != "Unknown"
        if not labelled:
            observations.append(Observation(
                NO_LABEL, "No camera produced a complete cultivar and ripeness label",
            ))
        if labelled and cultivar_conflict:
            observations.append(Observation(CULTIVAR_CONFLICT, "Cameras disagree on the cultivar"))
        if labelled and ripeness_conflict:
            observations.append(Observation(RIPENESS_CONFLICT, "Cameras disagree on the ripeness"))
        if labelled and pair_conflict and not (cultivar_conflict or ripeness_conflict):
            observations.append(Observation(
                WEAK_PAIR_SUPPORT,
                f"Less than {self.CONFLICT_THRESHOLD:.0%} of the camera evidence supports "
                "this cultivar and ripeness",
            ))
        if conflicted_views:
            observations.append(Observation(
                VIEW_CONFLICT,
                f"The {_cameras(conflicted_views)} own boxes disagree or overlap",
            ))
        if insufficient_views:
            observations.append(Observation(
                INSUFFICIENT_VIEWS,
                f"Only {supporting_views} camera{'' if supporting_views == 1 else 's'} "
                f"support{'s' if supporting_views == 1 else ''} the result",
            ))
        if missing_captures:
            observations.append(Observation(
                MISSING_CAPTURES,
                f"Only {len(per_camera)} of {expected} cameras returned a result",
            ))
        if count_views_differ:
            observations.append(Observation(
                COUNT_VIEWS_DIFFER, "Cameras report different finger counts",
            ))

        if auto_flagged:
            logger.warning(
                f"Fusion auto-flagged: cultivar={best_cultivar}, ripeness={best_ripeness}, "
                f"conf={final_confidence}%, conflict={conflict_detected}, "
                f"no_camera_majority={no_camera_majority}, "
                f"supporting_views={supporting_views}, captured={len(per_camera)}/{expected}, "
                f"threshold={_percent(threshold_percent)}%"
            )

        return FusedResult(
            cultivar=best_cultivar,
            ripeness=best_ripeness,
            confidence=final_confidence,
            finger_count=final_fingers,
            camera_count=len(per_camera),
            conflict_detected=conflict_detected,
            auto_flagged=auto_flagged,
            cultivar_conflict=cultivar_conflict,
            per_camera=per_camera,
            flag_reason=flag_reason,
            observations=observations,
        )

    def _select_winner(self, weights: dict[str, float]) -> str | None:
        if not weights:
            return None
        return max(weights, key=weights.get)  # type: ignore[arg-type]

    def _has_conflict(self, weights: dict[str, float], winner: str) -> bool:
        total = sum(weights.values())
        if total == 0:
            return True
        winner_ratio = weights.get(winner, 0) / total
        return winner_ratio < self.CONFLICT_THRESHOLD

    def _estimate_multi_camera_fingers(
        self,
        results: list[tuple[str, str, ClassificationResult]],
        finger_counts: list[int],
    ) -> int:
        baseline_max = max(finger_counts, default=0)
        if len(finger_counts) < 4 or baseline_max <= 0:
            return baseline_max

        by_label: dict[str, ClassificationResult] = {}
        seen_ids: set[str] = set()
        for camera_id, camera_label, result in results:
            if camera_id in seen_ids:
                continue
            seen_ids.add(camera_id)
            norm = (camera_label or "").strip().casefold()
            if norm in ("top", "left", "right", "rear") and norm not in by_label:
                by_label[norm] = result

        if len(by_label) < 4:
            return baseline_max

        t_res = by_label["top"]
        l_res = by_label["left"]
        r_res = by_label["right"]
        re_res = by_label["rear"]

        t_cnt = t_res.finger_count
        l_cnt = l_res.finger_count
        r_cnt = r_res.finger_count
        re_cnt = re_res.finger_count

        l_upper, l_lower = _split_horizontal_tiers(l_res.detections)
        r_upper, r_lower = _split_horizontal_tiers(r_res.detections)
        re_upper, re_lower = _split_horizontal_tiers(re_res.detections)

        top_second_tier = _count_top_second_tier(t_res.detections)
        u_primary = max(1, t_cnt - top_second_tier)

        # If Rear suffered a severe single-frame capture/detection collapse while both
        # lateral views independently observe two stacked vertical tiers, reconstruct
        # conservatively from Top's primary row plus the smaller observed lower tier.
        if re_cnt <= 4:
            if l_cnt >= 8 and r_cnt >= 8 and min(l_lower, r_lower) >= 3:
                fused_estimate = u_primary + min(l_lower, r_lower)
                return max(baseline_max, min(sum(finger_counts), fused_estimate))
            return baseline_max

        # When Rear partially under-detects (< 8 or < max(Left, Right)), still recover
        # the stacked lower tier if both Left and Right confirm two-tier stacking.
        if re_cnt < 8 or re_cnt < max(l_cnt, r_cnt):
            if (
                min(l_cnt, r_cnt) >= 7
                and max(l_cnt, r_cnt) >= 8
                and min(l_lower, r_lower) >= 3
            ):
                side_lower = (
                    sorted([l_lower, r_lower, re_lower])[1]
                    if re_lower >= 2
                    else min(l_lower, r_lower)
                )
                fused_estimate = u_primary + side_lower
                return max(baseline_max, min(sum(finger_counts), fused_estimate))
            return baseline_max

        # If one side view collapses (<= 4 boxes) while the surviving side (>= 7) and Rear
        # (>= 8) both confirm vertical stacking, recover from the surviving pair.
        if min(l_cnt, r_cnt) <= 4:
            surv_lower = max(l_lower, r_lower)
            if max(l_cnt, r_cnt) >= 7 and min(surv_lower, re_lower) >= 3:
                u_est = u_primary + (1 if re_cnt > t_cnt else 0)
                fused_estimate = u_est + min(surv_lower, re_lower)
                return max(baseline_max, min(sum(finger_counts), fused_estimate))
            return baseline_max

        # Require verified 2D vertical tier stacking across at least two horizontal views.
        if sum(1 for low in (l_lower, r_lower, re_lower) if low >= 2) < 2:
            return baseline_max

        u_est = u_primary + (1 if re_cnt > t_cnt else 0)
        wide_bilateral = (
            re_cnt >= 12
            and re_cnt >= u_primary + 2
            and max(l_cnt, r_cnt) >= 8
            and min(l_cnt, r_cnt) >= 7
            and min(l_lower, r_lower) >= 3
            and max(l_lower, r_lower) >= 4
            and re_lower >= max(l_lower, r_lower)
        )
        if wide_bilateral:
            # Wide curved two-tier hands foreshorten or tuck inner upper fingers in Top
            # while Left and Right capture opposite lateral wings around Rear's center arc.
            side_upper_union = min(l_upper + r_upper, re_upper + min(l_upper, r_upper))
            u_est = max(u_est, side_upper_union)

        if (
            (re_cnt >= 12 and re_lower > max(l_lower, r_lower) and top_second_tier == 0)
            or (
                re_cnt < 12
                and re_lower >= max(l_lower, r_lower) + 2
                and top_second_tier == 0
            )
            or wide_bilateral
        ):
            # Left and Right capture opposite lateral halves of the lower tier while
            # Rear spans the central overlap.
            l_est = min(l_lower + r_lower, re_lower + min(l_lower, r_lower))
        elif (
            re_cnt <= 10
            and re_cnt <= t_cnt
            and re_lower > max(l_lower, r_lower)
            and top_second_tier == 0
        ):
            # Compact Rear view did not add an upper finger beyond Top, yet directly sees
            # more lower-tier fingers than either side view alone.
            l_est = min(l_lower + r_lower, re_lower)
        else:
            # Standard two-tier hand: Left, Right, and Rear observe the shared lower tier.
            l_est = sorted([l_lower, r_lower, re_lower])[1]

        fused_estimate = u_est + l_est
        return max(baseline_max, min(sum(finger_counts), fused_estimate))


def _split_horizontal_tiers(dets: list[Detection]) -> tuple[int, int]:
    """Split unique detections in a horizontal view (Left/Right/Rear) into (upper_count, lower_count).

    A box belongs to the lower tier when another accepted box sits vertically above it
    with meaningful horizontal overlap along the hand span.
    """
    unique = _unique_box_detections(dets)
    if len(unique) < 2:
        return len(unique), 0
    lower_count = 0
    for b in unique:
        cy_b = b.y + b.h / 2
        has_upper = False
        for u in unique:
            if u is b:
                continue
            cy_u = u.y + u.h / 2
            if (cy_b - cy_u) >= 0.35 * min(u.h, b.h):
                ix1 = max(u.x, b.x)
                ix2 = min(u.x + u.w, b.x + b.w)
                inter_w = max(0.0, ix2 - ix1)
                if inter_w >= 0.20 * min(u.w, b.w):
                    has_upper = True
                    break
        if has_upper:
            lower_count += 1
    return len(unique) - lower_count, lower_count


def _count_top_second_tier(dets: list[Detection]) -> int:
    """Count lower-tier fingers already visible around the perimeter of the overhead Top view."""
    unique = _unique_box_detections(dets)
    if len(unique) < 4:
        return 0
    areas = [d.w * d.h for d in unique if d.w > 0 and d.h > 0]
    if not areas:
        return 0
    med_area = float(np.median(areas))
    # Only Pass-2 low-confidence recoveries (vertical overlaps) or genuinely small peeking
    # inner/perimeter tips belong to the second tier; splayed radial upper wings (w > h)
    # stay in the primary row.
    return sum(
        1
        for d in unique
        if (d.confidence < TOP_OVERLAP_CONFIDENCE and d.w <= d.h)
        or (d.w * d.h) < 0.42 * med_area
    )


# Singleton instance
fusion_engine = FusionEngine()
