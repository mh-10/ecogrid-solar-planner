"""
api/solar_mock.py
Simulates the NREL PVWatts v8 API response for local development.

Algorithm
---------
1. Derive a base daily irradiance from latitude
   (higher absolute latitude → less solar resource).
2. Apply a sinusoidal seasonal curve (peaks in summer for each hemisphere).
3. Add ±5 % random noise so different runs feel realistic.
4. Scale to AC monthly output using system capacity and a fixed efficiency.
5. Return a dict whose shape mirrors the real PVWatts v8 JSON payload.
"""

import json
import math
import random

# Month index labels for reference
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Average days per month (non-leap year)
DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# Overall system efficiency factor (panel conversion × inverter × wiring losses)
# Incorporates the user-supplied `losses` percentage below.
BASE_PANEL_EFFICIENCY = 0.96


def build_solar_payload(
    lat: float,
    lon: float,
    system_capacity: float = 4.0,
    losses: float = 14.0,
    array_type: int = 1,
    module_type: int = 0,
    tilt: float = 20.0,
    azimuth: float = 180.0,
) -> dict:
    """
    Return a PVWatts-shaped payload with simulated monthly solar data.

    Parameters
    ----------
    lat              : Latitude in decimal degrees (WGS-84).
    lon              : Longitude in decimal degrees (WGS-84).
    system_capacity  : DC system size in kW.
    losses           : System losses in percent (default 14 %).
    array_type       : Array type code (mirrors PVWatts field, unused in sim).
    module_type      : Module type code (mirrors PVWatts field, unused in sim).
    tilt             : Panel tilt in degrees (mirrors PVWatts field).
    azimuth          : Panel azimuth in degrees (mirrors PVWatts field).
    """
    random.seed(int((lat * 1000 + lon * 1000) % 2**31))  # reproducible per location

    efficiency = BASE_PANEL_EFFICIENCY * (1.0 - losses / 100.0)

    # ------------------------------------------------------------------
    # 1. Base daily irradiance (kWh / m² / day) — latitude-adjusted
    #    Ranges from ≈ 5.5 at equator to ≈ 2.5 at 85° latitude.
    # ------------------------------------------------------------------
    base_irradiance = max(1.5, 5.5 - 0.035 * abs(lat))

    # ------------------------------------------------------------------
    # 2. Seasonal sinusoidal curve.
    #    Peak month: July (index 6) for Northern Hemisphere,
    #                January (index 0) for Southern Hemisphere.
    # ------------------------------------------------------------------
    peak_month = 6 if lat >= 0 else 0  # 0-indexed

    solrad_monthly = []
    poa_monthly = []
    ac_monthly = []
    dc_monthly = []

    for m in range(12):
        # Cosine curve: +1 at peak_month, −1 six months later
        angle = (m - peak_month) * math.pi / 6.0
        seasonal_factor = 1.0 + 0.45 * math.cos(angle)

        # ±5 % noise — seeded so the same lat/lon gives the same output
        noise = random.uniform(0.95, 1.05)

        # Daily plane-of-array irradiance for month m
        daily_poa = base_irradiance * seasonal_factor * noise
        monthly_poa = round(daily_poa * DAYS_PER_MONTH[m], 2)

        # Daily irradiance (solrad) — same as poa in simplified model
        daily_solrad = round(daily_poa, 2)

        # AC energy output (kWh) = irradiance × area proxy × efficiency
        # system_capacity (kW) acts as the area-efficiency proxy
        ac = round(monthly_poa * system_capacity * efficiency, 1)
        dc = round(ac / (1 - losses / 100) * 1.05, 1)  # DC slightly higher

        solrad_monthly.append(daily_solrad)
        poa_monthly.append(monthly_poa)
        ac_monthly.append(ac)
        dc_monthly.append(dc)

    ac_annual = round(sum(ac_monthly), 1)
    solrad_annual = round(sum(solrad_monthly) / 12, 2)
    capacity_factor = round((ac_annual / (system_capacity * 8760)) * 100, 1)

    # ------------------------------------------------------------------
    # 3. Assemble PVWatts-shaped response
    # ------------------------------------------------------------------
    return {
        "inputs": {
            "lat": lat,
            "lon": lon,
            "system_capacity": system_capacity,
            "losses": losses,
            "array_type": array_type,
            "module_type": module_type,
            "tilt": tilt,
            "azimuth": azimuth,
        },
        "errors": [],
        "warnings": [],
        "outputs": {
            "ac_monthly": ac_monthly,
            "dc_monthly": dc_monthly,
            "poa_monthly": poa_monthly,
            "solrad_monthly": solrad_monthly,
            "ac_annual": ac_annual,
            "solrad_annual": solrad_annual,
            "capacity_factor": capacity_factor,
        },
        "_meta": {
            "source": "ecogrid-mock",
            "note": "Simulated data only. Not sourced from NREL PVWatts.",
        },
    }
