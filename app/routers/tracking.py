"""Public tracking endpoints — no authentication required.

GET /track/{tracking_token}        read-only incident status + live positions
WS  /track/{tracking_token}/live   real-time location stream via Redis pub/sub
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.incident_responses import IncidentResponse, ResponseStatus
from app.models.incidents import IncidentStatus
from app.redis_client import get_redis
from app.schemas.tracking import ShieldTrackingInfo, TrackingResponse
from app.services import incident_service
from app.services import navigation_service

logger = logging.getLogger(__name__)

router = APIRouter()

# TODO V2: rate-limit this endpoint — max 60 requests per minute per IP


def _incident_person_loc_key(incident_id: str) -> str:
    return f"shieldher:incident:location:{incident_id}"


def _incident_shield_loc_key(incident_id: str, shield_id: str) -> str:
    return f"shieldher:incident:{incident_id}:shield:{shield_id}:location"


def _incident_updates_channel(incident_id: str) -> str:
    return f"shieldher:incident:{incident_id}:updates"


@router.get("/{tracking_token}", response_model=TrackingResponse)
async def get_tracking_page(
    tracking_token: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TrackingResponse:
    """Public read-only incident tracking — no auth required.

    Returns anonymised incident data: no names, phones, or user IDs.
    """
    # TODO V2: tokens for resolved incidents expire after 24 hours
    incident = await incident_service.get_by_tracking_token(db, tracking_token)
    if incident is None:
        raise HTTPException(status_code=404, detail="Tracking link not found")

    person_lat: float | None = None
    person_lng: float | None = None
    shields: list[ShieldTrackingInfo] = []

    if incident.status == IncidentStatus.resolved:
        return TrackingResponse(
            incident_id=incident.id,
            status="resolved",
            person_lat=None,
            person_lng=None,
            responding_shields=[],
            convergence_lat=incident.convergence_lat,
            convergence_lng=incident.convergence_lng,
            triggered_at=incident.triggered_at,
            resolved_at=incident.resolved_at,
        )

    person_loc: dict[str, str] = await redis.hgetall(
        _incident_person_loc_key(str(incident.id))
    )
    if person_loc:
        person_lat = float(person_loc["lat"])
        person_lng = float(person_loc["lng"])
    else:
        person_lat = incident.trigger_lat
        person_lng = incident.trigger_lng

    rows = (
        await db.execute(
            select(IncidentResponse).where(
                IncidentResponse.incident_id == incident.id,
                IncidentResponse.status.in_(
                    [ResponseStatus.responding, ResponseStatus.arrived]
                    if hasattr(ResponseStatus, "arrived")
                    else [ResponseStatus.responding]
                ),
            )
        )
    ).scalars().all()

    conv_lat = incident.convergence_lat
    conv_lng = incident.convergence_lng

    for idx, resp in enumerate(rows, start=1):
        loc: dict[str, str] = await redis.hgetall(
            _incident_shield_loc_key(str(incident.id), str(resp.shield_id))
        )
        s_lat = float(loc["lat"]) if loc else None
        s_lng = float(loc["lng"]) if loc else None

        eta_seconds: int | None = None
        if (
            s_lat is not None
            and s_lng is not None
            and conv_lat is not None
            and conv_lng is not None
        ):
            eta_seconds = await navigation_service.get_eta_seconds(
                s_lat, s_lng, conv_lat, conv_lng
            )

        shields.append(
            ShieldTrackingInfo(
                shield_index=idx,
                lat=s_lat,
                lng=s_lng,
                eta_seconds=eta_seconds,
                status=resp.status.value,
            )
        )

    return TrackingResponse(
        incident_id=incident.id,
        status=incident.status.value,
        person_lat=person_lat,
        person_lng=person_lng,
        responding_shields=shields,
        convergence_lat=conv_lat,
        convergence_lng=conv_lng,
        triggered_at=incident.triggered_at,
        resolved_at=incident.resolved_at,
    )


@router.websocket("/{tracking_token}/live")
async def tracking_live_ws(
    tracking_token: str,
    websocket: WebSocket,
    redis: aioredis.Redis = Depends(get_redis),
) -> None:
    """Public WebSocket for live tracking updates — no auth required.

    Subscribes to the incident's Redis pub/sub channel and forwards
    shield_location, person_location, convergence_update, and
    incident_resolved messages to the tracking page client.

    DB session is scoped to the initial lookup only so we don't hold a
    connection-pool slot for the entire WebSocket lifetime.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        incident = await incident_service.get_by_tracking_token(db, tracking_token)

    if not incident:
        await websocket.accept()
        await websocket.close(code=4004)
        return

    if incident.status == IncidentStatus.resolved:
        await websocket.accept()
        await websocket.send_json({"type": "incident_resolved", "data": {}})
        await websocket.close(code=1000)
        return

    await websocket.accept()

    channel = _incident_updates_channel(str(incident.id))
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    async def _relay_pubsub() -> None:
        """Forward Redis pub/sub messages to the WebSocket client."""
        try:
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    await websocket.send_json(data)
                    if data.get("type") == "incident_resolved":
                        await websocket.close(code=1000)
                        return
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, Exception):
            pass

    relay_task = asyncio.create_task(_relay_pubsub())

    try:
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=30.0
                )
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        relay_task.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
