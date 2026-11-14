"""
Random Forest Regression spoilage predictor.

Predicts remaining shelf life (days) based on cultivar, ripeness,
temperature, humidity, VPD, and treatment.

Auto-detects whether the loaded model expects 4 features (legacy) or
6 features (enhanced with VPD + treatment), so existing models
continue to work while upgraded models benefit from richer inputs.
"""

from __future__ import annotations

import logging
import math
from decimal import Decimal
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.schemas.enums import CultivarEnum, RipenessEnum, TreatmentEnum
from app.services.feature_engineering import calc_vpd

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Feature encoding maps ────────────────────────────────────────────────────
CULTIVAR_MAP = {CultivarEnum.LAKATAN.value: 0, CultivarEnum.LATUNDAN.value: 1, CultivarEnum.CARDABA.value: 2}
RIPENESS_MAP = {RipenessEnum.UNRIPE.value: 0, RipenessEnum.SEMI_RIPE.value: 1, RipenessEnum.RIPE.value: 2, RipenessEnum.OVERRIPE.value: 3}
TREATMENT_MAP = {TreatmentEnum.NATURAL.value: 0, TreatmentEnum.ETHEPHON.value: 1}

LEGACY_FEATURE_COUNT = 4
ENHANCED_FEATURE_COUNT = 6  # + [vpd, treatment]
LEGACY_FEATURE_COLUMNS = (
    "cultivar_encoded", "ripeness_encoded", "temperature", "humidity",
)
ENHANCED_FEATURE_COLUMNS = LEGACY_FEATURE_COLUMNS + ("vpd", "treatment_encoded")


