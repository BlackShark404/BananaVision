"""
BananaVision — Chemical Feature Engineering

Derived environmental features computed from raw temperature / humidity
sensor readings. These features are used as inputs to the Random-Forest
Regression (RFR) spoilage model and are included in exported training
datasets.

Ported from SenseLog/backend/utils/feature_engineering.py.
"""

import math


def calc_dew_point(t_c: float, rh: float) -> float:
    """
    Calculate dew point in °C using the Magnus-Tetens approximation.

    The dew point indicates the temperature at which moisture begins
    to condense — a key factor in banana spoilage acceleration.

    Args:
        t_c: Temperature in degrees Celsius.
        rh:  Relative humidity (0-100%).

    Returns:
        Dew point temperature in °C, rounded to 2 decimal places.
    """
    if rh <= 0:
        return t_c
    a = 17.27
    b = 237.7
    alpha = ((a * t_c) / (b + t_c)) + math.log(rh / 100.0)
    return round((b * alpha) / (a - alpha), 2)


def calc_vpd(t_c: float, rh: float) -> float:
    """
    Calculate Vapor Pressure Deficit (VPD) in kPa.

    VPD measures the difference between the moisture the air *can* hold
    and the moisture it *does* hold.  Higher VPD accelerates moisture
    loss from banana skin, affecting ripening rate.

    Args:
        t_c: Temperature in degrees Celsius.
        rh:  Relative humidity (0-100%).

    Returns:
        VPD in kPa, rounded to 3 decimal places.
    """
    if rh < 0:
        rh = 0
    # Saturation Vapor Pressure (kPa)
    svp = 0.61078 * math.exp((17.27 * t_c) / (t_c + 237.3))
    # Actual Vapor Pressure (kPa)
    avp = (rh / 100.0) * svp
    return round(svp - avp, 3)


def calc_heat_index(t_c: float, rh: float) -> float:
    """
    Calculate Heat Index (apparent temperature) in °C using the
    Rothfusz regression.

    The heat index combines temperature and humidity into a single
    "feels-like" value that better correlates with biological
    degradation rates than raw temperature alone.

    Args:
        t_c: Temperature in degrees Celsius.
        rh:  Relative humidity (0-100%).

    Returns:
        Heat index in °C, rounded to 2 decimal places.
    """
    # Convert C to F for the Rothfusz equation
    t_f = (t_c * 9 / 5) + 32
    # Simple formula first
    hi = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh * 0.094))
    if hi >= 80:
        # Full Rothfusz regression
        hi = (
            -42.379
            + 2.04901523 * t_f
            + 10.14333127 * rh
            - 0.22475541 * t_f * rh
            - 0.00683783 * t_f * t_f
            - 0.05481717 * rh * rh
            + 0.00122874 * t_f * t_f * rh
            + 0.00085282 * t_f * rh * rh
            - 0.00000199 * t_f * t_f * rh * rh
        )
        # Adjustments for extreme conditions
        if rh < 13 and 80 <= t_f < 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95)) / 17)
        elif rh > 85 and 80 <= t_f <= 87:
            hi += ((rh - 85) / 10) * ((87 - t_f) / 5)
    # Convert F back to C
    return round((hi - 32) * 5 / 9, 2)
