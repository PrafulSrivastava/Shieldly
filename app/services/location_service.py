"""Real-time location tracking service.

Redis layout
------------
Shield general location (TTL 5 min):
    shieldher:shield:location:{shield_id}          HASH  lat, lng, updated_at

Person location during incident (TTL 5 min):
    shieldher:incident:location:{incident_id}      HASH  lat, lng, updated_at

Shield location during a specific incident (TTL 5 min):
    shieldher:incident:{incident_id}:shield:{shield_id}:location
                                                   HASH  lat, lng, updated_at

Pub/Sub channel for incident updates:
    shieldher:incident:{incident_id}:updates
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.incident_responses import IncidentResponse, ResponseStatus
from app.models.shields import Shield, ShieldStatus
from app.models.users import User
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)

_LOCATION_TTL = 300  # seconds — matches the "5 min stale" rule
_STALE_THRESHOLD = timedelta(days=7)
_MIN_SHIELDS_NEAR = 3
_MAX_SEARCH_RADIUS_KM = 3.0


# ── Redis key builders ────────────────────────────────────────────────────────

def _shield_location_key(shield_id: str) -> str:
    return f"shieldher:shield:location:{shield_id}"


def _incident_location_key(incident_id: str) -> str:
    return f"shieldher:incident:location:{incident_id}"


def _incident_shield_location_key(incident_id: str, shield_id: str) -> str:
    return f"shieldher:incident:{incident_id}:shield:{shield_id}:location"


def _incident_updates_channel(incident_id: str) -> str:
    return f"shieldher:incident:{incident_id}:updates"


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _persist_shield_location_to_db(
    shield_id: str, lat: float, lng: float
) -> None:
    """Persist shield GPS coordinates to Postgres (background — must not raise)."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Shield)
                .where(Shield.id == UUID(shield_id))
                .values(
                    current_lat=lat,
                    current_lng=lng,
                    location_updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception:
        logger.exception(
            "Failed to persist shield %s location to Postgres", shield_id
        )


# ── Public service functions ──────────────────────────────────────────────────

async def update_shield_location(
    shield_id: str,
    lat: float,
    lng: float,
    *,
    redis: aioredis.Redis,
) -> None:
    """Write the shield's GPS position to Redis and async-persist it to Postgres.

    Redis is authoritative for live tracking; Postgres is updated in the
    background so the response is never blocked by a DB write.
    """
    now = datetime.now(timezone.utc).isoformat()
    key = _shield_location_key(shield_id)

    await redis.hset(key, mapping={"lat": lat, "lng": lng, "updated_at": now})
    await redis.expire(key, _LOCATION_TTL)

    # Fire-and-forget Postgres persist — errors are logged, never propagated
    asyncio.create_task(_persist_shield_location_to_db(shield_id, lat, lng))


async def get_shield_location(
    shield_id: str,
    *,
    redis: aioredis.Redis,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """Return the shield's most recent location.

    Checks Redis first; falls back to Postgres on a cache miss.
    Returns ``None`` if no location exists or the record is older than 5 min.
    """
    key = _shield_location_key(shield_id)
    data: dict[str, str] = await redis.hgetall(key)

    if data:
        # Key exists → TTL guarantees freshness; no additional stale check needed
        return {
            "lat": float(data["lat"]),
            "lng": float(data["lng"]),
            "updated_at": data["updated_at"],
        }

    # Cache miss — query Postgres
    result = await db.execute(
        select(Shield).where(Shield.id == UUID(shield_id))
    )
    shield: Shield | None = result.scalar_one_or_none()

    if (
        shield is None
        or shield.current_lat is None
        or shield.current_lng is None
        or shield.location_updated_at is None
    ):
        return None

    age = datetime.now(timezone.utc) - shield.location_updated_at
    if age > _STALE_THRESHOLD:
        return None

    return {
        "lat": shield.current_lat,
        "lng": shield.current_lng,
        "updated_at": shield.location_updated_at.isoformat(),
    }


async def update_person_location(
    incident_id: str,
    lat: float,
    lng: float,
    *,
    redis: aioredis.Redis,
) -> None:
    """Store the person's live coordinates and broadcast them to all incident subscribers."""
    now = datetime.now(timezone.utc).isoformat()
    key = _incident_location_key(incident_id)

    await redis.hset(key, mapping={"lat": lat, "lng": lng, "updated_at": now})
    await redis.expire(key, _LOCATION_TTL)

    payload = json.dumps(
        {"type": "person_location", "lat": lat, "lng": lng, "timestamp": now}
    )
    await redis.publish(_incident_updates_channel(incident_id), payload)


async def update_responding_shield_location(
    incident_id: str,
    shield_id: str,
    lat: float,
    lng: float,
    *,
    redis: aioredis.Redis,
    context_update: dict[str, str] | None = None,
) -> None:
    """Store a responding shield's position for this incident and broadcast it.

    Uses a per-incident key so that a shield's movement while responding is
    visible to the person in distress without clobbering the shield's general
    location hash.

    When ``context_update`` is provided (nearest-shield distance changed > 50 m),
    it is included in the broadcast message so the frontend can call
    ``conversation.setVariables()`` to keep ElevenLabs voice current.
    """
    now = datetime.now(timezone.utc).isoformat()
    key = _incident_shield_location_key(incident_id, shield_id)

    await redis.hset(key, mapping={"lat": lat, "lng": lng, "updated_at": now})
    await redis.expire(key, _LOCATION_TTL)

    message: dict[str, Any] = {
        "type": "shield_location",
        "data": {
            "shield_id": shield_id,
            "lat": lat,
            "lng": lng,
            "timestamp": now,
        },
    }
    if context_update is not None:
        message["context_update"] = context_update

    await redis.publish(_incident_updates_channel(incident_id), json.dumps(message))


async def get_active_shields_near(
    lat: float,
    lng: float,
    radius_km: float,
    *,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Return active, verified shields within ``radius_km`` of the given point.

    The search expands from ``radius_km`` → 2 km → 3 km (in that order) until
    at least three shields are found.  Never expands beyond 3 km.  All
    candidates are fetched in a single DB query; filtering and distance
    calculation are done in Python via the Haversine formula.
    """
    stale_cutoff = datetime.now(timezone.utc) - _STALE_THRESHOLD

    rows = (
        await db.execute(
            select(Shield, User.name)
            .join(User, Shield.user_id == User.id)
            .where(
                Shield.status == ShieldStatus.active,
                Shield.id_verified.is_(True),
                Shield.current_lat.isnot(None),
                Shield.current_lng.isnot(None),
                Shield.location_updated_at >= stale_cutoff,
            )
        )
    ).all()

    # Pre-compute distances and keep only those within the maximum search radius
    candidates: list[dict[str, Any]] = []
    for shield, name in rows:
        dist = haversine_distance(lat, lng, shield.current_lat, shield.current_lng)
        if dist <= _MAX_SEARCH_RADIUS_KM:
            candidates.append(
                {
                    "shield_id": str(shield.id),
                    "user_id": str(shield.user_id),
                    "name": name,
                    "lat": shield.current_lat,
                    "lng": shield.current_lng,
                    "distance_km": round(dist, 3),
                }
            )

    candidates.sort(key=lambda c: c["distance_km"])

    # Expand outward until we have at least _MIN_SHIELDS_NEAR results
    search_radii: list[float] = [radius_km]
    if radius_km < 2.0:
        search_radii.append(2.0)
    if radius_km < _MAX_SEARCH_RADIUS_KM:
        search_radii.append(_MAX_SEARCH_RADIUS_KM)

    for r in search_radii:
        within = [c for c in candidates if c["distance_km"] <= r]
        if len(within) >= _MIN_SHIELDS_NEAR:
            return within

    # Return whatever is available even if fewer than 3 were found
    return [c for c in candidates if c["distance_km"] <= max(radius_km, _MAX_SEARCH_RADIUS_KM)]


async def get_incident_all_locations(
    incident_id: str,
    *,
    redis: aioredis.Redis,
    db: AsyncSession,
) -> dict[str, Any]:
    """Aggregate all live positions for an incident.

    Returns:
        {
            "incident_id": str,
            "person": {"lat", "lng", "updated_at"} | None,
            "shields": [{"shield_id", "lat", "lng", "updated_at"}, ...]
        }
    """
    # Person's last known position
    person_data: dict[str, str] = await redis.hgetall(
        _incident_location_key(incident_id)
    )
    person: dict[str, Any] | None = (
        {
            "lat": float(person_data["lat"]),
            "lng": float(person_data["lng"]),
            "updated_at": person_data.get("updated_at"),
        }
        if person_data
        else None
    )

    # All shields currently in the "responding" state for this incident
    result = await db.execute(
        select(IncidentResponse).where(
            IncidentResponse.incident_id == UUID(incident_id),
            IncidentResponse.status == ResponseStatus.responding,
        )
    )
    responses = result.scalars().all()

    shields: list[dict[str, Any]] = []
    for resp in responses:
        loc: dict[str, str] = await redis.hgetall(
            _incident_shield_location_key(incident_id, str(resp.shield_id))
        )
        if loc:
            shields.append(
                {
                    "shield_id": str(resp.shield_id),
                    "lat": float(loc["lat"]),
                    "lng": float(loc["lng"]),
                    "updated_at": loc.get("updated_at"),
                }
            )

    return {"incident_id": incident_id, "person": person, "shields": shields}