class SpoilagePredictor:
    """
    Random Forest Regression model wrapper for spoilage estimation.

    Legacy features (4):
        [cultivar_encoded, ripeness_encoded, temperature, humidity]

    Enhanced features (6):
        [cultivar_encoded, ripeness_encoded, temperature, humidity,
         vpd, treatment_encoded]

    The model's expected feature count is auto-detected on load via
    ``model.n_features_in_``, so both legacy and enhanced models work
    without configuration changes.

    Output: model prediction as a decimal string in the existing spoilage_days
    field. Rule-based fallback retains its historical range representation.
    """

    def __init__(self):
        self._model = None
        self._loaded = False
        self._reset_feature_metadata()

    def _reset_feature_metadata(self) -> None:
        self._n_features: int = LEGACY_FEATURE_COUNT
        self._feature_columns = LEGACY_FEATURE_COLUMNS
        self._cultivar_map = CULTIVAR_MAP.copy()
        self._ripeness_map = RIPENESS_MAP.copy()
        self._treatment_map = TREATMENT_MAP.copy()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def uses_enhanced_features(self) -> bool:
        """True if the loaded model expects engineered chemical features."""
        return self._n_features == ENHANCED_FEATURE_COUNT

    @staticmethod
    def resolve_model_path(configured: str) -> Path:
        """Keep explicit station artifacts; resolve the historical default to our bundle.

        The default used to name a file under ``weights/``, while Git ships the
        RFR bundle directly under ``app/ml/``. Only that relative default gets
        this compatibility lookup: a missing custom artifact must stay visible.
        """
        path = Path(configured)
        if path.exists() or path.is_absolute():
            return path
        if path.as_posix() != "app/ml/weights/spoilage_rfr.joblib":
            return path
        app_dir = Path(__file__).resolve().parents[1]
        station_path = app_dir / "ml" / "weights" / "spoilage_rfr.joblib"
        if station_path.exists():
            return station_path
        packaged_path = app_dir / "ml" / "spoilage_rfr.joblib"
        return packaged_path if packaged_path.exists() else path

    @staticmethod
    def _training_encoding(metadata: dict, key: str, default: dict) -> dict:
        """Convert training's code-to-label maps to the app's label-to-code maps."""
        raw_map = metadata.get(key)
        if raw_map is None:
            return default.copy()
        if not isinstance(raw_map, dict):
            raise ValueError(f"Invalid RFR {key} metadata")

        def normalized(label: str) -> str:
            return " ".join(label.casefold().replace("-", " ").replace("_", " ").split())

        labels = {normalized(label): label for label in default}
        encoding = {}
        for code, label in raw_map.items():
            if (
                isinstance(code, bool) or not isinstance(code, (int, np.integer))
                or code < 0 or not isinstance(label, str)
            ):
                raise ValueError(f"Invalid RFR {key} entry")
            canonical = labels.get(normalized(label))
            if canonical is None or canonical in encoding:
                raise ValueError(f"Unknown or duplicate RFR {key} label: {label}")
            encoding[canonical] = int(code)
        if set(encoding) != set(default):
            raise ValueError(f"Incomplete RFR {key} metadata")
        return encoding

    def _configure_artifact(self, artifact) -> None:
        """Accept bare estimators and training bundles with their feature metadata."""
        model = artifact.get("model") if isinstance(artifact, dict) else artifact
        metadata = artifact.get("metadata", {}) if isinstance(artifact, dict) else {}
        if not callable(getattr(model, "predict", None)):
            raise ValueError("RFR artifact does not contain a prediction model")
        if not isinstance(metadata, dict):
            raise ValueError("RFR bundle metadata must be a dictionary")

        columns = metadata.get("feature_columns")
        feature_count = getattr(model, "n_features_in_", None)
        if feature_count is None:
            feature_count = len(columns) if columns is not None else LEGACY_FEATURE_COUNT
        if feature_count not in (LEGACY_FEATURE_COUNT, ENHANCED_FEATURE_COUNT):
            raise ValueError(f"Unsupported RFR feature count: {feature_count}")
        expected = (
            ENHANCED_FEATURE_COLUMNS if feature_count == ENHANCED_FEATURE_COUNT
            else LEGACY_FEATURE_COLUMNS
        )
        columns = tuple(columns) if columns is not None else expected
        if len(columns) != feature_count or set(columns) != set(expected):
            raise ValueError("RFR training feature columns do not match the model")

        cultivar_map = self._training_encoding(metadata, "cultivar_map", CULTIVAR_MAP)
        ripeness_map = self._training_encoding(metadata, "ripeness_map", RIPENESS_MAP)
        treatment_map = self._training_encoding(metadata, "treatment_map", TREATMENT_MAP)
        self._model = model
        self._n_features = int(feature_count)
        self._feature_columns = columns
        self._cultivar_map = cultivar_map
        self._ripeness_map = ripeness_map
        self._treatment_map = treatment_map

    def load(self) -> None:
        """Load RFR model from .joblib file. Call once at startup."""
        self._model = None
        self._loaded = False
        self._reset_feature_metadata()
        try:
            import joblib

            model_path = self.resolve_model_path(settings.rfr_model_path)
            logger.info(f"Loading RFR spoilage model from {model_path}")

            if not Path(model_path).exists():
                logger.warning(
                    f"RFR model not found at {model_path}. "
                    "Running in fallback mode with rule-based estimation."
                )
                self._model = None
                return

            self._configure_artifact(joblib.load(model_path))
            self._loaded = True
            logger.info(
                f"RFR model loaded — expects {self._n_features} features "
                f"({'enhanced' if self.uses_enhanced_features else 'legacy'} mode)"
            )

        except Exception as exc:
            logger.error(f"Failed to load RFR model: {exc}")
            self._model = None
            # Fallback remains usable, but health must not report a loaded RFR.
            self._loaded = False

    def predict(
        self,
        cultivar: str,
        ripeness: str,
        temperature: float | None = None,
        humidity: float | None = None,
        vpd: float | None = None,
        treatment: str | None = None,
    ) -> str:
        """
        Predict days until spoilage.

        If the loaded model expects enhanced features, VPD is computed
        automatically from temperature/humidity when not explicitly provided.

        Returns:
            Unrounded model estimate as a decimal string, or a fallback range.
        """
        temp = temperature if temperature is not None else 25.0
        hum = humidity if humidity is not None else 65.0

        if self._model is not None:
            return self._model_predict(
                cultivar, ripeness, temp, hum,
                vpd=vpd,
                treatment=treatment,
            )
        else:
            return self._fallback_predict(cultivar, ripeness, temp, hum, treatment)

    def _model_predict(
        self,
        cultivar: str,
        ripeness: str,
        temperature: float,
        humidity: float,
        vpd: float | None = None,
        treatment: str | None = None,
    ) -> str:
        """Use the loaded RFR model for prediction."""
        try:
            values = {
                "cultivar_encoded": self._cultivar_map.get(
                    cultivar, self._cultivar_map[CultivarEnum.LAKATAN.value],
                ),
                "ripeness_encoded": self._ripeness_map.get(
                    ripeness, self._ripeness_map[RipenessEnum.SEMI_RIPE.value],
                ),
                "temperature": temperature,
                "humidity": humidity,
            }

            if self.uses_enhanced_features:
                # Compute VPD if not provided
                values["vpd"] = vpd if vpd is not None else calc_vpd(temperature, humidity)
                values["treatment_encoded"] = self._treatment_map.get(
                    treatment, self._treatment_map[TreatmentEnum.NATURAL.value],
                )

            features = np.array([[values[column] for column in self._feature_columns]])

            prediction = float(self._model.predict(features)[0])

            if not math.isfinite(prediction) or prediction < 0:
                raise ValueError("RFR returned an invalid shelf-life estimate")
            # Preserve the model mean, not a rounded quantile midpoint. Decimal
            # notation is compatible with existing SQL/Python risk parsers.
            result = format(Decimal(str(prediction)), "f")
            if "." in result:
                result = result.rstrip("0").rstrip(".")
            if len(result) > 20:
                raise ValueError("RFR estimate exceeds spoilage_days storage capacity")
            return result

        except Exception as exc:
            logger.error(f"RFR inference error: {exc}")
            return self._fallback_predict(cultivar, ripeness, temperature, humidity, treatment)

    def _fallback_predict(
        self, cultivar: str, ripeness: str, temperature: float, humidity: float,
        treatment: str | None = None,
    ) -> str:
        """
        Rule-based fallback based on literature values for natural vs ethephon-treated bananas.
        Used when no RFR model file is available.
        """
        base_min, base_max = 0, 0

        # Base shelf life adjusted to align with literature averages:
        # Natural averages: Unripe (6-9d), Semi-ripe (3-5d), Ripe (2-4d), Overripe (1-2d)
        if cultivar == CultivarEnum.LAKATAN.value:
            if ripeness == RipenessEnum.UNRIPE.value:
                base_min, base_max = 5, 8
            elif ripeness == RipenessEnum.SEMI_RIPE.value:
                base_min, base_max = 3, 5
            elif ripeness == RipenessEnum.RIPE.value:
                base_min, base_max = 2, 4
            elif ripeness == RipenessEnum.OVERRIPE.value:
                base_min, base_max = 1, 2
        elif cultivar == CultivarEnum.LATUNDAN.value:
            if ripeness == RipenessEnum.UNRIPE.value:
                base_min, base_max = 4, 7
            elif ripeness == RipenessEnum.SEMI_RIPE.value:
                base_min, base_max = 2, 4
            elif ripeness == RipenessEnum.RIPE.value:
                base_min, base_max = 1, 3
            elif ripeness == RipenessEnum.OVERRIPE.value:
                base_min, base_max = 1, 1
        elif cultivar == CultivarEnum.CARDABA.value:
            if ripeness == RipenessEnum.UNRIPE.value:
                base_min, base_max = 7, 10
            elif ripeness == RipenessEnum.SEMI_RIPE.value:
                base_min, base_max = 4, 6
            elif ripeness == RipenessEnum.RIPE.value:
                base_min, base_max = 3, 5
            elif ripeness == RipenessEnum.OVERRIPE.value:
                base_min, base_max = 2, 3
        else:
            # Fallback for unknown cultivars
            base_min, base_max = 5, 8

        # Environmental multiplier
        multiplier = 1.0
        if temperature > 28:
            multiplier -= 0.3
        elif temperature < 22:
            multiplier += 0.2
        if humidity > 75:
            multiplier -= 0.2
        elif humidity < 60:
            multiplier += 0.1

        # Ethephon treatment accelerates ripening significantly depending on the current stage
        # Based on literature: Unripe drops from 6-9d -> 3-6d (~35-40% reduction)
        if treatment == TreatmentEnum.ETHEPHON.value:
            if ripeness == RipenessEnum.UNRIPE.value:
                multiplier -= 0.40
            elif ripeness == RipenessEnum.SEMI_RIPE.value:
                multiplier -= 0.25
            elif ripeness == RipenessEnum.RIPE.value:
                multiplier -= 0.30
            elif ripeness == RipenessEnum.OVERRIPE.value:
                multiplier -= 0.15

        multiplier = max(0.2, min(2.0, multiplier))
        base_min = max(1, round(base_min * multiplier))
        base_max = max(base_min, round(base_max * multiplier))

        if base_min == base_max:
            return str(base_min)
        return f"{base_min}-{base_max}"


# Singleton instance
spoilage_predictor = SpoilagePredictor()
