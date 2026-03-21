"""Incidents router — SOS lifecycle endpoints.

POST /trigger               person triggers SOS
POST /{id}/respond          shield accepts or declines
POST /{id}/all-clear        person marks incident resolved
GET  /{id}                  full incident state + ETAs
"""

import logging
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.shields import Shield
from app.models.users import User, UserRole
from app.redis_client import get_redis
from app.routers.auth import get_current_user, require_shield
from app.schemas.incidents import (
    AllClearResponse,
    IncidentDetailResponse,
    RespondToIncidentRequest,
    RespondToIncidentResponse,
    TriggerSOSRequest,
    TriggerSOSResponse,
)
from app.services import incident_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/trigger", response_model=TriggerSOSResponse, status_code=201)
async def trigger_sos(
    body: TriggerSOSRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TriggerSOSResponse:
    """Trigger an SOS alert — creates the incident and notifies nearby Shields.

    Requires role: **person**.
    """
    if user.role != UserRole.person:
        raise HTTPException(
            status_code=403, detail="Only persons can trigger an SOS alert"
        )
    return await incident_service.trigger_sos(
        user, body.lat, body.lng, db=db, redis=redis, background_tasks=background_tasks
    )


@router.post(
    "/{incident_id}/respond",
    responses={
        200: {"model": RespondToIncidentResponse, "description": "Shield is responding"},
        204: {"description": "Shield declined — no body"},
    },
)
async def respond_to_incident(
    incident_id: UUID,
    body: RespondToIncidentRequest,
    shield: Shield = Depends(require_shield),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RespondToIncidentResponse | Response:
    """Shield responds to an active SOS.

    - **responding**: updates status, recalculates convergence point, returns
      the new centroid and other responding shields.
    - **declined**: updates status, returns HTTP 204.

    Requires role: **shield** (verified).
    """
    result = await incident_service.update_response_status(
        shield, incident_id, body.action, db=db, redis=redis
    )
    if result is None:
        return Response(status_code=204)
    return result


@router.post("/{incident_id}/all-clear", response_model=AllClearResponse)
async def all_clear(
    incident_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AllClearResponse:
    """Person marks the incident resolved.

    Notifies responding Shields, sends SMS to the emergency contact, logs the
    hotspot bucket, and clears the Redis incident cache.

    Requires role: **person** (must be the incident owner).
    """
    await incident_service.resolve_incident(
        user,
        incident_id,
        db=db,
        redis=redis,
        background_tasks=background_tasks,
    )
    return AllClearResponse()


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> IncidentDetailResponse:
    """Return full incident state.

    Includes responding shields, their last-known positions, stub walking ETAs
    (straight-line distance ÷ 5 km/h), and the current convergence point.

    Requires: authenticated user (person or shield).
    """
    return await incident_service.get_incident_detail(
        incident_id, db=db, redis=redis
    )
