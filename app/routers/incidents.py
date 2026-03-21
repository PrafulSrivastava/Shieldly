"""Incidents router — SOS lifecycle endpoints.

POST /trigger               person triggers SOS
POST /{id}/respond          shield accepts or declines
POST /{id}/all-clear        person marks incident resolved
GET  /{id}                  full incident state + ETAs
GET  /{id}/elevenlabs-token signed URL for ElevenLabs Conversational AI
GET  /{id}/context          flat string context for ElevenLabs dynamicVariables
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
    ElevenLabsTokenResponse,
    IncidentContextResponse,
    IncidentDetailResponse,
    RespondToIncidentRequest,
    RespondToIncidentResponse,
    TriggerSOSRequest,
    TriggerSOSResponse,
)
from app.services import incident_service
from app.services.elevenlabs_service import get_signed_conversation_url

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
    response_model=None,
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
    hotspot bucket, and clears the Redis incident cache.  If Gemini returns a
    zone safety summary for the incident location it is included as
    ``zone_summary`` in the response.

    Requires role: **person** (must be the incident owner).
    """
    zone_summary = await incident_service.resolve_incident(
        user,
        incident_id,
        db=db,
        redis=redis,
        background_tasks=background_tasks,
    )
    return AllClearResponse(zone_summary=zone_summary)


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


@router.get(
    "/{incident_id}/elevenlabs-token",
    response_model=ElevenLabsTokenResponse,
)
async def get_elevenlabs_token(
    incident_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ElevenLabsTokenResponse:
    """Issue a short-lived signed URL for the ElevenLabs Conversational AI SDK.

    Only the incident owner may request a token.  The API key never leaves
    the server — the frontend receives only the signed WebSocket URL.
    """
    incident = await incident_service.require_incident_owner(incident_id, user, db=db)
    signed_url = await get_signed_conversation_url(incident.id, db)
    return ElevenLabsTokenResponse(signed_url=signed_url, incident_id=incident.id)


@router.get(
    "/{incident_id}/context",
    response_model=IncidentContextResponse,
)
async def get_incident_context(
    incident_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> IncidentContextResponse:
    """Return live incident data shaped for ElevenLabs dynamicVariables.

    All values are human-readable strings — no nested objects, no numbers,
    no nulls.  The frontend passes this dict directly to
    ``conversation.setVariables()``.
    """
    return await incident_service.get_incident_context(
        incident_id, db=db, redis=redis
    )
