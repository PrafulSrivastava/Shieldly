"""Tests for the incidents domain.

Coverage
--------
- POST /trigger → creates incident, notifies nearby shields
- POST /trigger with no nearby shields → incident created with 0 shields notified
- POST /{id}/respond (responding) → updates status, returns convergence point
- POST /{id}/respond (declined) → 204
- POST /{id}/respond by wrong shield → 403
- POST /{id}/all-clear → resolves incident
- POST /{id}/all-clear by non-owner → 403
- GET /{id} → returns full incident detail
"""

import json
from uuid import uuid4

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident_responses import IncidentResponse, ResponseStatus
from app.models.incidents import Incident, IncidentStatus
from app.models.shields import Shield, ShieldStatus
from tests.conftest import auth_headers, make_person, make_shield

# Heilbronn centre — same as seed data
_LAT = 49.1427
_LNG = 9.2109

# Shields within 1 km of centre
_SHIELD_POSITIONS = [
    ("+491700000002", 49.1460, 9.2160),  # ~400 m NE
    ("+491700000003", 49.1395, 9.2060),  # ~450 m SW
    ("+491700000004", 49.1470, 9.2050),  # ~430 m NW
]


# ── trigger SOS ───────────────────────────────────────────────────────────────


async def test_trigger_sos_creates_incident_and_notifies_shields(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    person = await make_person(db_session)
    for phone, lat, lng in _SHIELD_POSITIONS:
        await make_shield(db_session, fake_redis, phone=phone, lat=lat, lng=lng)

    resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "incident_id" in data
    assert data["shields_notified"] >= 1


async def test_trigger_sos_requires_person_role(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    _, shield = await make_shield(
        db_session, fake_redis, phone="+491700000005", lat=_LAT, lng=_LNG
    )
    # Load the shield's user
    result = await db_session.execute(
        select(Shield).where(Shield.id == shield.id)
    )
    s = result.scalar_one()
    from app.models.users import User

    u_result = await db_session.execute(
        select(User).where(User.id == s.user_id)
    )
    shield_user = u_result.scalar_one()

    resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(shield_user),
    )
    assert resp.status_code == 403


async def test_trigger_sos_with_no_nearby_shields(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """SOS must still create the incident even when no shields are nearby."""
    person = await make_person(db_session)
    resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["shields_notified"] == 0


# ── shield respond ────────────────────────────────────────────────────────────


async def test_shield_respond_accepting_returns_convergence_point(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    person = await make_person(db_session)
    shield_user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000006", lat=49.1460, lng=9.2160
    )

    # Trigger SOS
    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    assert sos_resp.status_code == 201
    incident_id = sos_resp.json()["incident_id"]

    # Shield responds
    resp = await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(shield_user),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["convergence_point"] is not None
    assert "lat" in data["convergence_point"]
    assert "lng" in data["convergence_point"]


async def test_shield_declining_returns_204(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    person = await make_person(db_session)
    shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700000007", lat=49.1460, lng=9.2160
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    resp = await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "declined"},
        headers=auth_headers(shield_user),
    )
    assert resp.status_code == 204


async def test_uninvited_shield_cannot_respond(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """A shield not notified for this incident must receive 403."""
    person = await make_person(db_session)
    # SOS — no shields nearby → notifies nobody
    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    # A different shield that was NOT notified tries to respond
    far_shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700000008", lat=49.2000, lng=9.3000
    )
    resp = await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(far_shield_user),
    )
    assert resp.status_code == 403


# ── all-clear ─────────────────────────────────────────────────────────────────


