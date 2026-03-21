"""Tests for push notification service and device registration endpoint.

Coverage
--------
- send_to_shield: mock mode logs and returns True without HTTP call
- send_to_shield: no token → returns False, logs warning
- send_to_shield: Expo returns {"data": {"status": "ok"}} → returns True
- send_to_shield: Expo returns DeviceNotRegistered → returns False, clears token
- PATCH /api/v1/shields/me/device: valid token → 200, stored in DB
- PATCH /api/v1/shields/me/device: invalid format → 422
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shields import Shield, ShieldStatus
from app.models.users import User, UserRole
from app.services import push_service
from tests.conftest import auth_headers, make_shield

# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_TOKEN = "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"
_VALID_TOKEN_PREVIEW = _VALID_TOKEN[-8:]


async def _make_shield_with_token(
    db: AsyncSession,
    redis: object,
    *,
    token: str | None = _VALID_TOKEN,
) -> tuple[User, Shield]:
    user, shield = await make_shield(
        db, redis, phone="+491700000010", lat=49.1427, lng=9.2109
    )
    shield.expo_push_token = token
    await db.commit()
    await db.refresh(shield)
    return user, shield


# ── send_to_shield: mock mode ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_to_shield_mock_mode(
    db_session: AsyncSession,
    fake_redis: object,
) -> None:
    """MOCK_PUSH=true → logs, returns True, makes no HTTP call."""
    _, shield = await _make_shield_with_token(db_session, fake_redis)

    with (
        patch.object(push_service.settings, "mock_push", True),
        patch("app.services.push_service.httpx.AsyncClient") as mock_http,
    ):
        result = await push_service.send_to_shield(
            shield.id,
            title="SOS Alert",
            body="Help needed",
            data={"type": "sos_alert"},
            db=db_session,
        )

    assert result is True
    mock_http.assert_not_called()


# ── send_to_shield: no token ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_to_shield_no_token(
    db_session: AsyncSession,
    fake_redis: object,
) -> None:
    """Shield with no expo_push_token → returns False, logs warning."""
    _, shield = await _make_shield_with_token(db_session, fake_redis, token=None)

    with patch.object(push_service.settings, "mock_push", False):
        result = await push_service.send_to_shield(
            shield.id,
            title="SOS Alert",
            body="Help needed",
            data={"type": "sos_alert"},
            db=db_session,
        )

    assert result is False


# ── send_to_shield: successful delivery ───────────────────────────────────────


@pytest.mark.asyncio
async def test_send_to_shield_success(
    db_session: AsyncSession,
    fake_redis: object,
) -> None:
    """Expo responds {"data": {"status": "ok"}} → returns True."""
    _, shield = await _make_shield_with_token(db_session, fake_redis)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"data": {"status": "ok"}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await push_service.send_to_shield(
            shield.id,
            title="SOS Alert",
            body="Help needed",
            data={"type": "sos_alert"},
            db=db_session,
        )

    assert result is True
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[0][0] == push_service._EXPO_PUSH_URL
    sent_payload = call_kwargs[1]["json"]
    assert sent_payload["to"] == _VALID_TOKEN
    assert sent_payload["priority"] == "high"
    assert sent_payload["channelId"] == "sos-alerts"


# ── send_to_shield: DeviceNotRegistered ───────────────────────────────────────


@pytest.mark.asyncio
async def test_send_to_shield_device_not_registered(
    db_session: AsyncSession,
    fake_redis: object,
) -> None:
    """Expo returns DeviceNotRegistered → returns False, clears token in DB."""
    _, shield = await _make_shield_with_token(db_session, fake_redis)
    shield_id = shield.id

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "status": "error",
            "details": {"error": "DeviceNotRegistered"},
        }
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(push_service.settings, "mock_push", False),
        patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await push_service.send_to_shield(
            shield_id,
            title="SOS Alert",
            body="Help needed",
            data={"type": "sos_alert"},
            db=db_session,
        )

    assert result is False

    # Reload shield from DB and confirm token was cleared
    await db_session.refresh(shield)
    assert shield.expo_push_token is None
    assert shield.token_updated_at is None


# ── device registration endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_device_registration_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: object,
) -> None:
    """PATCH /shields/me/device with valid token → 200, token stored in DB."""
    user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000011", lat=49.1427, lng=9.2109
    )

    resp = await client.patch(
        "/api/v1/shields/me/device",
        json={"expo_push_token": _VALID_TOKEN},
        headers=auth_headers(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["registered"] is True
    assert body["token_preview"] == _VALID_TOKEN_PREVIEW

    # Confirm persisted in DB
    await db_session.refresh(shield)
    assert shield.expo_push_token == _VALID_TOKEN
    assert shield.token_updated_at is not None


@pytest.mark.asyncio
async def test_device_registration_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: object,
) -> None:
    """Calling the endpoint twice with the same token is safe."""
    user, shield = await make_shield(
        db_session, fake_redis, phone="+491700000012", lat=49.1427, lng=9.2109
    )

    for _ in range(2):
        resp = await client.patch(
            "/api/v1/shields/me/device",
            json={"expo_push_token": _VALID_TOKEN},
            headers=auth_headers(user),
        )
        assert resp.status_code == 200

    await db_session.refresh(shield)
    assert shield.expo_push_token == _VALID_TOKEN


@pytest.mark.asyncio
async def test_device_registration_invalid_token_format(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: object,
) -> None:
    """PATCH /shields/me/device with non-Expo token → 422."""
    user, _ = await make_shield(
        db_session, fake_redis, phone="+491700000013", lat=49.1427, lng=9.2109
    )

    resp = await client.patch(
        "/api/v1/shields/me/device",
        json={"expo_push_token": "not-a-real-token"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 422
