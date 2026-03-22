"""Tests for Brevo Transactional SMS service.

Coverage
--------
- send_emergency_contact_sos: mock mode logs without HTTP call
- send_emergency_contact_sos: real mode calls Brevo, asserts URL/headers/body
- send_emergency_contact_sos: Brevo failure (400) doesn't raise
- send_emergency_contact_all_clear: real mode, message contains "is safe"
- send_emergency_contact_escalation: real mode, message contains "URGENT"
- SMS functions never log full phone numbers — only last 4 digits
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import sms_service
from app.services.sms_service import (
    BREVO_SMS_URL,
    send_emergency_contact_all_clear,
    send_emergency_contact_escalation,
    send_emergency_contact_sos,
)

_PHONE = "+491700000099"
_NAME = "Test Person"
_LAT = 49.1427
_LNG = 9.2109
_TRACKING_URL = f"https://maps.google.com/?q={_LAT},{_LNG}"


# ── Mock mode ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_sos_sms_mock_mode(caplog: pytest.LogCaptureFixture) -> None:
    """MOCK_SMS=true → logs with [MOCK SMS] prefix, no HTTP call made."""
    with (
        patch.object(sms_service.settings, "mock_sms", True),
        patch("app.services.sms_service.httpx.AsyncClient") as mock_http,
    ):
        await send_emergency_contact_sos(
            contact_phone=_PHONE,
            person_name=_NAME,
            lat=_LAT,
            lng=_LNG,
            tracking_url=_TRACKING_URL,
        )

        mock_http.assert_not_called()
        assert any("[MOCK SMS" in r.message for r in caplog.records)


# ── Real Brevo — success ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_sos_sms_real_brevo() -> None:
    """MOCK_SMS=false, Brevo returns 201 → POST to correct URL with right payload."""
    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(sms_service.settings, "mock_sms", False),
        patch.object(sms_service.settings, "brevo_api_key", "test-api-key"),
        patch.object(sms_service.settings, "brevo_sender_name", "ShieldHer"),
        patch("app.services.sms_service.httpx.AsyncClient", return_value=mock_client),
    ):
        await send_emergency_contact_sos(
            contact_phone=_PHONE,
            person_name=_NAME,
            lat=_LAT,
            lng=_LNG,
            tracking_url=_TRACKING_URL,
        )

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args

    assert call_args[0][0] == BREVO_SMS_URL
    assert call_args[1]["headers"]["api-key"] == "test-api-key"
    body = call_args[1]["json"]
    assert body["recipient"] == _PHONE
    assert body["sender"] == "ShieldHer"
    assert _TRACKING_URL in body["content"]


# ── Real Brevo — failure ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_sos_sms_brevo_failure(caplog: pytest.LogCaptureFixture) -> None:
    """Brevo returns 400 → function returns without raising, error logged."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(sms_service.settings, "mock_sms", False),
        patch.object(sms_service.settings, "brevo_api_key", "test-api-key"),
        patch.object(sms_service.settings, "brevo_sender_name", "ShieldHer"),
        patch("app.services.sms_service.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level(logging.ERROR),
    ):
        await send_emergency_contact_sos(
            contact_phone=_PHONE,
            person_name=_NAME,
            lat=_LAT,
            lng=_LNG,
            tracking_url=_TRACKING_URL,
        )

    assert any("Brevo SMS failed" in r.message for r in caplog.records)


# ── All-clear ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_all_clear_sms() -> None:
    """All-clear message contains 'is safe'."""
    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(sms_service.settings, "mock_sms", False),
        patch.object(sms_service.settings, "brevo_api_key", "test-api-key"),
        patch.object(sms_service.settings, "brevo_sender_name", "ShieldHer"),
        patch("app.services.sms_service.httpx.AsyncClient", return_value=mock_client),
    ):
        await send_emergency_contact_all_clear(
            contact_phone=_PHONE,
            person_name=_NAME,
        )

    body = mock_client.post.call_args[1]["json"]
    assert "is safe" in body["content"]


# ── Escalation ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_escalation_sms() -> None:
    """Escalation message contains 'URGENT' and tracking URL."""
    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(sms_service.settings, "mock_sms", False),
        patch.object(sms_service.settings, "brevo_api_key", "test-api-key"),
        patch.object(sms_service.settings, "brevo_sender_name", "ShieldHer"),
        patch("app.services.sms_service.httpx.AsyncClient", return_value=mock_client),
    ):
        await send_emergency_contact_escalation(
            contact_phone=_PHONE,
            person_name=_NAME,
            tracking_url=_TRACKING_URL,
        )

    body = mock_client.post.call_args[1]["json"]
    assert "URGENT" in body["content"]
    assert _TRACKING_URL in body["content"]


# ── Privacy: no full phone in logs ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_sms_never_logs_full_phone_number(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mock-mode log lines must not contain the full phone number."""
    with (
        patch.object(sms_service.settings, "mock_sms", True),
        caplog.at_level(logging.DEBUG),
    ):
        await send_emergency_contact_sos(
            contact_phone=_PHONE,
            person_name=_NAME,
            lat=_LAT,
            lng=_LNG,
            tracking_url=_TRACKING_URL,
        )

    for record in caplog.records:
        assert _PHONE not in record.message, (
            f"Full phone number leaked in log: {record.message}"
        )
        assert _PHONE[-4:] in record.message or "MOCK SMS" in record.message