async def test_all_clear_resolves_incident(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    person = await make_person(db_session)
    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    resp = await client.post(
        f"/api/v1/incidents/{incident_id}/all-clear",
        headers=auth_headers(person),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


async def test_all_clear_by_non_owner_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    owner = await make_person(db_session, phone="+491700000011")
    other = await make_person(db_session, phone="+491700000012")

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(owner),
    )
    incident_id = sos_resp.json()["incident_id"]

    resp = await client.post(
        f"/api/v1/incidents/{incident_id}/all-clear",
        headers=auth_headers(other),
    )
    assert resp.status_code == 403


async def test_all_clear_already_resolved_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    person = await make_person(db_session)
    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    await client.post(
        f"/api/v1/incidents/{incident_id}/all-clear", headers=auth_headers(person)
    )
    resp = await client.post(
        f"/api/v1/incidents/{incident_id}/all-clear", headers=auth_headers(person)
    )
    assert resp.status_code == 409


# ── GET incident detail ───────────────────────────────────────────────────────


async def test_get_incident_detail(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    person = await make_person(db_session)
    shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700000013", lat=49.1460, lng=9.2160
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    detail_resp = await client.get(
        f"/api/v1/incidents/{incident_id}",
        headers=auth_headers(person),
    )
    assert detail_resp.status_code == 200, detail_resp.text
    data = detail_resp.json()
    assert data["incident_id"] == incident_id
    assert data["status"] == "active"
    assert data["trigger_lat"] == pytest.approx(_LAT, abs=0.001)
    assert data["trigger_lng"] == pytest.approx(_LNG, abs=0.001)
    assert "shields" in data


async def test_get_nonexistent_incident_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    person = await make_person(db_session)
    resp = await client.get(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(person),
    )
    assert resp.status_code == 404


# ── ElevenLabs token endpoint ────────────────────────────────────────────────


async def test_elevenlabs_token_endpoint_mock(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """MOCK_ELEVENLABS=true → returns 200 with a wss:// signed_url."""
    person = await make_person(db_session)
    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    resp = await client.get(
        f"/api/v1/incidents/{incident_id}/elevenlabs-token",
        headers=auth_headers(person),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["signed_url"].startswith("wss://")
    assert data["incident_id"] == incident_id


async def test_elevenlabs_token_forbidden_for_non_owner(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A user who did not trigger the incident must receive 403."""
    owner = await make_person(db_session, phone="+491700000020")
    other = await make_person(db_session, phone="+491700000021")

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(owner),
    )
    incident_id = sos_resp.json()["incident_id"]

    resp = await client.get(
        f"/api/v1/incidents/{incident_id}/elevenlabs-token",
        headers=auth_headers(other),
    )
    assert resp.status_code == 403


# ── Incident context endpoint ────────────────────────────────────────────────


async def test_context_returns_string_values_only(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Every value in the /context response must be a string — no ints, nulls, or dicts."""
    person = await make_person(db_session)
    shield_user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000030", lat=49.1460, lng=9.2160
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    # Shield responds so we get meaningful distances
    await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(shield_user),
    )

    resp = await client.get(
        f"/api/v1/incidents/{incident_id}/context",
        headers=auth_headers(person),
    )
    assert resp.status_code == 200
    data = resp.json()

    for key, value in data.items():
        assert isinstance(value, str), f"{key} should be str, got {type(value).__name__}"

    assert "metres" in data["nearest_distance"]
    assert "minutes" in data["nearest_eta"]


# ── WebSocket broadcast context_update ───────────────────────────────────────


async def test_ws_broadcast_includes_context_update_on_significant_move(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Shield moves 60 m closer → context_update present.
    Shield moves 20 m closer → context_update absent."""
    person = await make_person(db_session)
    shield_user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000040", lat=49.1460, lng=9.2160
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    incident_id = sos_resp.json()["incident_id"]

    await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(shield_user),
    )

    channel = f"shieldher:incident:{incident_id}:updates"
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(channel)
    # Drain the subscribe confirmation message
    await pubsub.get_message(timeout=1)

    # Move shield significantly closer (~60 m = 0.00054 degrees lat at this lat)
    await client.patch(
        "/api/v1/location/shield",
        json={"lat": 49.1454, "lng": 9.2150},
        headers=auth_headers(shield_user),
    )

    msg = await pubsub.get_message(timeout=1)
    assert msg is not None, "Expected broadcast after significant move"
    payload = json.loads(msg["data"])
    assert payload["type"] == "shield_location"
    assert "context_update" in payload, "context_update should be present after >50m move"
    ctx = payload["context_update"]
    assert isinstance(ctx["shield_count"], str)
    assert "metres" in ctx["nearest_distance"]

    # Move shield only slightly (~20 m = 0.00018 degrees lat)
    await client.patch(
        "/api/v1/location/shield",
        json={"lat": 49.14522, "lng": 9.2148},
        headers=auth_headers(shield_user),
    )

    msg2 = await pubsub.get_message(timeout=1)
    assert msg2 is not None, "Expected broadcast after small move"
    payload2 = json.loads(msg2["data"])
    assert "context_update" not in payload2, "context_update should NOT be present after <50m move"

    await pubsub.unsubscribe(channel)


# ── ElevenLabs E2E flow ───────────────────────────────────────────────────────


async def test_elevenlabs_e2e_full_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """End-to-end: person triggers SOS → shield responds → token → context → shield moves.

    Simulates the full backend flow an incident owner experiences when using
    ElevenLabs voice during an active SOS.
    """
    # 1. Set up person and nearby shield
    person = await make_person(db_session, phone="+491700000050")
    shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700000051", lat=49.1460, lng=9.2160
    )

    # 2. Person triggers SOS
    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    assert sos_resp.status_code == 201
    incident_id = sos_resp.json()["incident_id"]

    # 3. Shield responds → convergence point computed
    respond_resp = await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(shield_user),
    )
    assert respond_resp.status_code == 200

    # 4. Person requests ElevenLabs token (incident owner only)
    token_resp = await client.get(
        f"/api/v1/incidents/{incident_id}/elevenlabs-token",
        headers=auth_headers(person),
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert token_data["signed_url"].startswith("wss://")
    assert token_data["incident_id"] == incident_id

    # 5. Person fetches context for ElevenLabs dynamicVariables
    context_resp = await client.get(
        f"/api/v1/incidents/{incident_id}/context",
        headers=auth_headers(person),
    )
    assert context_resp.status_code == 200
    context = context_resp.json()
    assert all(isinstance(v, str) for v in context.values())
    assert context["incident_status"] == "active"
    assert context["shield_count"] == "1"

    # 6. Subscribe to incident updates before shield moves
    channel = f"shieldher:incident:{incident_id}:updates"
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=1)  # Drain subscribe confirmation

    # 7. Shield moves significantly closer (>50 m) → broadcast includes context_update
    await client.patch(
        "/api/v1/location/shield",
        json={"lat": 49.1454, "lng": 9.2150},
        headers=auth_headers(shield_user),
    )

    msg = await pubsub.get_message(timeout=1)
    assert msg is not None
    payload = json.loads(msg["data"])
    assert payload["type"] == "shield_location"
    assert "context_update" in payload
    ctx = payload["context_update"]
    assert ctx["incident_status"] == "active"
    assert "metres" in ctx["nearest_distance"]

    await pubsub.unsubscribe(channel)
