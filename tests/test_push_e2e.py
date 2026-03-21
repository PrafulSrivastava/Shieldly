"""End-to-end tests for the push notification flow.

What "E2E" means here
---------------------
Every test drives the system exclusively through HTTP endpoints (the `client`
fixture), identical to what a real mobile app would do.  The only mock is at
the Expo API network boundary — we intercept the outbound httpx call and
record every payload that would have been sent to exp.host, then assert on
those captured payloads.  Everything else (DB writes, Redis, auth, the full
SOS pipeline) runs for real.

Flow exercised
--------------
1.  PATCH /shields/me/device      — shield registers its Expo token
2.  POST  /incidents/trigger      — person triggers SOS
    → Expo API called once per notified shield; payload asserted
3.  POST  /incidents/{id}/respond — shield responds
4.  POST  /incidents/{id}/all-clear — person signals safety
    → Expo API called with "she is safe" notification; payload asserted

Edge cases
----------
- Shield without a token is skipped (no Expo call)
- DeviceNotRegistered response clears token in DB
- Expo HTTP error is absorbed; SOS flow still completes successfully
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import push_service
from tests.conftest import auth_headers, make_person, make_shield

# ── Constants ─────────────────────────────────────────────────────────────────

_LAT = 49.1427
_LNG = 9.2109

_TOKEN_A = "ExponentPushToken[ShieldAlpha_FakeToken_abc]"
_TOKEN_B = "ExponentPushToken[ShieldBeta__FakeToken_xyz]"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _expo_ok() -> MagicMock:
    """Build a fake successful Expo response."""
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = {"data": {"status": "ok"}}
    return r


def _expo_device_not_registered() -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = {
        "data": {
            "status": "error",
            "details": {"error": "DeviceNotRegistered"},
        }
    }
    return r


def _make_mock_http_client(responses: list[MagicMock]) -> MagicMock:
    """Return a context-manager-compatible mock httpx.AsyncClient.

    ``responses`` is consumed in order for each successive POST call.
    """
    responses_iter = iter(responses)

    async def _post(*args: Any, **kwargs: Any) -> MagicMock:
        return next(responses_iter)

    mock_client = AsyncMock()
    mock_client.post = _post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ── Full SOS lifecycle ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_sos_push_lifecycle(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    Complete happy-path:
      register token → trigger SOS → assert push payload → respond → all-clear →
      assert 'she is safe' push payload.
    """
    # ── 1. Create person + shield ──────────────────────────────────────────────
    person = await make_person(db_session)
    shield_user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000020", lat=49.1460, lng=9.2160
    )

    # ── 2. Shield registers its Expo token via the API ─────────────────────────
    reg_resp = await client.patch(
        "/api/v1/shields/me/device",
        json={"expo_push_token": _TOKEN_A},
        headers=auth_headers(shield_user),
    )
    assert reg_resp.status_code == 200, reg_resp.text
    assert reg_resp.json()["registered"] is True
    assert reg_resp.json()["token_preview"] == _TOKEN_A[-8:]

    # ── 3. Trigger SOS — intercept Expo API calls ──────────────────────────────
    # One shield → expect exactly one POST to Expo
    captured_sos_calls: list[dict[str, Any]] = []

    async def _capture_post(url: str, **kwargs: Any) -> MagicMock:
        captured_sos_calls.append({"url": url, "payload": kwargs.get("json", {})})
        return _expo_ok()

    mock_client = AsyncMock()
    mock_client.post = _capture_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client),
    ):
        sos_resp = await client.post(
            "/api/v1/incidents/trigger",
            json={"lat": _LAT, "lng": _LNG},
            headers=auth_headers(person),
        )

    assert sos_resp.status_code == 201, sos_resp.text
    sos_data = sos_resp.json()
    assert sos_data["shields_notified"] == 1
    incident_id: str = sos_data["incident_id"]

    # Assert Expo was called with the right SOS payload
    assert len(captured_sos_calls) == 1, "Expected exactly one Expo push call"
    sos_payload = captured_sos_calls[0]["payload"]
    assert sos_payload["to"] == _TOKEN_A
    assert sos_payload["priority"] == "high"
    assert sos_payload["channelId"] == "sos-alerts"
    assert sos_payload["data"]["type"] == "sos_alert"
    assert sos_payload["data"]["incident_id"] == incident_id
    assert "lat" in sos_payload["data"]
    assert "lng" in sos_payload["data"]
    assert "distance_km" in sos_payload["data"]

    # ── 4. Shield responds ─────────────────────────────────────────────────────
    respond_resp = await client.post(
        f"/api/v1/incidents/{incident_id}/respond",
        json={"action": "responding"},
        headers=auth_headers(shield_user),
    )
    assert respond_resp.status_code == 200, respond_resp.text

    # ── 5. Person signals all-clear — shield should receive "she is safe" push ─
    captured_clear_calls: list[dict[str, Any]] = []

    async def _capture_clear_post(url: str, **kwargs: Any) -> MagicMock:
        captured_clear_calls.append({"url": url, "payload": kwargs.get("json", {})})
        return _expo_ok()

    mock_client2 = AsyncMock()
    mock_client2.post = _capture_clear_post
    mock_client2.__aenter__ = AsyncMock(return_value=mock_client2)
    mock_client2.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client2),
    ):
        clear_resp = await client.post(
            f"/api/v1/incidents/{incident_id}/all-clear",
            headers=auth_headers(person),
        )

    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["status"] == "resolved"

    assert len(captured_clear_calls) == 1, "Expected 'she is safe' push to the responding shield"
    clear_payload = captured_clear_calls[0]["payload"]
    assert clear_payload["to"] == _TOKEN_A
    assert clear_payload["data"]["type"] == "resolved"
    assert clear_payload["data"]["incident_id"] == incident_id


