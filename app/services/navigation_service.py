"""Navigation service — convergence point calculation and Google Maps Routes API.

Responsibilities:
  calculate_convergence_point  → weighted centroid (person 2x, each shield 1x)
  get_directions               → Google Maps Routes API with MOCK_MAPS fallback
  get_eta_seconds              → wraps get_directions; falls back to Haversine / 1.4 m/s
"""

import logging
from typing import Any

import httpx

from app.config import settings
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)

_WALKING_SPEED_MS: float = 1.4  # metres per second ≈ 5 km/h
_ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_ROUTES_FIELD_MASK = "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline"
_OSRM_API_URL = "https://router.project-osrm.org/route/v1/foot/{lng1},{lat1};{lng2},{lat2}"
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

    body = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
        "travelMode": "WALK",
        "languageCode": "en-US",
        "units": "METRIC",
    }
    headers = {
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": _ROUTES_FIELD_MASK,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(_ROUTES_API_URL, json=body, headers=headers)
            resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        if not data.get("routes"):
            raise ValueError(f"Routes API returned no routes: {data!r}")

        route = data["routes"][0]
        duration_str: str = route.get("duration", "0s")
        duration_seconds = int(duration_str.rstrip("s"))
        encoded_polyline: str = route["polyline"]["encodedPolyline"]
        return {
            "distance_meters": int(route.get("distanceMeters", 0)),
            "duration_seconds": duration_seconds,
            "polyline": encoded_polyline,
            "steps": [],
        }
    except Exception as google_exc:
        logger.warning(
            "Google Routes API failed (%s) — falling back to OSRM", google_exc
        )
        return await _osrm_directions(origin_lat, origin_lng, dest_lat, dest_lng)


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

async def _osrm_directions(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict[str, Any]:
    """Fetch walking directions from the public OSRM demo server (no API key needed)."""
    url = _OSRM_API_URL.format(
        lng1=origin_lng, lat1=origin_lat,
        lng2=dest_lng,   lat2=dest_lat,
    )
    params = {"overview": "full", "geometries": "polyline"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()

    data: dict[str, Any] = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"OSRM returned no routes: {data!r}")

    route = data["routes"][0]
    return {
        "distance_meters": int(route.get("distance", 0)),
        "duration_seconds": int(route.get("duration", 0)),
        "polyline": route["geometry"],
        "steps": [],
    }


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
