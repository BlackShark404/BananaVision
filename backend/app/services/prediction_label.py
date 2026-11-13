"""Immutable prediction values shared by QR and human-readable label."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.time import as_manila, now_manila
from app.services.inventory_policy import prediction_bounds


def _value(value):
    return str(getattr(value, "value", value))


def _iso_date(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    try:
        return as_manila(dt).isoformat()
    except Exception:
        return str(dt)


def _get_tracking_url(scan_id: str) -> str | None:
    try:
        from app.config import get_settings
        settings = get_settings()
        if settings.public_base_url:
            return f"{settings.public_base_url.rstrip('/')}/track/{scan_id}"
    except Exception:
        pass

    public_file = Path(r"C:\Users\Kent\AppData\Local\BananaVision\laptop-host\public-url.txt")
    if public_file.is_file():
        try:
            url = public_file.read_text(encoding="utf-8").strip()
            if url:
                return f"{url.rstrip('/')}/track/{scan_id}"
        except Exception:
            pass

    return None


@dataclass(frozen=True)
class PredictionData:
    prediction_id: str
    ripeness: str
    spoilage_days: str
    confidence: float
    temperature: float | None = None
    humidity: float | None = None
    demo: bool = False
    cultivar: str | None = None
    scanned_at: str | None = None
    tracking_url: str | None = None

    @classmethod
    def from_scan(cls, scan, *, demo=False, tracking_url: str | None = None):
        result = scan.classification
        if (result is None or result.ripeness is None or result.confidence is None
                or result.spoilage_days is None):
            raise ValueError("This scan has no complete prediction to print.")
        if tracking_url is None:
            tracking_url = _get_tracking_url(str(scan.id))
        return cls(
            str(scan.id), _value(result.ripeness), result.spoilage_days,
            float(result.confidence),
            float(result.temperature) if result.temperature is not None else None,
            float(result.humidity) if result.humidity is not None else None,
            demo,
            cultivar=_value(result.cultivar) if result.cultivar else None,
            scanned_at=_iso_date(getattr(scan, "date_time", None)),
            tracking_url=tracking_url,
        )

    def qr_data(self) -> str:
        return self.tracking_url if self.tracking_url else self.payload()

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
        cultivar_text = self.cultivar or "Banana"
        bounds = prediction_bounds(self.spoilage_days)
        if bounds:
            low, high = bounds
            range_str = f"{low}-{high}" if low != high else str(low)
            unit = "Day" if range_str == "1" else "Days"
            spoilage_text = f"Est. {range_str} {unit}"
        else:
            spoilage_text = f"Est. {self.spoilage_days} Days"

        if self.demo:
            date_text = "DEMO"
        elif self.scanned_at:
            try:
                dt = datetime.fromisoformat(self.scanned_at)
                date_text = as_manila(dt).strftime("%b %d, %Y")
            except Exception:
                date_text = now_manila().strftime("%b %d, %Y")
        else:
            date_text = now_manila().strftime("%b %d, %Y")

        return (
            "BANANAVISION",
            cultivar_text,
            self.ripeness,
            spoilage_text,
            date_text,
        )
