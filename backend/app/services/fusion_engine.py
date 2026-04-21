"""
Multi-camera fusion engine.

Merges YOLOv8n detections from 4 cameras into a single authoritative
classification using confidence-weighted majority voting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.classification import ClassificationResult

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
        1. Collect all (class, confidence) votes from each camera
        2. Weight each vote by its detection confidence
        3. Winner = class with highest total weighted score
        4. finger_count = max across cameras (most complete view)
        5. Final confidence = weighted average of winning class confidences
        6. Auto-flag if winner has <60% of total weight
    """

    CONFLICT_THRESHOLD = 0.60  # Flag if winner has less than 60% of total weight
    MIN_CONFIDENCE = 0.50       # Minimum confidence to consider a result valid

    def fuse(self, results: list[tuple[str, str, ClassificationResult]]) -> FusedResult:
        """
        Merge classification results from multiple cameras.

        Args:
            results: List of (camera_id, camera_label, ClassificationResult) tuples

        Returns:
            FusedResult with final classification
        """
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
        cultivar_confs: dict[str, list[float]] = {}
        ripeness_weights: dict[str, float] = {}
        ripeness_confs: dict[str, list[float]] = {}
        finger_counts: list[int] = []
        per_camera: list[CameraDetection] = []

        for camera_id, camera_label, result in results:
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

            # Accumulate cultivar votes
            if result.cultivar:
                conf = result.confidence / 100.0  # Normalize to 0-1
                cultivar_weights[result.cultivar] = (
                    cultivar_weights.get(result.cultivar, 0) + conf
                )
                cultivar_confs.setdefault(result.cultivar, []).append(result.confidence)

            # Accumulate ripeness votes
            if result.ripeness:
                conf = result.confidence / 100.0
                ripeness_weights[result.ripeness] = (
                    ripeness_weights.get(result.ripeness, 0) + conf
                )
                ripeness_confs.setdefault(result.ripeness, []).append(result.confidence)

            finger_counts.append(result.finger_count)

        # Determine winners
        best_cultivar = self._select_winner(cultivar_weights) or "Unknown"
        best_ripeness = self._select_winner(ripeness_weights) or "Unknown"

        # Check for conflicts
        cultivar_conflict = self._has_conflict(cultivar_weights, best_cultivar)
        ripeness_conflict = self._has_conflict(ripeness_weights, best_ripeness)
        conflict_detected = cultivar_conflict or ripeness_conflict

        # Final confidence = mean of winning class confidences
        winning_confs: list[float] = []
        if best_cultivar in cultivar_confs:
            winning_confs.extend(cultivar_confs[best_cultivar])
        if best_ripeness in ripeness_confs:
            winning_confs.extend(ripeness_confs[best_ripeness])

        final_confidence = (
            round(sum(winning_confs) / len(winning_confs), 1) if winning_confs else 0.0
        )

        # Finger count = max across cameras (most complete view)
        final_fingers = max(finger_counts) if finger_counts else 0

        # Auto-flag if low confidence or conflict
        auto_flagged = conflict_detected or final_confidence < self.MIN_CONFIDENCE * 100

        if auto_flagged:
            logger.warning(
                f"Fusion auto-flagged: cultivar={best_cultivar}, ripeness={best_ripeness}, "
                f"conf={final_confidence}%, conflict={conflict_detected}"
            )

        return FusedResult(
            cultivar=best_cultivar,
            ripeness=best_ripeness,
            confidence=final_confidence,
            finger_count=final_fingers,
            camera_count=len(results),
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


# Singleton instance
fusion_engine = FusionEngine()