# ── Shield without token is skipped ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_sos_skips_shields_without_token(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Shields that never registered a token produce zero Expo API calls."""
    person = await make_person(db_session)
    # make_shield does NOT assign a token — expo_push_token stays NULL
    await make_shield(
        db_session, fake_redis, phone="+491700000021", lat=49.1460, lng=9.2160
    )

    expo_call_count = 0

    async def _count_post(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal expo_call_count
        expo_call_count += 1
        return _expo_ok()

    mock_client = AsyncMock()
    mock_client.post = _count_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client),
    ):
        sos_resp = await client.post(
            "/api/v1/incidents/trigger",
            json={"lat": _LAT, "lng": _LNG},
            headers=auth_headers(person),
        )

    assert sos_resp.status_code == 201
    assert sos_resp.json()["shields_notified"] == 1   # shield was notified in DB
    assert expo_call_count == 0                        # but no Expo call was made


# ── Multiple shields receive independent payloads ─────────────────────────────


@pytest.mark.asyncio
async def test_sos_sends_push_to_all_nearby_shields(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Two shields with tokens both receive pushes with their own distance_km."""
    person = await make_person(db_session)

    shield_user_a, shield_a = await make_shield(
        db_session, fake_redis, phone="+491700000022", lat=49.1460, lng=9.2160
    )
    shield_user_b, shield_b = await make_shield(
        db_session, fake_redis, phone="+491700000023", lat=49.1395, lng=9.2060
    )

    # Register tokens for both shields
    for user, token in [(shield_user_a, _TOKEN_A), (shield_user_b, _TOKEN_B)]:
        r = await client.patch(
            "/api/v1/shields/me/device",
            json={"expo_push_token": token},
            headers=auth_headers(user),
        )
        assert r.status_code == 200

    captured: list[dict[str, Any]] = []

    async def _capture(url: str, **kwargs: Any) -> MagicMock:
        captured.append(kwargs.get("json", {}))
        return _expo_ok()

    mock_client = AsyncMock()
    mock_client.post = _capture
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client),
    ):
        sos_resp = await client.post(
            "/api/v1/incidents/trigger",
            json={"lat": _LAT, "lng": _LNG},
            headers=auth_headers(person),
        )

    assert sos_resp.status_code == 201
    assert sos_resp.json()["shields_notified"] == 2
    assert len(captured) == 2, "Expected one Expo call per shield"

    # Both payloads hit Expo Push URL
    for payload in captured:
        assert payload["to"] in (_TOKEN_A, _TOKEN_B)
        assert payload["data"]["type"] == "sos_alert"
        assert payload["priority"] == "high"

    # Each shield gets its own distance_km
    distances = {p["to"]: p["data"]["distance_km"] for p in captured}
    assert distances[_TOKEN_A] != distances[_TOKEN_B]


# ── Expo error is absorbed — SOS never fails ──────────────────────────────────


@pytest.mark.asyncio
async def test_sos_completes_even_if_expo_returns_error(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """A network error from the Expo API must not break the SOS trigger."""
    person = await make_person(db_session)
    shield_user, _ = await make_shield(
        db_session, fake_redis, phone="+491700000024", lat=49.1460, lng=9.2160
    )
    await client.patch(
        "/api/v1/shields/me/device",
        json={"expo_push_token": _TOKEN_A},
        headers=auth_headers(shield_user),
    )

    async def _raise(*args: Any, **kwargs: Any) -> None:
        raise Exception("Expo is down")

    mock_client = AsyncMock()
    mock_client.post = _raise
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client),
    ):
        sos_resp = await client.post(
            "/api/v1/incidents/trigger",
            json={"lat": _LAT, "lng": _LNG},
            headers=auth_headers(person),
        )

    # SOS endpoint must still return 201 — push failure is non-fatal
    assert sos_resp.status_code == 201, sos_resp.text
    assert sos_resp.json()["shields_notified"] == 1


# ── DeviceNotRegistered clears token in DB ────────────────────────────────────


@pytest.mark.asyncio
async def test_device_not_registered_clears_token_during_sos(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    When Expo returns DeviceNotRegistered during an SOS push the shield's token
    is wiped from the DB and the SOS still completes successfully.
    """
    person = await make_person(db_session)
    shield_user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000025", lat=49.1460, lng=9.2160
    )
    await client.patch(
        "/api/v1/shields/me/device",
        json={"expo_push_token": _TOKEN_A},
        headers=auth_headers(shield_user),
    )

    mock_client = _make_mock_http_client([_expo_device_not_registered()])

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client),
    ):
        sos_resp = await client.post(
            "/api/v1/incidents/trigger",
            json={"lat": _LAT, "lng": _LNG},
            headers=auth_headers(person),
        )

    assert sos_resp.status_code == 201

    # Token must be cleared in DB after DeviceNotRegistered
    await db_session.refresh(shield)
    assert shield.expo_push_token is None, (
        "expo_push_token should be cleared after DeviceNotRegistered response"
    )


# ── Token update replaces old token ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_device_registration_replaces_old_token(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Calling PATCH /device twice stores the most recent token."""
    shield_user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000026", lat=49.1460, lng=9.2160
    )

    # First registration
    r1 = await client.patch(
        "/api/v1/shields/me/device",
        json={"expo_push_token": _TOKEN_A},
        headers=auth_headers(shield_user),
    )
    assert r1.status_code == 200

    # Second registration (e.g. after app reinstall)
    r2 = await client.patch(
        "/api/v1/shields/me/device",
        json={"expo_push_token": _TOKEN_B},
        headers=auth_headers(shield_user),
    )
    assert r2.status_code == 200
    assert r2.json()["token_preview"] == _TOKEN_B[-8:]

    await db_session.refresh(shield)
    assert shield.expo_push_token == _TOKEN_B
