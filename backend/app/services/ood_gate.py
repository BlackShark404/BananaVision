"""
Out-of-distribution (OOD) rejection gate.

The cultivar model is closed-set: every box it emits is one of the twelve
Lakatan/Latundan/Cardaba ripeness labels, so an unrelated object can only be
reported as a supported cultivar. This gate requires independent banana evidence
from the general COCO detector before a cultivar box is trusted:

    1. Scan level: enough camera views must contain a banana at the acceptance
       confidence, otherwise the scan is rejected before classification.
    2. Box level: a cultivar box is kept only where lower-confidence banana
       evidence covers its centre in the same frame. Background fixtures and
       foreign objects beside a real banana no longer vote or count as fingers.

Pure functions only: no model, database or camera access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# Stable machine-readable outcomes shared with the API and the kiosk.
REJECTION_CODE = "ood_rejected"
REASON_NO_BANANA = "no_banana"
REASON_NO_TARGET_CULTIVAR = "no_target_cultivar"
GATE_UNAVAILABLE_CODE = "ood_gate_unavailable"

REJECTION_MESSAGE = (
    "No Lakatan, Latundan, or Cardaba detected. "
    "Place a supported banana hand on the tray and scan again."
)
GATE_UNAVAILABLE_MESSAGE = (
    "Banana verification is unavailable, so the scan was not classified. "
    "Ask an administrator to check the detection models."
)


class Box(Protocol):
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class EvidenceBox:
    """A banana box from the general detector, in original pixel coordinates."""
    x: float
    y: float
    w: float
    h: float
    confidence: float


@dataclass(frozen=True)
class GatePolicy:
    """Operating thresholds; see docs/audits/ood-gate-evaluation-2026-11-12.json."""
    banana_confidence: float = 0.30
    support_confidence: float = 0.05
    support_margin: float = 0.25
    min_banana_views: int = 1
    box_support_filter: bool = True

    def __post_init__(self) -> None:
        if not 0 < self.support_confidence <= self.banana_confidence <= 1:
            raise ValueError(
                "Thresholds must satisfy 0 < support confidence <= banana confidence <= 1"
            )
        if not 0 <= self.support_margin <= 1:
            raise ValueError("Support margin must be in [0, 1]")
        if self.min_banana_views < 1:
            raise ValueError("At least one banana view is required")


def policy_from_settings(settings: object) -> GatePolicy:
    """Build the policy from application settings; absent fields keep the defaults."""
    defaults = GatePolicy()
    return GatePolicy(
        banana_confidence=getattr(settings, "ood_banana_confidence", defaults.banana_confidence),
        support_confidence=getattr(
            settings, "ood_support_confidence", defaults.support_confidence,
        ),
        support_margin=getattr(settings, "ood_support_margin", defaults.support_margin),
        min_banana_views=getattr(settings, "ood_min_banana_views", defaults.min_banana_views),
        box_support_filter=getattr(
            settings, "ood_box_support_filter", defaults.box_support_filter,
        ),
    )


@dataclass
class ViewEvidence:
    """Banana evidence for one camera frame."""
    camera_id: str
    camera_label: str
    # None means the detector exposed no boxes (legacy result): nothing can be filtered.
    evidence: list[EvidenceBox] | None
    banana_score: float
    has_banana: bool


@dataclass
class ScanGateDecision:
    accepted: bool
    banana_views: int
    required_views: int
    reason: str | None = None
    views: list[ViewEvidence] = field(default_factory=list)


def banana_score(evidence: list[EvidenceBox]) -> float:
    """Frame-level OOD score: the strongest banana confidence (0 when none)."""
    return max((box.confidence for box in evidence), default=0.0)


def is_supported(box: Box, evidence: list[EvidenceBox], margin: float) -> bool:
    """True when banana evidence, grown by margin on each side, covers the box centre."""
    centre_x = box.x + box.w / 2
    centre_y = box.y + box.h / 2
    return any(
        item.x - margin * item.w <= centre_x <= item.x + item.w * (1 + margin)
        and item.y - margin * item.h <= centre_y <= item.y + item.h * (1 + margin)
        for item in evidence
    )


def decide_scan(views: list[ViewEvidence], policy: GatePolicy) -> ScanGateDecision:
    """Accept the scan only when enough captured views show a banana."""
    banana_views = sum(1 for view in views if view.has_banana)
    # A station with fewer cameras cannot be asked for more views than it has.
    required = max(1, min(policy.min_banana_views, len(views)))
    accepted = banana_views >= required
    return ScanGateDecision(
        accepted=accepted, banana_views=banana_views, required_views=required,
        reason=None if accepted else REASON_NO_BANANA, views=views,
    )
