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
    assert resp.status_code == 200, resp.text
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
    assert resp.status_code == 200
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
    assert sos_resp.status_code == 200
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
