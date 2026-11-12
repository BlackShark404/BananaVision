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
    cultivar_conflict: bool = False
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

        # Views overlap: 2D edge positions cannot establish unique fingers across
        # cameras. Use the largest observed per-view count without adding sightings.
        final_fingers = max(finger_counts, default=0)

        expected = expected_camera_count if expected_camera_count is not None else len(per_camera)
        supporting_views = len(pair_cameras.get(winning_pair, set()))
        insufficient_views = supporting_views < min(2, expected)
        missing_captures = len(per_camera) < expected
        # Different positive counts can reflect occlusion or detector errors. The
        # maximum is still an estimate; request confirmation when detecting views
        # disagree. Empty/missing views retain the support/capture checks above.
        count_requires_review = len({count for count in finger_counts if count > 0}) > 1
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
            cultivar_conflict=cultivar_conflict,
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


# Singleton instance
fusion_engine = FusionEngine()
