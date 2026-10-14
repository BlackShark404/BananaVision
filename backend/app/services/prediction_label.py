"""Immutable prediction values shared by QR and human-readable label."""

from dataclasses import dataclass


def _value(value):
    return str(getattr(value, "value", value))


@dataclass(frozen=True)
class PredictionData:
    prediction_id: str
    ripeness: str
    spoilage_days: str
    confidence: float
    temperature: float | None = None
    humidity: float | None = None
    demo: bool = False

    @classmethod
    def from_scan(cls, scan, *, demo=False):
        result = scan.classification
        if (result is None or result.ripeness is None or result.confidence is None
                or result.spoilage_days is None):
            raise ValueError("This scan has no complete prediction to print.")
        return cls(
            str(scan.id), _value(result.ripeness), result.spoilage_days,
            float(result.confidence),
            float(result.temperature) if result.temperature is not None else None,
            float(result.humidity) if result.humidity is not None else None,
            demo,
        )

    def payload(self) -> str:
        lines = [
            "BANANAVISION", f"ID={self.prediction_id}",
            f"RIPENESS={self.ripeness}", f"SPOILAGE_DAYS={self.spoilage_days}",
            f"CONFIDENCE={self.confidence:g}%",
        ]
        if self.temperature is not None:
            lines.append(f"TEMP={self.temperature:g}C")
        if self.humidity is not None:
            lines.append(f"HUMIDITY={self.humidity:g}%")
        lines.append("TEST=DEMO" if self.demo else "TEST=LIVE")
        return "\n".join(lines)

    def panel(self) -> tuple[str, ...]:
        return (
            "BANANAVISION", self.prediction_id[:8], self.ripeness,
            f"{self.spoilage_days} days", f"{self.confidence:g}%",
            "DEMO" if self.demo else "PREDICTION",
        )
