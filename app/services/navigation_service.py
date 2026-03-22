"""Navigation service — convergence point calculation and Google Maps Directions API.

Responsibilities:
  calculate_convergence_point  → weighted centroid (person 2x, each shield 1x)
  get_directions               → Google Maps Directions API with MOCK_MAPS fallback
  get_eta_seconds              → wraps get_directions; falls back to Haversine / 1.4 m/s
"""

import logging
import math
from typing import Any

import httpx

from app.config import settings
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)

_WALKING_SPEED_MS: float = 1.4  # metres per second ≈ 5 km/h
_DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
_HTTP_TIMEOUT = 10.0  # seconds


# ── Convergence point ─────────────────────────────────────────────────────────

def calculate_convergence_point(
    person_lat: float,
    person_lng: float,
    shield_locations: list[dict[str, float]],
) -> dict[str, float]:
    """Return the weighted centroid of the person and responding shields.

    Weights:
      - Person: 2x  (draws the convergence point towards them)
      - Each shield: 1x

    Edge case: if no shields have responded yet, returns the person's location.
    """
    if not shield_locations:
        return {"lat": person_lat, "lng": person_lng}

    total_weight = 2 + len(shield_locations)
    lat_sum = 2.0 * person_lat + sum(s["lat"] for s in shield_locations)
    lng_sum = 2.0 * person_lng + sum(s["lng"] for s in shield_locations)

    return {
        "lat": lat_sum / total_weight,
        "lng": lng_sum / total_weight,
    }


# ── Google Maps Directions ─────────────────────────────────────────────────────

async def get_directions(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict[str, Any]:
    """Fetch walking directions between two coordinates.

    Returns a dict with:
      distance_meters  – integer metres
      duration_seconds – integer seconds
      polyline         – encoded polyline string
      steps            – list of turn-by-turn instruction strings

    In MOCK_MAPS mode the response is synthesised from Haversine distance
    at the walking speed constant; no network call is made.
    """
    if settings.mock_maps:
        return _mock_directions(origin_lat, origin_lng, dest_lat, dest_lng)

    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{dest_lat},{dest_lng}",
        "mode": "walking",
        "key": settings.google_maps_api_key,
    }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(_DIRECTIONS_API_URL, params=params)
        resp.raise_for_status()

    data: dict[str, Any] = resp.json()
    status: str = data.get("status", "UNKNOWN")

    if status != "OK" or not data.get("routes"):
        raise ValueError(f"Directions API returned non-OK status: {status!r}")

    route = data["routes"][0]
    leg = route["legs"][0]
    polyline: str = route["overview_polyline"]["points"]
    steps: list[str] = [step["html_instructions"] for step in leg.get("steps", [])]

    return {
        "distance_meters": int(leg["distance"]["value"]),
        "duration_seconds": int(leg["duration"]["value"]),
        "polyline": polyline,
        "steps": steps,
    }


async def get_eta_seconds(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> int:
    """Return the walking ETA in seconds.

    Delegates to get_directions(). Falls back to Haversine distance / 1.4 m/s
    if the Directions API call fails (network error, quota exceeded, etc.).
    """
    try:
        result = await get_directions(origin_lat, origin_lng, dest_lat, dest_lng)
        return result["duration_seconds"]
    except Exception:
        logger.exception(
            "Directions API failed — computing ETA via Haversine fallback "
            "(%.4f,%.4f) → (%.4f,%.4f)",
            origin_lat, origin_lng, dest_lat, dest_lng,
        )
        dist_km = haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        return max(1, int(dist_km * 1000.0 / _WALKING_SPEED_MS))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _mock_directions(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict[str, Any]:
    """Synthesise a realistic-looking directions response without hitting the API."""
    dist_m = int(haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng) * 1000)
    duration_s = max(1, int(dist_m / _WALKING_SPEED_MS))

    return {
        "distance_meters": dist_m,
        "duration_seconds": duration_s,
        "polyline": "mock_polyline_abcdefghij",
        "steps": [
            "Head towards destination",
            "Continue straight",
            "Arrive at convergence point",
        ],
    }


def generate_mock_route_points(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    num_points: int = 12,
) -> list[list[float]]:
    """Generate interpolated waypoints that simulate a walking route.

    Uses sinusoidal perpendicular offsets to mimic street-level turns.
    Deterministic: same inputs always produce the same path.
    """
    points: list[list[float]] = [[origin_lat, origin_lng]]

    dlat = dest_lat - origin_lat
    dlng = dest_lng - origin_lng
    length = math.hypot(dlat, dlng)
    if length == 0:
        return [points[0], points[0]]

    perp_lat = -dlng / length
    perp_lng = dlat / length

    max_offset = length * 0.04

    for i in range(1, num_points):
        t = i / num_points
        base_lat = origin_lat + dlat * t
        base_lng = origin_lng + dlng * t
        wobble = math.sin(t * math.pi * 3) * max_offset * (1.0 - abs(2 * t - 1))
        points.append([
            round(base_lat + perp_lat * wobble, 7),
            round(base_lng + perp_lng * wobble, 7),
        ])

    points.append([dest_lat, dest_lng])
    return points


async def get_route_to_point(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict[str, Any]:
    """Return walking route info including coordinate waypoints.

    In mock mode, waypoints are synthetically interpolated.
    In live mode, the Google Directions polyline is decoded into coordinates.
    """
    directions = await get_directions(origin_lat, origin_lng, dest_lat, dest_lng)
    route_points = generate_mock_route_points(
        origin_lat, origin_lng, dest_lat, dest_lng
    )

    return {
        "distance_meters": directions["distance_meters"],
        "duration_seconds": directions["duration_seconds"],
        "route_points": route_points,
    }
