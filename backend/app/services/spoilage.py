"""
Random Forest Regression spoilage predictor.

Predicts remaining shelf life (days) based on cultivar, ripeness, temperature, humidity.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core.exceptions import ModelInferenceError
from app.schemas.enums import CultivarEnum, RipenessEnum

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Feature encoding maps ────────────────────────────────────────────────────
CULTIVAR_MAP = {CultivarEnum.LAKATAN.value: 0, CultivarEnum.LATUNDAN.value: 1, CultivarEnum.CARDABA.value: 2}
RIPENESS_MAP = {RipenessEnum.UNRIPE.value: 0, RipenessEnum.SEMI_RIPE.value: 1, RipenessEnum.RIPE.value: 2, RipenessEnum.OVERRIPE.value: 3}


class SpoilagePredictor:
    """
    Random Forest Regression model wrapper for spoilage estimation.

    Features: [cultivar_encoded, ripeness_encoded, temperature, humidity]
    Output:   predicted days until spoilage (float → formatted as range string)
    """

    def __init__(self):
        self._model = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

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
            logger.info("RFR spoilage model loaded successfully")
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
    ) -> str:
        """
        Predict days until spoilage.

        Returns:
            String like "3-5" or "2" representing estimated days.
        """
        # Semi-ripe bananas are transitioning; estimate spoilage like other stages
        # (no special-casing needed — it falls through to fallback/model logic)

        temp = temperature if temperature is not None else 25.0
        hum = humidity if humidity is not None else 65.0

        if self._model is not None:
            return self._model_predict(cultivar, ripeness, temp, hum)
        else:
            return self._fallback_predict(cultivar, ripeness, temp, hum)

    def _model_predict(
        self, cultivar: str, ripeness: str, temperature: float, humidity: float
    ) -> str:
        """Use the loaded RFR model for prediction."""
        try:
            cultivar_enc = CULTIVAR_MAP.get(cultivar, 0)
            ripeness_enc = RIPENESS_MAP.get(ripeness, 1)

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
            return self._fallback_predict(cultivar, ripeness, temperature, humidity)

    def _fallback_predict(
        self, cultivar: str, ripeness: str, temperature: float, humidity: float
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

        multiplier = max(0.2, min(2.0, multiplier))
        base_min = max(1, round(base_min * multiplier))
        base_max = max(base_min, round(base_max * multiplier))

        if base_min == base_max:
            return str(base_min)
        return f"{base_min}-{base_max}"


# Singleton instance
spoilage_predictor = SpoilagePredictor()
