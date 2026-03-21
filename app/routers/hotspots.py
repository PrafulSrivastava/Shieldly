"""Hotspots router — area safety context endpoints.

GET /hotspots/context?lat=&lng=
    Returns risk level, incident count, a Gemini AI safety summary, and the
    count of active Shields within 1 km.

GET /hotspots/summary?lat=&lng=
    Lightweight single-cell lookup with Gemini one-sentence zone summary.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.users import User
from app.routers.auth import get_current_user
from app.schemas.hotspots import HotspotContextResponse, HotspotSummaryResponse
from app.services import hotspot_service, location_service

logger = logging.getLogger(__name__)

router = APIRouter()

_SHIELD_NEARBY_RADIUS_KM = 1.0


@router.get("/context", response_model=HotspotContextResponse)
async def get_hotspot_context(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude of the queried point"),
    lng: float = Query(..., ge=-180.0, le=180.0, description="Longitude of the queried point"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HotspotContextResponse:
    """Return safety context for the given location.

    Aggregates incident history across the centre geohash cell and its 8
    neighbours (~3×3 km grid), generates an AI safety message via Gemini, and
    reports how many active Shields are within 1 km.

    Requires: **authenticated user** (any role).
    """
    summary = await hotspot_service.get_hotspot_summary(lat, lng, db=db)
    gemini_text = await hotspot_service.get_gemini_safety_context(
        lat, lng, db=db, summary=summary
    )
    nearby_shields = await location_service.get_active_shields_near(
        lat, lng, _SHIELD_NEARBY_RADIUS_KM, db=db
    )

    return HotspotContextResponse(
        risk_level=summary["risk_level"],
        total_incidents=summary["total_incidents"],
        gemini_summary=gemini_text,
        shield_count_nearby=len(nearby_shields),
    )


@router.get("/summary", response_model=HotspotSummaryResponse)
async def get_hotspot_summary_endpoint(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude"),
    lng: float = Query(..., ge=-180.0, le=180.0, description="Longitude"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HotspotSummaryResponse:
    """Single-cell hotspot lookup with a Gemini one-sentence zone summary.

    Converts the coordinates to a geohash-6 cell and checks for recorded
    incidents.  If the cell has fewer than 2 incidents, ``summary`` is null.
    Otherwise a concise, non-alarmist safety sentence is generated via Gemini
    (3-second timeout; silent fallback to null on failure).

    Requires: **authenticated user** (any role).
    """
    data = await hotspot_service.get_zone_summary(lat, lng, db=db)
    return HotspotSummaryResponse(**data)
