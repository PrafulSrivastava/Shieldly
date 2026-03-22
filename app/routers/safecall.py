"""SafeCall voice agent router — safety update endpoints.

POST /{incident_id}/update      agent posts extracted safety data
GET  /{incident_id}/latest      latest safety update for the incident
GET  /{incident_id}/history     all safety updates for the incident
"""

import logging
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.users import User
from app.redis_client import get_redis
from app.routers.auth import get_current_user
from app.schemas.safecall import (
    LatestSafetyUpdateResponse,
    SafetyUpdateHistoryResponse,
    SafetyUpdateRequest,
    SafetyUpdateResponse,
)
from app.services import safecall_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/{incident_id}/update",
    response_model=SafetyUpdateResponse,
    status_code=201,
)
async def post_safety_update(
    incident_id: UUID,
    body: SafetyUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SafetyUpdateResponse:
    """Receive a safety update from the SafeCall agent.

    The agent extracts safety info (threat description, location, distress
    level) from the voice conversation every few seconds and posts it here.

    Requires: authenticated person who owns the incident.
    """
    return await safecall_service.receive_safety_update(
        incident_id, user, body, db=db, redis=redis
    )


@router.get(
    "/{incident_id}/latest",
    response_model=LatestSafetyUpdateResponse,
)
async def get_latest_safety_update(
    incident_id: UUID,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> LatestSafetyUpdateResponse:
    """Return the most recent safety update for the incident.

    Requires: any authenticated user (person or shield).
    """
    return await safecall_service.get_latest_safety_update(
        incident_id, redis=redis
    )


@router.get(
    "/{incident_id}/history",
    response_model=SafetyUpdateHistoryResponse,
)
async def get_safety_update_history(
    incident_id: UUID,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> SafetyUpdateHistoryResponse:
    """Return the full history of safety updates for the incident.

    Requires: any authenticated user (person or shield).
    """
    return await safecall_service.get_safety_update_history(
        incident_id, redis=redis
    )
