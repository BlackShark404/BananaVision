"""
Multi-camera fusion engine.

Merges YOLO detections from 4 cameras into a single authoritative
classification using confidence-weighted majority voting.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from app.config import get_settings
from app.services.classification import (
    VOTE_CONFLICT_THRESHOLD,
    ClassificationResult,
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
    per_camera: list[CameraDetection] = field(default_factory=list)


class FusionEngine:
    """
    Confidence-Weighted Majority Voting fusion for multi-camera detections.

    Strategy:
        1. Weight each complete camera classification by detection confidence
        2. Select cultivar with the highest total weight
        3. Select ripeness only from cameras supporting that cultivar
        4. Estimate finger count from available camera views
        5. Final confidence = mean confidence of the winning observed pair
        6. Auto-flag conflicts, no cultivar camera majority, missing captures,
           insufficient supporting views, or unverified cross-camera finger additions
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
            )

        cultivar_weights: dict[str, float] = {}
        cultivar_view_counts: dict[str, int] = {}
        pair_confs: dict[tuple[str, str], list[float]] = {}
        pair_cameras: dict[tuple[str, str], set[str]] = {}
        finger_counts: list[int] = []
        per_camera: list[CameraDetection] = []
        seen_cameras: set[str] = set()
        per_view_conflict = False

        for camera_id, camera_label, result in results:
            # A repeated view must not count as independent camera evidence.
            if camera_id in seen_cameras:
                continue
            seen_cameras.add(camera_id)
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
            per_view_conflict = per_view_conflict or result.conflict_detected

        # Keep cultivar consensus without borrowing ripeness from another variety.
        best_cultivar = self._select_winner(cultivar_weights) or "Unknown"
        ripeness_weights = {
            ripeness: sum(confs) / 100.0
            for (cultivar, ripeness), confs in pair_confs.items()
            if cultivar == best_cultivar
        }
        best_ripeness = self._select_winner(ripeness_weights) or "Unknown"

        # Check for conflicts
        # A high score cannot turn a split of independent camera labels into
        # cultivar agreement. Keep the weighted candidate and its raw score,
        # but require review when it lacks a strict majority of valid views.
        no_camera_majority = (
            len(cultivar_view_counts) > 1
            and cultivar_view_counts.get(best_cultivar, 0) * 2
            <= sum(cultivar_view_counts.values())
        )
        cultivar_conflict = (
            self._has_conflict(cultivar_weights, best_cultivar) or no_camera_majority
        )
        ripeness_conflict = self._has_conflict(ripeness_weights, best_ripeness)
        conflict_detected = cultivar_conflict or ripeness_conflict or per_view_conflict

        # Confidence describes the observed pair, not two unrelated marginal votes.
        winning_pair = (best_cultivar, best_ripeness)
        winning_confs = pair_confs.get(winning_pair, [])
        pair_conflict = (
            sum(winning_confs) / 100.0
            < sum(cultivar_weights.values()) * self.CONFLICT_THRESHOLD
        )
        conflict_detected = conflict_detected or pair_conflict

        final_confidence = (
            round(sum(winning_confs) / len(winning_confs), 1) if winning_confs else 0.0
        )

        # Multi-camera spatial complementarity finger count
        final_fingers = self._fuse_finger_counts(results, finger_counts)

        expected = expected_camera_count if expected_camera_count is not None else len(per_camera)
        supporting_views = len(pair_cameras.get(winning_pair, set()))
        insufficient_views = supporting_views < min(2, expected)
        missing_captures = len(per_camera) < expected
        # Peripheral position does not establish physical identity across views.
        # Counts above every individual view need operator confirmation even if
        # all cameras agree on cultivar and ripeness.
        count_requires_review = final_fingers > max(finger_counts, default=0)
        auto_flagged = (
            conflict_detected or final_confidence < review_confidence_threshold * 100
            or insufficient_views or missing_captures or count_requires_review
        )

        if auto_flagged:
            logger.warning(
                f"Fusion auto-flagged: cultivar={best_cultivar}, ripeness={best_ripeness}, "
                f"conf={final_confidence}%, conflict={conflict_detected}, "
                f"no_camera_majority={no_camera_majority}, "
                f"supporting_views={supporting_views}, captured={len(per_camera)}/{expected}, "
                f"count_requires_review={count_requires_review}"
            )

        return FusedResult(
            cultivar=best_cultivar,
            ripeness=best_ripeness,
            confidence=final_confidence,
            finger_count=final_fingers,
            camera_count=len(per_camera),
            conflict_detected=conflict_detected,
            auto_flagged=auto_flagged,
            per_camera=per_camera,
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

    def _fuse_finger_counts(
        self,
        results: list[tuple[str, str, ClassificationResult]],
        finger_counts: list[int],
    ) -> int:
        """
        Multi-camera spatial complementarity fusion for finger counting.

        Anchors on the Top camera view (primary visible tier) and estimates
        additional fingers from peripheral/inner camera positions:
          - Left: lateral outer flank detections (rel_x <= 0.38)
          - Right: lateral outer flank detections (rel_x >= 0.62)
          - Rear: inner concave / underside tier detections (rel_y >= 0.50)

        Position alone does not verify that these detections are new physical
        fingers. The caller flags additions beyond the largest per-view count.

        Guards:
          - Always bounded between max(finger_counts) and sum(finger_counts).
          - Falls back to max(finger_counts) if disabled or no Top view is available.
        """
        if not finger_counts:
            return 0
        baseline_max = max(finger_counts)
        settings = get_settings()
        if not getattr(settings, "multi_camera_finger_fusion", True):
            return baseline_max

        # Map results by normalized camera label
        views_by_label: dict[str, ClassificationResult] = {}
        seen_ids: set[str] = set()
        for camera_id, camera_label, res in results:
            if camera_id in seen_ids:
                continue
            seen_ids.add(camera_id)
            norm_label = (camera_label or "").strip().casefold()
            if norm_label and norm_label not in views_by_label:
                views_by_label[norm_label] = res

        # Anchor view is Top
        top_res = views_by_label.get("top")
        if not top_res or top_res.finger_count <= 0:
            return baseline_max

        top_count = top_res.finger_count
        rear_res = views_by_label.get("rear")
        rear_count = rear_res.finger_count if rear_res else 0

        # Cross-validation stabilization: if Top detects fewer than Rear
        # (detector noise / partial occlusion), trust the higher of the two
        # as the primary tier count. No artificial +1 inflation.
        rear_is_anchor = rear_count >= 8 and rear_count > top_count
        if rear_is_anchor:
            effective_top = rear_count
        else:
            effective_top = top_count

        # Extract novel peripheral detections from side and rear cameras
        novel_left = self._extract_novel_peripheral(views_by_label.get("left"), "left")
        novel_right = self._extract_novel_peripheral(views_by_label.get("right"), "right")
        # If Rear supplies the anchor count, its own boxes are already included.
        novel_rear = 0 if rear_is_anchor else self._extract_novel_peripheral(rear_res, "rear")

        # Cap combined novel additions to prevent overcounting when multiple
        # cameras partially see overlapping peripheral fingers.
        max_total_novel = 9  # Existing heuristic cap; does not verify physical identities.
        total_novel = min(novel_left + novel_right + novel_rear, max_total_novel)

        fused_estimate = effective_top + total_novel

        # Bound strictly between max(per_view) and sum(per_view)
        total_boxes = sum(finger_counts)
        return max(baseline_max, min(fused_estimate, total_boxes))

    def _extract_novel_peripheral(
        self,
        view_res: ClassificationResult | None,
        view_type: str,
    ) -> int:
        """Extract novel detections from a peripheral/concavity camera view."""
        if not view_res or not view_res.detections:
            return 0

        dets = _unique_box_detections(view_res.detections)
        # Ignore views with very few detections (small single-tier bunch or partial view)
        if len(dets) < 4:
            return 0

        xs = [d.x for d in dets] + [d.x + d.w for d in dets]
        ys = [d.y for d in dets] + [d.y + d.h for d in dets]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max_x - min_x
        span_y = max_y - min_y

        novel = 0
        if view_type == "left" and span_x > 0:
            # Outer left flank of the banana hand
            novel = sum(1 for d in dets if ((d.x + d.w / 2) - min_x) / span_x <= 0.38)
        elif view_type == "right" and span_x > 0:
            # Outer right flank of the banana hand
            novel = sum(1 for d in dets if ((d.x + d.w / 2) - min_x) / span_x >= 0.62)
        elif view_type == "rear" and span_y > 0:
            # Inner concave underside tier
            novel = sum(1 for d in dets if ((d.y + d.h / 2) - min_y) / span_y >= 0.50)

        # Cap novel additions per view to prevent extreme outliers
        return min(novel, 4)


# Singleton instance
fusion_engine = FusionEngine()
