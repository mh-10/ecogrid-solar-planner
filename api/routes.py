"""
api/routes.py
Flask Blueprint exposing all /api/* endpoints.

Endpoints
---------
GET  /api/solar-data           -> Live NREL PVWatts v8 data (mock fallback)
POST /api/locations            -> Persist a location + fetch its estimate
GET  /api/locations            -> List all saved locations with latest estimate
DELETE /api/locations/<int:id> -> Remove a location (cascades to estimates)
"""

import json
import sqlite3

import requests as http_client
from flask import Blueprint, current_app, jsonify, request

from api.solar_mock import build_solar_payload

api_bp = Blueprint("api", __name__, url_prefix="/api")

NREL_PVWATTS_URL = "https://developer.nlr.gov/api/pvwatts/v8.json"
NREL_TIMEOUT_SEC = 10   # seconds before we fall back to mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    """Open a SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(current_app.config["DB_PATH"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def fetch_solar_payload(
    lat: float,
    lon: float,
    system_capacity: float = 4.0,
    losses: float = 14.0,
    module_type: int = 0,
    array_type: int = 0,
    tilt: float = 20.0,
    azimuth: float = 180.0,
) -> dict:
    """
    Try the live NREL PVWatts v6 API first.
    Falls back to the local simulator if:
      - NREL_API_KEY is absent / empty
      - The NREL request fails or times out
      - NREL returns API-level errors

    Always returns a dict in the same PVWatts-shaped schema so callers
    never need to branch on the data source.
    """
    api_key = current_app.config.get("NREL_API_KEY", "")

    if api_key:
        params = {
            "api_key"         : api_key,
            "lat"             : lat,
            "lon"             : lon,
            "system_capacity" : system_capacity,
            "module_type"     : module_type,
            "losses"          : losses,
            "array_type"      : array_type,
            "tilt"            : tilt,
            "azimuth"         : azimuth,
        }

        try:
            resp = http_client.get(
                NREL_PVWATTS_URL,
                params=params,
                timeout=NREL_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            nrel_data = resp.json()

            # NREL returns API-level errors inside the JSON body
            if nrel_data.get("errors"):
                raise ValueError(f"NREL errors: {nrel_data['errors']}")

            # Stamp the source so the frontend can show where data came from
            nrel_data.setdefault("_meta", {})
            nrel_data["_meta"]["source"] = "nrel-pvwatts-v8"
            nrel_data["_meta"]["note"]   = "Live data from NREL PVWatts v8 API (developer.nlr.gov)."
            return nrel_data

        except Exception as exc:
            # Log and fall through to mock
            current_app.logger.warning(
                "NREL PVWatts request failed (%s) — using mock data.", exc
            )

    # ---- Fallback: local simulator ----------------------------------------
    payload = build_solar_payload(
        lat=lat,
        lon=lon,
        system_capacity=system_capacity,
        losses=losses,
        array_type=array_type,
        module_type=module_type,
        tilt=tilt,
        azimuth=azimuth,
    )
    return payload


# ---------------------------------------------------------------------------
# GET /api/solar-data
# ---------------------------------------------------------------------------

@api_bp.route("/solar-data", methods=["GET"])
def solar_data():
    """
    Return a PVWatts v6 payload for the requested coordinates.
    Uses the live NREL API when NREL_API_KEY is present, otherwise
    falls back to the local simulator transparently.

    Query params:
        lat              (float, required)
        lon              (float, required)
        system_capacity  (float, optional, default 4.0)
        losses           (float, optional, default 14.0)
        module_type      (int,   optional, default 0)
        array_type       (int,   optional, default 0)
        tilt             (float, optional, default 20.0)
    """
    # --- Validate required params -------------------------------------------
    errors = []
    try:
        lat = float(request.args["lat"])
    except (KeyError, ValueError):
        errors.append("'lat' is required and must be a valid float.")

    try:
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        errors.append("'lon' is required and must be a valid float.")

    if errors:
        return jsonify({"errors": errors}), 400

    # --- Optional params (with sensible clamps) -----------------------------
    system_capacity = max(0.5, min(float(request.args.get("system_capacity", 4.0)), 500.0))
    losses          = max(0.0, min(float(request.args.get("losses",           14.0)),  99.0))
    module_type     = int(request.args.get("module_type", 0))
    array_type      = int(request.args.get("array_type",  0))
    tilt            = float(request.args.get("tilt", 20.0))

    payload = fetch_solar_payload(
        lat=lat,
        lon=lon,
        system_capacity=system_capacity,
        losses=losses,
        module_type=module_type,
        array_type=array_type,
        tilt=tilt,
    )
    return jsonify(payload), 200


# ---------------------------------------------------------------------------
# POST /api/locations
# ---------------------------------------------------------------------------

@api_bp.route("/locations", methods=["POST"])
def create_location():
    """
    Persist a new location and compute + cache its solar estimate.

    JSON body:
        name               (str, required)
        latitude           (float, required)
        longitude          (float, required)
        system_capacity_kw (float, optional, default 4.0)
    """
    body = request.get_json(silent=True) or {}

    # --- Validate -----------------------------------------------------------
    errors = []
    name = body.get("name", "").strip()
    if not name:
        errors.append("'name' is required and must be a non-empty string.")

    try:
        latitude = float(body["latitude"])
    except (KeyError, ValueError, TypeError):
        errors.append("'latitude' is required and must be a valid float.")

    try:
        longitude = float(body["longitude"])
    except (KeyError, ValueError, TypeError):
        errors.append("'longitude' is required and must be a valid float.")

    if errors:
        return jsonify({"errors": errors}), 400

    system_capacity_kw = float(body.get("system_capacity_kw", 4.0))
    system_capacity_kw = max(0.5, min(system_capacity_kw, 500.0))

    # --- Fetch solar data (live NREL if key present, mock otherwise) --------
    solar = fetch_solar_payload(
        lat=latitude,
        lon=longitude,
        system_capacity=system_capacity_kw,
    )
    outputs = solar["outputs"]
    monthly_kwh_json = json.dumps(outputs["ac_monthly"])

    # --- Persist to SQLite --------------------------------------------------
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO locations (name, latitude, longitude, system_capacity_kw)
            VALUES (?, ?, ?, ?)
            """,
            (name, latitude, longitude, system_capacity_kw),
        )
        location_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO solar_estimates
                (location_id, annual_kwh, monthly_kwh, ac_annual, solrad_annual)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                location_id,
                outputs["ac_annual"],
                monthly_kwh_json,
                outputs["ac_annual"],
                outputs["solrad_annual"],
            ),
        )
        conn.commit()

    return jsonify({
        "id": location_id,
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "system_capacity_kw": system_capacity_kw,
        "solar": solar,
    }), 201


# ---------------------------------------------------------------------------
# GET /api/locations
# ---------------------------------------------------------------------------

@api_bp.route("/locations", methods=["GET"])
def list_locations():
    """
    Return all saved locations with their latest solar estimate.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                l.id,
                l.name,
                l.latitude,
                l.longitude,
                l.system_capacity_kw,
                l.created_at,
                e.annual_kwh,
                e.monthly_kwh,
                e.solrad_annual
            FROM locations l
            LEFT JOIN solar_estimates e ON e.location_id = l.id
            ORDER BY l.created_at DESC
            """
        ).fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        # Parse the stored JSON string back into a list
        if d.get("monthly_kwh"):
            d["monthly_kwh"] = json.loads(d["monthly_kwh"])
        results.append(d)

    return jsonify(results), 200


# ---------------------------------------------------------------------------
# DELETE /api/locations/<id>
# ---------------------------------------------------------------------------

@api_bp.route("/locations/<int:location_id>", methods=["DELETE"])
def delete_location(location_id: int):
    """
    Delete a location by ID. Solar estimates are removed via CASCADE.
    """
    with get_db() as conn:
        result = conn.execute(
            "SELECT id FROM locations WHERE id = ?", (location_id,)
        ).fetchone()

        if result is None:
            return jsonify({"error": f"Location {location_id} not found."}), 404

        conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
        conn.commit()

    return jsonify({"deleted": location_id}), 200


# ---------------------------------------------------------------------------
# GET /api/status  — reports live vs mock mode to the frontend
# ---------------------------------------------------------------------------

@api_bp.route("/status", methods=["GET"])
def api_status():
    """
    Probe NREL connectivity and return whether the app is in live or mock mode.
    The frontend uses this to show a status badge on load.
    """
    api_key = current_app.config.get("NREL_API_KEY", "")
    has_key = bool(api_key)
    nrel_reachable = False

    if has_key:
        try:
            # Lightweight DNS-only probe — no quota used
            probe = http_client.get(
                NREL_PVWATTS_URL,
                params={"api_key": api_key, "lat": 40, "lon": -105,
                        "system_capacity": 1, "module_type": 0,
                        "losses": 14, "array_type": 0, "tilt": 20},
                timeout=5,
            )
            nrel_reachable = probe.status_code < 500
        except Exception:
            nrel_reachable = False

    mode = "live" if (has_key and nrel_reachable) else "mock"
    return jsonify({
        "mode"          : mode,
        "has_api_key"   : has_key,
        "nrel_reachable": nrel_reachable,
        "message"       : (
            "Connected to NREL PVWatts v8 API — data is real."
            if mode == "live" else
            "NREL unreachable — using simulated data (key is set)."
            if has_key else
            "No NREL API key — using simulated data."
        ),
    }), 200
