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
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core.exceptions import ModelInferenceError
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

    Output: predicted days until spoilage (float → formatted as range string)
    """

    def __init__(self):
        self._model = None
        self._loaded = False
        self._n_features: int = LEGACY_FEATURE_COUNT

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def uses_enhanced_features(self) -> bool:
        """True if the loaded model expects engineered chemical features."""
        return self._n_features >= ENHANCED_FEATURE_COUNT

    def load(self) -> None:
        """Load RFR model from .joblib file. Call once at startup."""
        try:
            import joblib

            model_path = settings.rfr_model_path
            logger.info(f"Loading RFR spoilage model from {model_path}")

            if not Path(model_path).exists():
                logger.warning(
                    f"RFR model not found at {model_path}. "
                    "Running in fallback mode with rule-based estimation."
                )
                self._model = None
                self._loaded = True
                return

            self._model = joblib.load(model_path)
            self._loaded = True

            # Auto-detect feature count from the loaded model
            if hasattr(self._model, "n_features_in_"):
                self._n_features = self._model.n_features_in_
                logger.info(
                    f"RFR model loaded — expects {self._n_features} features "
                    f"({'enhanced' if self.uses_enhanced_features else 'legacy'} mode)"
                )
            else:
                self._n_features = LEGACY_FEATURE_COUNT
                logger.info("RFR model loaded (legacy mode, feature count unknown)")

        except Exception as exc:
            logger.error(f"Failed to load RFR model: {exc}")
            self._model = None
            self._loaded = True  # Allow fallback

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
            String like "3-5" or "2" representing estimated days.
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
            cultivar_enc = CULTIVAR_MAP.get(cultivar, 0)
            ripeness_enc = RIPENESS_MAP.get(ripeness, 1)

            if self.uses_enhanced_features:
                # Compute VPD if not provided
                v = vpd if vpd is not None else calc_vpd(temperature, humidity)
                treat_enc = TREATMENT_MAP.get(treatment, 0) if treatment else 0

                features = np.array([[
                    cultivar_enc, ripeness_enc, temperature, humidity,
                    v, treat_enc,
                ]])
            else:
                # Legacy 4-feature model
                features = np.array([[cultivar_enc, ripeness_enc, temperature, humidity]])

            prediction = float(self._model.predict(features)[0])

            # Convert to range string with ±RMSE margin
            pred_int = max(0, round(prediction))
            margin = max(1, round(prediction * 0.15))
            low = max(0, pred_int - margin)
            high = pred_int + margin

            if low == high:
                return str(low)
            return f"{low}-{high}"

        except Exception as exc:
            logger.error(f"RFR inference error: {exc}")
            return self._fallback_predict(cultivar, ripeness, temperature, humidity, treatment)

    def _fallback_predict(
        self, cultivar: str, ripeness: str, temperature: float, humidity: float,
        treatment: str | None = None,
    ) -> str:
        """
        Rule-based fallback matching the frontend's getSpoilageDays() logic.
        Used when no RFR model file is available.
        """
        base_min, base_max = 0, 0

        if cultivar == CultivarEnum.LAKATAN.value:
            if ripeness == RipenessEnum.UNRIPE.value:
                base_min, base_max = 4, 6
            elif ripeness == RipenessEnum.RIPE.value:
                base_min, base_max = 2, 3
            elif ripeness == RipenessEnum.OVERRIPE.value:
                base_min, base_max = 1, 2
            elif ripeness == RipenessEnum.SEMI_RIPE.value:
                base_min, base_max = 3, 5
        elif cultivar == CultivarEnum.LATUNDAN.value:
            if ripeness == RipenessEnum.UNRIPE.value:
                base_min, base_max = 3, 5
            elif ripeness == RipenessEnum.RIPE.value:
                base_min, base_max = 1, 2
            elif ripeness == RipenessEnum.OVERRIPE.value:
                base_min, base_max = 1, 1
            elif ripeness == RipenessEnum.SEMI_RIPE.value:
                base_min, base_max = 2, 4
        elif cultivar == CultivarEnum.CARDABA.value:
            if ripeness == RipenessEnum.UNRIPE.value:
                base_min, base_max = 6, 8
            elif ripeness == RipenessEnum.RIPE.value:
                base_min, base_max = 3, 4
            elif ripeness == RipenessEnum.OVERRIPE.value:
                base_min, base_max = 2, 3
            elif ripeness == RipenessEnum.SEMI_RIPE.value:
                base_min, base_max = 5, 7

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

        # Ethephon-treated bananas spoil faster
        if treatment == TreatmentEnum.ETHEPHON.value:
            multiplier -= 0.15

        multiplier = max(0.2, min(2.0, multiplier))
        base_min = max(1, round(base_min * multiplier))
        base_max = max(base_min, round(base_max * multiplier))

        if base_min == base_max:
            return str(base_min)
        return f"{base_min}-{base_max}"


# Singleton instance
spoilage_predictor = SpoilagePredictor()
