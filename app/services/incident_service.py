"""Business logic for the incidents domain.

Covers the full SOS lifecycle:
  trigger_sos            → create incident, notify shields, cache state
  update_response_status → shield accepts/declines, recalculate convergence point
  resolve_incident       → all-clear from person, thank shields, log hotspot
  get_incident_detail    → read-only view with stub walking ETAs
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident_responses import IncidentResponse, ResponseStatus
from app.models.incidents import Incident, IncidentStatus
from app.models.shields import Shield
from app.models.users import User
from app.schemas.incidents import (
    ConvergencePoint,
    IncidentContextResponse,
    IncidentDetailResponse,
    RespondingShieldInfo,
    RespondToIncidentResponse,
    ShieldStatusInfo,
    TriggerSOSResponse,
)
from app.services.push_service import send_to_shield
from app.services.sms_service import (
    send_emergency_contact_all_clear,
    send_emergency_contact_sos,
)
from app.services.location_service import get_active_shields_near
from app.services import hotspot_service, navigation_service
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)

_INCIDENT_STATE_TTL = 24 * 3600  # seconds
_MIN_SHIELDS_TO_COVER = 3        # threshold that triggers "covered" push to remaining notified shields


# ── Redis key helpers ─────────────────────────────────────────────────────────

def _state_key(incident_id: UUID | str) -> str:
    return f"shieldher:incident:{incident_id}:state"


def _incident_shield_loc_key(incident_id: str, shield_id: str) -> str:
    return f"shieldher:incident:{incident_id}:shield:{shield_id}:location"


def _shield_loc_key(shield_id: str) -> str:
    return f"shieldher:shield:location:{shield_id}"


def _incident_person_loc_key(incident_id: str) -> str:
    return f"shieldher:incident:location:{incident_id}"


# ── Public service functions ──────────────────────────────────────────────────

async def trigger_sos(
    user: User,
    lat: float,
    lng: float,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    background_tasks: BackgroundTasks,
) -> TriggerSOSResponse:
    """Create an active incident and broadcast SOS to verified nearby Shields.

    Steps (in order as per spec):
      1. Create Incident row (status=active)
      2. Find active shields within 1 km — expands to 3 km if < 3 found
      3. Create IncidentResponse rows for each shield (status=notified)
      4. Fire push notifications concurrently (non-blocking, errors swallowed)
      5. Enqueue SMS to emergency contact as background task
      6. Cache incident state in Redis
      7. Return summary
    """
    # Step 1 — persist incident
    incident = Incident(
        triggered_by=user.id,
        trigger_lat=lat,
        trigger_lng=lng,
        status=IncidentStatus.active,
    )
    db.add(incident)
    await db.flush()  # assign UUID before child rows reference it

    # Step 2 — nearby shields (location_service handles radius expansion)
    nearby: list[dict[str, Any]] = await get_active_shields_near(
        lat, lng, radius_km=1.0, db=db
    )

    # Step 3 — one IncidentResponse per shield
    for s in nearby:
        db.add(
            IncidentResponse(
                incident_id=incident.id,
                shield_id=UUID(s["shield_id"]),
                status=ResponseStatus.notified,
            )
        )
    await db.flush()

    # Step 4 — push notifications (fire-and-forget; errors must not fail the request)
    await asyncio.gather(
        *[
            send_to_shield(
                UUID(s["shield_id"]),
                title="SOS Alert — Help Needed",
                body=f"Someone needs help {s['distance_km']:.1f} km away",
                data={
                    "type": "sos_alert",
                    "incident_id": str(incident.id),
                    "lat": incident.trigger_lat,
                    "lng": incident.trigger_lng,
                    "distance_km": round(s["distance_km"], 2),
                },
                db=db,
            )
            for s in nearby
        ],
        return_exceptions=True,
    )

    # Step 5 — SMS (background task; runs after response is sent)
    if user.emergency_contact_phone:
        background_tasks.add_task(
            send_emergency_contact_sos,
            incident_id=str(incident.id),
            person_name=user.name,
            contact_phone=user.emergency_contact_phone,
            lat=lat,
            lng=lng,
        )

    # Step 6 — Redis incident state cache
    await redis.set(
        _state_key(incident.id),
        json.dumps(
            {
                "incident_id": str(incident.id),
                "triggered_by": str(user.id),
                "trigger_lat": lat,
                "trigger_lng": lng,
                "status": IncidentStatus.active.value,
                "shields_notified": [s["shield_id"] for s in nearby],
                "convergence_lat": None,
                "convergence_lng": None,
            }
        ),
        ex=_INCIDENT_STATE_TTL,
    )

    # Step 7 — return
    return TriggerSOSResponse(
        incident_id=incident.id,
        shields_notified=len(nearby),
        convergence_point=None,
    )


async def update_response_status(
    shield: Shield,
    incident_id: UUID,
    action: str,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> RespondToIncidentResponse | None:
    """Handle a shield's response to an SOS.

    'responding' → update status, recalculate centroid, push 'covered' if ≥ 3
    'declined'   → update status, return None (caller converts to 204)
    """
    incident = await _require_active_incident(db, incident_id)
    response = await _require_notified_response(db, incident_id, shield.id)

    now = datetime.now(timezone.utc)

    if action == "declined":
        response.status = ResponseStatus.declined
        response.responded_at = now
        return None

    # ── action == "responding" ────────────────────────────────────────────────

    response.status = ResponseStatus.responding
    response.responded_at = now
    await db.flush()

    # Load all currently responding shields with their Shield + User records
    rows = (
        await db.execute(
            select(IncidentResponse, Shield, User.name)
            .join(Shield, IncidentResponse.shield_id == Shield.id)
            .join(User, Shield.user_id == User.id)
            .where(
                IncidentResponse.incident_id == incident_id,
                IncidentResponse.status == ResponseStatus.responding,
            )
        )
    ).all()

    # Weighted centroid: person 2x, each responding shield 1x
    shield_positions: list[dict[str, float]] = []
    responding_shields: list[RespondingShieldInfo] = []

    for inc_resp, shield_obj, name in rows:
        s_lat, s_lng = await _resolve_shield_position(
            redis,
            incident_id=str(incident_id),
            shield_id=str(shield_obj.id),
            fallback_lat=shield_obj.current_lat,
            fallback_lng=shield_obj.current_lng,
        )
        if s_lat is not None and s_lng is not None:
            shield_positions.append({"lat": s_lat, "lng": s_lng})
        responding_shields.append(
            RespondingShieldInfo(
                shield_id=inc_resp.shield_id,
                name=name,
                lat=s_lat,
                lng=s_lng,
            )
        )

    conv = navigation_service.calculate_convergence_point(
        incident.trigger_lat, incident.trigger_lng, shield_positions
    )
    conv_lat, conv_lng = conv["lat"], conv["lng"]

    # Persist convergence point
    incident.convergence_lat = conv_lat
    incident.convergence_lng = conv_lng

    # Update Redis cache
    await _patch_incident_state(
        redis,
        incident_id=incident_id,
        patch={"convergence_lat": conv_lat, "convergence_lng": conv_lng},
    )

    # If coverage threshold reached, tell remaining notified shields they're off the hook
    if len(rows) >= _MIN_SHIELDS_TO_COVER:
        await _send_covered_notifications(db, redis, incident_id=incident_id)

    other_shields = [s for s in responding_shields if s.shield_id != shield.id]
    return RespondToIncidentResponse(
        convergence_point=ConvergencePoint(lat=conv_lat, lng=conv_lng),
        other_responding_shields=other_shields,
    )


async def resolve_incident(
    user: User,
    incident_id: UUID,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    background_tasks: BackgroundTasks,
) -> None:
    """Mark the incident resolved.

    Steps:
      1. Validate ownership + active status
      2. Set status=resolved, resolved_at=now()
      3. Push 'she is safe' to all responding shields
      4. Enqueue SMS to emergency contact
      5. Upsert hotspot bucket (geohash + hour-of-day)
      6. Clear Redis incident cache
    """
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident: Incident | None = result.scalar_one_or_none()

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.triggered_by != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to resolve this incident"
        )
    if incident.status != IncidentStatus.active:
        raise HTTPException(status_code=409, detail="Incident is already resolved")

    now = datetime.now(timezone.utc)
    incident.status = IncidentStatus.resolved
    incident.resolved_at = now

    # Notify all responding shields
    responding = (
        await db.execute(
            select(IncidentResponse).where(
                IncidentResponse.incident_id == incident_id,
                IncidentResponse.status == ResponseStatus.responding,
            )
        )
    ).scalars().all()

    await asyncio.gather(
        *[
            send_to_shield(
                resp.shield_id,
                title="She is safe",
                body="She is safe — thank you",
                data={"type": "resolved", "incident_id": str(incident_id)},
                db=db,
            )
            for resp in responding
        ],
        return_exceptions=True,
    )

    # Background SMS
    if user.emergency_contact_phone:
        background_tasks.add_task(
            send_emergency_contact_all_clear,
            person_name=user.name,
            contact_phone=user.emergency_contact_phone,
        )

    # Hotspot logging
    await _increment_hotspot(db, lat=incident.trigger_lat, lng=incident.trigger_lng, now=now)

    # Clear Redis incident state + person location cache
    await asyncio.gather(
        redis.delete(_state_key(incident_id)),
        redis.delete(_incident_person_loc_key(str(incident_id))),
        return_exceptions=True,
    )


async def get_incident_detail(
    incident_id: UUID,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> IncidentDetailResponse:
    """Return full incident state with real ETAs via Google Maps Directions API.

    For each responding shield their ETA is calculated from their current position
    to the convergence point.  The person's encoded polyline to the same point is
    also included.  Both fall back gracefully when the API is unavailable.
    """
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident: Incident | None = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    rows = (
        await db.execute(
            select(IncidentResponse, Shield, User.name)
            .join(Shield, IncidentResponse.shield_id == Shield.id)
            .join(User, Shield.user_id == User.id)
            .where(IncidentResponse.incident_id == incident_id)
        )
    ).all()

    # Convergence point — only present once at least one shield is responding
    convergence_point: ConvergencePoint | None = None
    conv_lat: float = incident.trigger_lat
    conv_lng: float = incident.trigger_lng
    if incident.convergence_lat is not None and incident.convergence_lng is not None:
        conv_lat = incident.convergence_lat
        conv_lng = incident.convergence_lng
        convergence_point = ConvergencePoint(lat=conv_lat, lng=conv_lng)

    # Person's current position (live Redis hash → trigger point fallback)
    person_loc: dict[str, str] = await redis.hgetall(
        _incident_person_loc_key(str(incident_id))
    )
    person_lat = float(person_loc["lat"]) if person_loc else incident.trigger_lat
    person_lng = float(person_loc["lng"]) if person_loc else incident.trigger_lng

    # Person's encoded polyline to convergence point
    person_polyline: str | None = None
    if convergence_point is not None:
        try:
            directions = await navigation_service.get_directions(
                person_lat, person_lng, conv_lat, conv_lng
            )
            person_polyline = directions["polyline"]
        except Exception:
            logger.exception(
                "Failed to get person's polyline to convergence point for incident %s",
                incident_id,
            )

    # Per-shield ETAs to convergence point (responding shields only)
    shields_info: list[ShieldStatusInfo] = []
    for inc_resp, shield_obj, name in rows:
        s_lat, s_lng = await _resolve_shield_position(
            redis,
            incident_id=str(incident_id),
            shield_id=str(shield_obj.id),
            fallback_lat=shield_obj.current_lat,
            fallback_lng=shield_obj.current_lng,
            check_incident_key=(inc_resp.status == ResponseStatus.responding),
        )

        eta_seconds: int | None = None
        if (
            inc_resp.status == ResponseStatus.responding
            and s_lat is not None
            and s_lng is not None
            and convergence_point is not None
        ):
            eta_seconds = await navigation_service.get_eta_seconds(
                s_lat, s_lng, conv_lat, conv_lng
            )

        shields_info.append(
            ShieldStatusInfo(
                shield_id=inc_resp.shield_id,
                name=name,
                status=inc_resp.status.value,
                lat=s_lat,
                lng=s_lng,
                eta_seconds=eta_seconds,
            )
        )

    return IncidentDetailResponse(
        incident_id=incident.id,
        status=incident.status.value,
        trigger_lat=incident.trigger_lat,
        trigger_lng=incident.trigger_lng,
        convergence_point=convergence_point,
        triggered_at=incident.triggered_at,
        resolved_at=incident.resolved_at,
        shields_notified=len(rows),
        shields=shields_info,
        person_polyline=person_polyline,
    )


async def get_incident_context(
    incident_id: UUID,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    skip_gemini: bool = False,
) -> IncidentContextResponse:
    """Build the flat string-valued context dict ElevenLabs dynamicVariables expects.

    Every value is a human-readable string — no ints, no nulls, no nested objects.
    """
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident: Incident | None = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    conv_lat = incident.convergence_lat or incident.trigger_lat
    conv_lng = incident.convergence_lng or incident.trigger_lng

    rows = (
        await db.execute(
            select(IncidentResponse, Shield)
            .join(Shield, IncidentResponse.shield_id == Shield.id)
            .where(
                IncidentResponse.incident_id == incident_id,
                IncidentResponse.status == ResponseStatus.responding,
            )
        )
    ).all()

    responding_count = len(rows)
    nearest_distance_m: float | None = None
    nearest_eta_seconds: int | None = None

    for inc_resp, shield_obj in rows:
        s_lat, s_lng = await _resolve_shield_position(
            redis,
            incident_id=str(incident_id),
            shield_id=str(shield_obj.id),
            fallback_lat=shield_obj.current_lat,
            fallback_lng=shield_obj.current_lng,
        )
        if s_lat is None or s_lng is None:
            continue

        dist_m = haversine_distance(s_lat, s_lng, conv_lat, conv_lng) * 1000.0
        if nearest_distance_m is None or dist_m < nearest_distance_m:
            nearest_distance_m = dist_m
            try:
                nearest_eta_seconds = await navigation_service.get_eta_seconds(
                    s_lat, s_lng, conv_lat, conv_lng
                )
            except Exception:
                logger.exception("ETA computation failed for context")
                nearest_eta_seconds = None

    area_safety_note = ""
    if not skip_gemini:
        try:
            from app.services import hotspot_service

            area_safety_note = await hotspot_service.get_gemini_safety_context(
                incident.trigger_lat, incident.trigger_lng, db=db
            )
        except Exception:
            logger.exception("Gemini safety context failed for incident %s", incident_id)

    convergence_address = "your convergence point"
    if incident.convergence_lat is not None:
        convergence_address = f"{incident.convergence_lat:.4f}, {incident.convergence_lng:.4f}"

    return IncidentContextResponse(
        shield_count=str(responding_count),
        nearest_distance=(
            f"{round(nearest_distance_m)} metres"
            if nearest_distance_m is not None
            else "unknown distance"
        ),
        nearest_eta=(
            f"{round(nearest_eta_seconds / 60)} minutes"
            if nearest_eta_seconds is not None
            else "a few minutes"
        ),
        convergence_address=convergence_address,
        incident_status=incident.status.value,
        area_safety_note=area_safety_note,
    )


_CONTEXT_UPDATE_THRESHOLD_M = 50.0


def _nearest_distance_key(incident_id: str) -> str:
    return f"shieldher:incident:{incident_id}:last_nearest_m"


async def compute_context_update_if_needed(
    incident_id: str,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> dict[str, str] | None:
    """Recompute nearest-shield distance and return a context dict if it changed > 50 m.

    Returns ``None`` when the change is below threshold (no broadcast needed).
    Stores the new nearest distance in Redis for subsequent comparisons.
    """
    result = await db.execute(
        select(Incident).where(Incident.id == UUID(incident_id))
    )
    incident: Incident | None = result.scalar_one_or_none()
    if incident is None or incident.status != IncidentStatus.active:
        return None

    conv_lat = incident.convergence_lat or incident.trigger_lat
    conv_lng = incident.convergence_lng or incident.trigger_lng

    responding = (
        await db.execute(
            select(IncidentResponse, Shield)
            .join(Shield, IncidentResponse.shield_id == Shield.id)
            .where(
                IncidentResponse.incident_id == UUID(incident_id),
                IncidentResponse.status == ResponseStatus.responding,
            )
        )
    ).all()

    nearest_m: float | None = None
    nearest_eta_s: int | None = None
    for inc_resp, shield_obj in responding:
        s_lat, s_lng = await _resolve_shield_position(
            redis,
            incident_id=incident_id,
            shield_id=str(shield_obj.id),
            fallback_lat=shield_obj.current_lat,
            fallback_lng=shield_obj.current_lng,
        )
        if s_lat is None or s_lng is None:
            continue
        dist_m = haversine_distance(s_lat, s_lng, conv_lat, conv_lng) * 1000.0
        if nearest_m is None or dist_m < nearest_m:
            nearest_m = dist_m

    if nearest_m is None:
        return None

    prev_raw: bytes | str | None = await redis.get(_nearest_distance_key(incident_id))
    prev_nearest: float | None = float(prev_raw) if prev_raw else None

    await redis.set(
        _nearest_distance_key(incident_id),
        str(nearest_m),
        ex=_INCIDENT_STATE_TTL,
    )

    if prev_nearest is not None and abs(prev_nearest - nearest_m) <= _CONTEXT_UPDATE_THRESHOLD_M:
        return None

    # Threshold exceeded — compute lightweight context (skip Gemini for speed)
    if nearest_m is not None:
        nearest_eta_s = max(1, int(nearest_m / 1.4))  # Haversine-based, no API

    convergence_address = "your convergence point"
    if incident.convergence_lat is not None:
        convergence_address = f"{incident.convergence_lat:.4f}, {incident.convergence_lng:.4f}"

    return {
        "shield_count": str(len(responding)),
        "nearest_distance": f"{round(nearest_m)} metres",
        "nearest_eta": (
            f"{round(nearest_eta_s / 60)} minutes"
            if nearest_eta_s is not None
            else "a few minutes"
        ),
        "convergence_address": convergence_address,
        "incident_status": incident.status.value,
        "area_safety_note": "",
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

async def require_incident_owner(
    incident_id: UUID,
    user: User,
    *,
    db: AsyncSession,
) -> Incident:
    """Load an incident and verify the requesting user owns it.  Raises 404/403."""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident: Incident | None = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.triggered_by != user.id:
        raise HTTPException(status_code=403, detail="Not the incident owner")
    return incident


async def _require_active_incident(db: AsyncSession, incident_id: UUID) -> Incident:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident: Incident | None = result.scalar_one_or_none()
    if incident is None or incident.status != IncidentStatus.active:
        raise HTTPException(status_code=404, detail="Active incident not found")
    return incident


async def _require_notified_response(
    db: AsyncSession, incident_id: UUID, shield_id: UUID
) -> IncidentResponse:
    result = await db.execute(
        select(IncidentResponse).where(
            IncidentResponse.incident_id == incident_id,
            IncidentResponse.shield_id == shield_id,
        )
    )
    response: IncidentResponse | None = result.scalar_one_or_none()
    if response is None:
        raise HTTPException(
            status_code=403, detail="You were not notified for this incident"
        )
    return response


async def _resolve_shield_position(
    redis: aioredis.Redis,
    *,
    incident_id: str,
    shield_id: str,
    fallback_lat: float | None,
    fallback_lng: float | None,
    check_incident_key: bool = True,
) -> tuple[float | None, float | None]:
    """Return the best-known (lat, lng) for a shield.

    Priority:
      1. Per-incident location hash (most current while responding)
      2. General shield location hash
      3. Postgres fallback values
    """
    if check_incident_key:
        data: dict[str, str] = await redis.hgetall(
            _incident_shield_loc_key(incident_id, shield_id)
        )
        if data:
            return float(data["lat"]), float(data["lng"])

    data = await redis.hgetall(_shield_loc_key(shield_id))
    if data:
        return float(data["lat"]), float(data["lng"])

    return fallback_lat, fallback_lng


async def _patch_incident_state(
    redis: aioredis.Redis,
    *,
    incident_id: UUID,
    patch: dict[str, Any],
) -> None:
    """Merge ``patch`` into the cached incident state blob."""
    raw: bytes | None = await redis.get(_state_key(incident_id))
    if not raw:
        return
    state: dict[str, Any] = json.loads(raw)
    state.update(patch)
    await redis.set(_state_key(incident_id), json.dumps(state), ex=_INCIDENT_STATE_TTL)


async def _send_covered_notifications(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    incident_id: UUID,
) -> None:
    """Push a 'covered' notification to all still-notified (not-yet-responded) shields."""
    notified = (
        await db.execute(
            select(IncidentResponse).where(
                IncidentResponse.incident_id == incident_id,
                IncidentResponse.status == ResponseStatus.notified,
            )
        )
    ).scalars().all()

    await asyncio.gather(
        *[
            send_to_shield(
                resp.shield_id,
                title="Covered",
                body="Enough Shields are responding — you're off the hook. Thank you!",
                data={"type": "covered", "incident_id": str(incident_id)},
                db=db,
            )
            for resp in notified
        ],
        return_exceptions=True,
    )


async def _increment_hotspot(
    db: AsyncSession,
    *,
    lat: float,
    lng: float,
    now: datetime,
) -> None:
    """Delegate hotspot upsert to hotspot_service (precision-6 cells, ~1.2 km)."""
    await hotspot_service.log_incident_to_hotspot(lat, lng, now, db=db)
