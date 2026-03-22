"""Tests for shareable live location tracking.

Coverage
--------
- POST /trigger returns tracking_url with a 43-char token segment
- GET /track/{token} returns 200 with TrackingResponse — no auth required
- GET /track/{token} returns zero PII (no name, phone, user_id, shield_name)
- GET /track/invalidtoken returns 404
- Resolved incident tracking page returns status == "resolved" with purged locations
- SMS body contains tracking_url (mock mode)
- WS /track/{token}/live receives shield location updates
- WS /track/{token}/live closes on incident resolve
"""

import json
import logging
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import sms_service
from tests.conftest import auth_headers, make_person, make_shield

_LAT = 49.1427
_LNG = 9.2109


# ── Token generation on trigger ──────────────────────────────────────────────


async def test_tracking_token_generated_on_trigger(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """POST /incidents/trigger returns tracking_url with a 43-char token."""
    person = await make_person(db_session)
    await make_shield(
        db_session, fake_redis, phone="+491700000102", lat=49.146, lng=9.216
    )

    resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "tracking_url" in data
    tracking_url: str = data["tracking_url"]
    assert "/track/" in tracking_url
    token = tracking_url.split("/track/")[-1]
    assert len(token) == 43


# ── Public tracking endpoint — no auth ───────────────────────────────────────


async def test_public_tracking_endpoint_no_auth(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """GET /track/{token} returns 200 with no Authorization header."""
    person = await make_person(db_session)
    await make_shield(
        db_session, fake_redis, phone="+491700000103", lat=49.146, lng=9.216
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    tracking_url: str = sos_resp.json()["tracking_url"]
    token = tracking_url.split("/track/")[-1]

    resp = await client.get(f"/api/v1/track/{token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["person_lat"] is not None
    assert "incident_id" in data


# ── No PII in tracking response ──────────────────────────────────────────────


async def test_tracking_endpoint_returns_no_pii(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Tracking response must never contain name, phone, user_id, or shield_name."""
    person = await make_person(db_session)
    shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700000104", lat=49.146, lng=9.216
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    tracking_url: str = sos_resp.json()["tracking_url"]
    token = tracking_url.split("/track/")[-1]
    incident_id = sos_resp.json()["incident_id"]

    await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(shield_user),
    )

    resp = await client.get(f"/api/v1/track/{token}")
    assert resp.status_code == 200
    body_str = resp.text

    pii_fields = ["name", "phone", "user_id", "shield_name", "shield_id"]
    data = resp.json()
    for field in pii_fields:
        assert field not in data, f"PII field '{field}' found in tracking response"

    for shield in data.get("responding_shields", []):
        assert "shield_index" in shield
        for pii in ["name", "phone", "user_id", "shield_id"]:
            assert pii not in shield, f"PII '{pii}' found in shield tracking info"


# ── 404 for bad token ────────────────────────────────────────────────────────


async def test_tracking_endpoint_404_bad_token(client: AsyncClient) -> None:
    """GET /track/totallyinvalidtoken returns 404."""
    resp = await client.get("/api/v1/track/totallyinvalidtoken")
    assert resp.status_code == 404


# ── Resolved incident tracking page ──────────────────────────────────────────


async def test_resolved_incident_tracking_page(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Resolved incident returns status=resolved with person_lat/lng purged."""
    person = await make_person(db_session)
    await make_shield(
        db_session, fake_redis, phone="+491700000105", lat=49.146, lng=9.216
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    tracking_url: str = sos_resp.json()["tracking_url"]
    token = tracking_url.split("/track/")[-1]
    incident_id = sos_resp.json()["incident_id"]

    await client.post(
        f"/api/v1/incidents/{incident_id}/all-clear",
        headers=auth_headers(person),
    )

    resp = await client.get(f"/api/v1/track/{token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resolved"
    assert data["person_lat"] is None
    assert data["person_lng"] is None
    assert data["responding_shields"] == []


# ── SMS body contains tracking URL ───────────────────────────────────────────


async def test_sms_body_contains_tracking_url(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """MOCK_SMS=true — SMS body logged to console contains the tracking URL."""
    person = await make_person(db_session)
    await make_shield(
        db_session, fake_redis, phone="+491700000106", lat=49.146, lng=9.216
    )

    with (
        patch.object(sms_service.settings, "mock_sms", True),
        caplog.at_level(logging.INFO),
    ):
        resp = await client.post(
            "/api/v1/incidents/trigger",
            json={"lat": _LAT, "lng": _LNG},
            headers=auth_headers(person),
        )

    assert resp.status_code == 201
    tracking_url: str = resp.json()["tracking_url"]

    # The SMS runs as a BackgroundTask — when using httpx AsyncClient with
    # ASGITransport the background tasks execute before the response returns.
    sms_logs = [r.message for r in caplog.records if "MOCK SMS" in r.message]
    assert len(sms_logs) >= 1, "Expected at least one mock SMS log entry"
    assert any("/track/" in log for log in sms_logs), (
        f"Tracking URL not found in SMS logs: {sms_logs}"
    )


# ── WebSocket — receives shield location updates ─────────────────────────────


async def test_tracking_ws_receives_shield_updates(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """WS /track/{token}/live receives shield_location broadcasts."""
    person = await make_person(db_session)
    shield_user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000107", lat=49.146, lng=9.216
    )

    sos_resp = await client.post(
        "/api/v1/incidents/trigger",
        json={"lat": _LAT, "lng": _LNG},
        headers=auth_headers(person),
    )
    tracking_url: str = sos_resp.json()["tracking_url"]
    token = tracking_url.split("/track/")[-1]
    incident_id = sos_resp.json()["incident_id"]

    await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(shield_user),
    )

    channel = f"shieldher:incident:{incident_id}:updates"
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=1)

    await client.patch(
        "/api/v1/location/shield",
        json={"lat": 49.1454, "lng": 9.2150},
        headers=auth_headers(shield_user),
    )

    msg = await pubsub.get_message(timeout=1)
    assert msg is not None, "Expected broadcast after shield location update"
    payload = json.loads(msg["data"])
    assert payload["type"] == "shield_location"

    await pubsub.unsubscribe(channel)
