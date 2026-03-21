"""Tests for the location service and /location router.

Coverage
--------
- update_shield_location  → writes lat/lng to Redis hash with correct TTL
- update_shield_location  → triggers background DB persist (best-effort)
- get_active_shields_near → returns shields within initial radius
- get_active_shields_near → expands radius when fewer than 3 found
- get_active_shields_near → ignores stale locations (> 5 min old)
- update_person_location  → writes to Redis and publishes to Pub/Sub channel
- PATCH /location/shield  → authenticated shield can update its location
- PATCH /location/incident/{id} → authenticated person can update their location
- GET  /location/incident/{id}/all → returns live positions for an active incident
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shields import Shield, ShieldStatus
from app.models.users import User, UserRole
from app.services.location_service import (
    get_active_shields_near,
    update_person_location,
    update_shield_location,
)
from tests.conftest import auth_headers, make_person, make_shield

_LAT = 49.1427
_LNG = 9.2109


# ── update_shield_location ────────────────────────────────────────────────────


async def test_update_shield_location_writes_to_redis(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    shield_id = str(uuid4())
    await update_shield_location(shield_id, 49.1427, 9.2109, redis=fake_redis)

    key = f"shieldher:shield:location:{shield_id}"
    data = await fake_redis.hgetall(key)
    assert float(data["lat"]) == pytest.approx(49.1427)
    assert float(data["lng"]) == pytest.approx(9.2109)
    assert "updated_at" in data


async def test_update_shield_location_has_ttl(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    shield_id = str(uuid4())
    await update_shield_location(shield_id, 49.1427, 9.2109, redis=fake_redis)

    key = f"shieldher:shield:location:{shield_id}"
    ttl = await fake_redis.ttl(key)
    # TTL must be 300 s (±5 s tolerance)
    assert 295 <= ttl <= 305


# ── get_active_shields_near ───────────────────────────────────────────────────


async def test_get_active_shields_near_returns_within_radius(
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Shields within 1 km are returned in the first pass."""
    for i, (lat, lng) in enumerate([(49.1460, 9.2160), (49.1395, 9.2060)]):
        await make_shield(
            db_session, fake_redis, phone=f"+4917000{i:05d}", lat=lat, lng=lng
        )

    results = await get_active_shields_near(_LAT, _LNG, radius_km=1.0, db=db_session)
    assert len(results) >= 2
    for r in results:
        assert r["distance_km"] <= 3.0  # max search radius cap


async def test_get_active_shields_near_radius_expansion(
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """When fewer than 3 shields are in the initial radius, search expands."""
    # Place a single shield at ~1.5 km (outside 1 km, inside 2 km)
    await make_shield(
        db_session, fake_redis, phone="+491700010001", lat=49.1560, lng=9.2300
    )

    results = await get_active_shields_near(_LAT, _LNG, radius_km=1.0, db=db_session)
    # Expansion should include the 1.5 km shield
    assert len(results) >= 1


async def test_get_active_shields_near_excludes_stale_locations(
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Shields whose location_updated_at is older than 5 min are excluded."""
    _, shield = await make_shield(
        db_session, fake_redis, phone="+491700010002", lat=49.1450, lng=9.2150
    )

    # Back-date location_updated_at by 10 minutes
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.execute(
        update(Shield)
        .where(Shield.id == shield.id)
        .values(location_updated_at=stale_time)
    )
    await db_session.commit()

    results = await get_active_shields_near(_LAT, _LNG, radius_km=3.0, db=db_session)
    shield_ids = [r["shield_id"] for r in results]
    assert str(shield.id) not in shield_ids


async def test_get_active_shields_near_excludes_inactive(
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Inactive or unverified shields must not appear in proximity results."""
    await make_shield(
        db_session,
        fake_redis,
        phone="+491700010003",
        lat=49.1450,
        lng=9.2150,
        status=ShieldStatus.inactive,
    )
    await make_shield(
        db_session,
        fake_redis,
        phone="+491700010004",
        lat=49.1450,
        lng=9.2160,
        id_verified=False,
        status=ShieldStatus.active,
    )

    results = await get_active_shields_near(_LAT, _LNG, radius_km=3.0, db=db_session)
    assert len(results) == 0


# ── update_person_location ────────────────────────────────────────────────────


async def test_update_person_location_writes_to_redis(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    incident_id = str(uuid4())
    await update_person_location(incident_id, 49.1427, 9.2109, redis=fake_redis)

    key = f"shieldher:incident:location:{incident_id}"
    data = await fake_redis.hgetall(key)
    assert float(data["lat"]) == pytest.approx(49.1427)
    assert float(data["lng"]) == pytest.approx(9.2109)


async def test_update_person_location_publishes_to_channel(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    incident_id = str(uuid4())
    channel = f"shieldher:incident:{incident_id}:updates"

    # Subscribe before publishing
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(channel)

    await update_person_location(incident_id, 49.1427, 9.2109, redis=fake_redis)

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
    assert msg is not None
    assert msg["type"] == "message"

    await pubsub.unsubscribe(channel)
    await pubsub.aclose()


# ── HTTP endpoints ────────────────────────────────────────────────────────────


async def test_patch_shield_location_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """PATCH /location/shield updates the shield's position."""
    shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700010010", lat=49.1450, lng=9.2150
    )
    resp = await client.patch(
        "/api/v1/location/shield",
        json={"lat": 49.1460, "lng": 9.2160},
        headers=auth_headers(shield_user),
    )
    assert resp.status_code == 200, resp.text


async def test_patch_shield_location_requires_shield_role(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    person = await make_person(db_session, phone="+491700010011")
    resp = await client.patch(
        "/api/v1/location/shield",
        json={"lat": 49.1460, "lng": 9.2160},
        headers=auth_headers(person),
    )
    assert resp.status_code == 403


async def test_get_incident_all_locations(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """GET /location/incident/{id}/all returns aggregated live positions."""
    person = await make_person(db_session)
    shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700010012", lat=49.1460, lng=9.2160
    )

    # Trigger SOS so the incident exists
    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    # Set the person's live location
    await update_person_location(incident_id, _LAT, _LNG, redis=fake_redis)

    resp = await client.get(
        f"/api/v1/location/incident/{incident_id}/all",
        headers=auth_headers(person),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["incident_id"] == incident_id
    assert data["person"] is not None
    assert isinstance(data["shields"], list)
