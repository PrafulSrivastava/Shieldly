"""Location router — live GPS position updates and retrieval."""

import logging
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.incident_responses import IncidentResponse, ResponseStatus
from app.models.incidents import Incident, IncidentStatus
from app.models.shields import Shield
from app.models.users import User
from app.redis_client import get_redis
from app.routers.auth import get_current_user, require_shield
from app.schemas.location import (
    IncidentLocationsResponse,
    NearbyShieldResponse,
    PersonLocationResponse,
    ShieldLocationResponse,
    UpdateLocationRequest,
)
from app.services.incident_service import compute_context_update_if_needed
from app.services.location_service import (
    get_active_shields_near,
    get_incident_all_locations,
    update_person_location,
    update_responding_shield_location,
    update_shield_location,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── PATCH /location/shield ────────────────────────────────────────────────────

@router.patch("/shield", status_code=204)
async def update_shield_live_location(
    body: UpdateLocationRequest,
    shield: Shield = Depends(require_shield),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Update the authenticated shield's GPS coordinates.

    Writes to Redis (with 5-min TTL) and asynchronously persists to Postgres.
    If the shield is currently responding to one or more active incidents their
    updated position is also broadcast on each incident's update channel so
    that the person and other shields see the movement in real-time.
    """
    await update_shield_location(
        shield_id=str(shield.id),
        lat=body.lat,
        lng=body.lng,
        redis=redis,
    )

    # Broadcast to every incident this shield is actively responding to
    result = await db.execute(
        select(IncidentResponse).where(
            IncidentResponse.shield_id == shield.id,
            IncidentResponse.status == ResponseStatus.responding,
        )
    )
    active_responses = result.scalars().all()

    for resp in active_responses:
        ctx = await compute_context_update_if_needed(
            str(resp.incident_id), db=db, redis=redis,
        )
        await update_responding_shield_location(
            incident_id=str(resp.incident_id),
            shield_id=str(shield.id),
            lat=body.lat,
            lng=body.lng,
            redis=redis,
            context_update=ctx,
        )


# ── PATCH /location/incident/{incident_id} ────────────────────────────────────

@router.patch("/incident/{incident_id}", status_code=204)
async def update_incident_person_location(
    incident_id: UUID,
    body: UpdateLocationRequest,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Update the person's live location during their active incident.

    Only the user who triggered the incident may call this endpoint.
    """
    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.triggered_by == user.id,
            Incident.status == IncidentStatus.active,
        )
    )
    incident: Incident | None = result.scalar_one_or_none()

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Active incident not found or you are not the incident owner",
        )

    await update_person_location(
        incident_id=str(incident_id),
        lat=body.lat,
        lng=body.lng,
        redis=redis,
    )


# ── GET /location/incident/{incident_id}/all ──────────────────────────────────

@router.get(
    "/incident/{incident_id}/all",
    response_model=IncidentLocationsResponse,
)
async def get_incident_all_live_locations(
    incident_id: UUID,
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> IncidentLocationsResponse:
    """Return all live GPS positions for an active incident.

    Includes the person's last broadcast location and the positions of every
    shield currently in the ``responding`` state for this incident.
    Positions are read from Redis; a missing key means no update has been
    received yet (or the last update expired after 5 minutes of silence).
    """
    data = await get_incident_all_locations(
        incident_id=str(incident_id),
        redis=redis,
        db=db,
    )

    return IncidentLocationsResponse(
        incident_id=data["incident_id"],
        person=(
            PersonLocationResponse(**data["person"]) if data["person"] else None
        ),
        shields=[ShieldLocationResponse(**s) for s in data["shields"]],
    )


# ── GET /location/shields/nearby ─────────────────────────────────────────────

@router.get(
    "/shields/nearby",
    response_model=list[NearbyShieldResponse],
    summary="Get nearby active shields with positions",
)
async def get_nearby_shields(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lng: float = Query(..., ge=-180.0, le=180.0),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NearbyShieldResponse]:
    """Return active verified shields within ~3 km of the given coordinates.

    Used by the frontend to display shield blips on the idle-phase mini-map.
    """
    nearby = await get_active_shields_near(lat, lng, radius_km=3.0, db=db)
    return [NearbyShieldResponse(**s) for s in nearby]
