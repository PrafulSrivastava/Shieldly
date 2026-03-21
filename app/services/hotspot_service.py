"""Hotspot tracking and Gemini AI safety summary service.

Geohash precision
-----------------
All public functions in this module use precision **6** (~1.2 km cells), giving
a coarser but more statistically meaningful picture than the per-incident
precision-7 (~150 m) write used during incident resolution.
"""

import logging
from datetime import datetime
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.models.hotspot_data import HotspotData
from app.utils.geo import encode_geohash, geohash_neighbors

logger = logging.getLogger(__name__)

_GEOHASH_PRECISION = 6
_MOCK_GEMINI_RESPONSE = (
    "This area has seen some recent activity; consider walking on "
    "well-lit streets and staying alert, especially during late-night hours."
)
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _risk_level(total: int) -> Literal["low", "medium", "high"]:
    if total > 5:
        return "high"
    if total >= 2:
        return "medium"
    return "low"


def _format_peak_hour(peak_hour: int | None) -> str:
    """Return a human-readable time window string, e.g. '22:00–00:00'."""
    if peak_hour is None:
        return "unknown hours"
    end_hour = (peak_hour + 2) % 24
    return f"{peak_hour:02d}:00\u2013{end_hour:02d}:00"


# ── Public service functions ──────────────────────────────────────────────────

async def log_incident_to_hotspot(
    lat: float,
    lng: float,
    triggered_at: datetime,
    *,
    db: AsyncSession,
) -> None:
    """Upsert the hotspot_data row for the geohash-6 cell containing (lat, lng).

    Increments incident_count, advances last_incident, and increments the
    hour-of-day bucket in time_distribution.  Safe to call inside an existing
    transaction — the caller is responsible for committing.
    """
    geohash = encode_geohash(lat, lng, precision=_GEOHASH_PRECISION)
    hour_key = str(triggered_at.hour)

    result = await db.execute(
        select(HotspotData).where(HotspotData.geohash == geohash)
    )
    hotspot: HotspotData | None = result.scalar_one_or_none()

    if hotspot is not None:
        time_dist: dict[str, int] = dict(hotspot.time_distribution or {})
        time_dist[hour_key] = time_dist.get(hour_key, 0) + 1
        hotspot.incident_count += 1
        hotspot.last_incident = triggered_at
        hotspot.time_distribution = time_dist
        # Explicit flag required so SQLAlchemy detects JSONB mutation
        flag_modified(hotspot, "time_distribution")
    else:
        db.add(
            HotspotData(
                geohash=geohash,
                incident_count=1,
                last_incident=triggered_at,
                time_distribution={hour_key: 1},
            )
        )


async def get_hotspot_summary(
    lat: float,
    lng: float,
    radius_geohashes: int = 1,
    *,
    db: AsyncSession,
) -> dict[str, Any]:
    """Aggregate hotspot data across the centre cell and its 8 neighbours.

    ``radius_geohashes`` is accepted for forward-compatibility but currently
    only the immediate ring of 8 cells is queried regardless of its value.

    Returns::

        {
            "total_incidents": int,
            "last_incident":   datetime | None,
            "peak_hour":       int | None,
            "risk_level":      "low" | "medium" | "high",
        }
    """
    center = encode_geohash(lat, lng, precision=_GEOHASH_PRECISION)
    cells: list[str] = [center, *geohash_neighbors(center)]

    result = await db.execute(
        select(HotspotData).where(HotspotData.geohash.in_(cells))
    )
    rows: list[HotspotData] = list(result.scalars().all())

    total_incidents = sum(r.incident_count for r in rows)
    last_incident: datetime | None = None
    combined_time_dist: dict[int, int] = {}

    for row in rows:
        if row.last_incident is not None:
            if last_incident is None or row.last_incident > last_incident:
                last_incident = row.last_incident
        for hour_str, count in (row.time_distribution or {}).items():
            hour = int(hour_str)
            combined_time_dist[hour] = combined_time_dist.get(hour, 0) + count

    peak_hour: int | None = (
        max(combined_time_dist, key=lambda h: combined_time_dist[h])
        if combined_time_dist
        else None
    )

    return {
        "total_incidents": total_incidents,
        "last_incident": last_incident,
        "peak_hour": peak_hour,
        "risk_level": _risk_level(total_incidents),
    }


async def get_gemini_safety_context(
    lat: float,
    lng: float,
    *,
    db: AsyncSession,
    summary: dict[str, Any] | None = None,
) -> str:
    """Return a Gemini AI safety awareness message for the given location.

    Callers may pass a pre-fetched ``summary`` dict (from ``get_hotspot_summary``)
    to avoid a redundant DB round-trip.  If omitted the summary is fetched here.

    Behaviour:
    - ``total_incidents == 0``  → returns a reassuring string, no Gemini call.
    - ``MOCK_GEMINI=true``      → returns a hardcoded example string.
    - Otherwise                 → calls the Gemini 1.5 Flash API.  On any error
      the exception is logged and a safe fallback string is returned.
    """
    if summary is None:
        summary = await get_hotspot_summary(lat, lng, db=db)

    if summary["total_incidents"] == 0:
        return (
            "No safety incidents have been recorded in this area recently \u2014 "
            "stay aware of your surroundings and trust your instincts."
        )

    if settings.mock_gemini:
        return _MOCK_GEMINI_RESPONSE

    count: int = summary["total_incidents"]
    peak_hours_text = _format_peak_hour(summary.get("peak_hour"))

    prompt = (
        f"You are a safety assistant. This area has had {count} safety incidents "
        f"in the last 30 days, mostly between hours {peak_hours_text}. "
        "Write a calm, factual 1-sentence safety awareness message for a woman "
        "walking alone here. Do not be alarmist."
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _GEMINI_URL,
                params={"key": settings.gemini_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        logger.exception(
            "Gemini API call failed for hotspot context at (%.6f, %.6f)", lat, lng
        )
        return "Exercise normal caution in this area and stay aware of your surroundings."
