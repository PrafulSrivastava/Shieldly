"""SafeCall voice agent safety update service.

Handles receiving, storing, and broadcasting safety updates
extracted by the SafeCall agent during an active incident.
"""

import json
import logging
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incidents import Incident, IncidentStatus
from app.models.users import User
from app.schemas.safecall import (
    LatestSafetyUpdateResponse,
    SafetyUpdateHistoryResponse,
    SafetyUpdateRecord,
    SafetyUpdateRequest,
    SafetyUpdateResponse,
)

logger = logging.getLogger(__name__)

_SAFECALL_TTL = 24 * 3600  # 24 hours — matches incident state TTL


# ── Redis key helpers ────────────────────────────────────────────────────────

def _latest_key(incident_id: UUID | str) -> str:
    return f"shieldher:incident:{incident_id}:safecall:latest"


def _history_key(incident_id: UUID | str) -> str:
    return f"shieldher:incident:{incident_id}:safecall:history"


def _count_key(incident_id: UUID | str) -> str:
    return f"shieldher:incident:{incident_id}:safecall:count"


def _updates_channel(incident_id: UUID | str) -> str:
    return f"shieldher:incident:{incident_id}:updates"


# ── Public service functions ─────────────────────────────────────────────────

async def receive_safety_update(
    incident_id: UUID,
    user: User,
    body: SafetyUpdateRequest,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SafetyUpdateResponse:
    """Validate the incident, store the update in Redis, and broadcast via pub/sub."""

    # Validate incident exists, is active, and is owned by this user
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident: Incident | None = result.scalar_one_or_none()

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status != IncidentStatus.active:
        raise HTTPException(status_code=409, detail="Incident is not active")
    if incident.triggered_by != user.id:
        raise HTTPException(status_code=403, detail="Not the incident owner")

    # Increment update counter
    update_number = await redis.incr(_count_key(incident_id))

    # Build the record
    record = SafetyUpdateRecord(
        update_number=update_number,
        timestamp=body.timestamp,
        extracted=body.extracted,
        transcript_length=body.transcript_length,
    )
    record_json = record.model_dump_json()

    # Pipeline: SET latest, RPUSH history, EXPIRE all keys
    pipe = redis.pipeline()
    pipe.set(_latest_key(incident_id), record_json, ex=_SAFECALL_TTL)
    pipe.rpush(_history_key(incident_id), record_json)
    pipe.expire(_history_key(incident_id), _SAFECALL_TTL)
    pipe.expire(_count_key(incident_id), _SAFECALL_TTL)
    await pipe.execute()

    # Broadcast via pub/sub on the existing incident updates channel
    pub_message = json.dumps({
        "type": "safety_update",
        "data": record.model_dump(mode="json"),
    })
    await redis.publish(_updates_channel(incident_id), pub_message)

    logger.info(
        "SafeCall update #%d for incident %s (transcript: %d turns)",
        update_number, incident_id, body.transcript_length,
    )

    return SafetyUpdateResponse(
        status="received",
        update_number=update_number,
        incident_id=incident_id,
    )


async def get_latest_safety_update(
    incident_id: UUID,
    *,
    redis: aioredis.Redis,
) -> LatestSafetyUpdateResponse:
    """Return the most recent safety update for the incident, or None."""
    raw: bytes | None = await redis.get(_latest_key(incident_id))
    update = SafetyUpdateRecord.model_validate_json(raw) if raw else None
    return LatestSafetyUpdateResponse(incident_id=incident_id, update=update)


async def get_safety_update_history(
    incident_id: UUID,
    *,
    redis: aioredis.Redis,
) -> SafetyUpdateHistoryResponse:
    """Return all safety updates for the incident in chronological order."""
    raw_list: list[bytes] = await redis.lrange(_history_key(incident_id), 0, -1)
    updates = [SafetyUpdateRecord.model_validate_json(r) for r in raw_list]
    return SafetyUpdateHistoryResponse(
        incident_id=incident_id,
        total=len(updates),
        updates=updates,
    )
