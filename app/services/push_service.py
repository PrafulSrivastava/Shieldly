"""Expo Push Notification service.

Sends push notifications to Shield volunteers via the Expo Push API, which
abstracts FCM (Android) and APNs (iOS) behind a single HTTP endpoint.

Mock mode (MOCK_PUSH=true, default for local dev):
  Logs the notification to the console — no HTTP call, no real device needed.

Production (MOCK_PUSH=false):
  POSTs to https://exp.host/--/api/v2/push/send.
  Handles DeviceNotRegistered by clearing the stale token from the DB.

Push failures NEVER raise — they are caught, logged, and return False so that
the SOS trigger flow is never interrupted by a notification problem.
"""

import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.shields import Shield

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_to_shield(
    shield_id: UUID,
    title: str,
    body: str,
    data: dict[str, Any],
    db: AsyncSession,
) -> bool:
    """Fire a push notification to a single Shield volunteer.

    Returns True if the notification was delivered (or mock-logged), False if
    there is no token or delivery failed.  Never raises.
    """
    try:
        shield: Shield | None = await db.get(Shield, shield_id)
        if shield is None or not shield.expo_push_token:
            logger.warning(
                "[PUSH] shield %s has no expo_push_token — skipping", shield_id
            )
            return False

        token = shield.expo_push_token
        token_preview = token[-8:]

        if settings.mock_push:
            logger.info(
                "[MOCK PUSH → …%s | shield=%s] %s: %s | data=%s",
                token_preview,
                shield_id,
                title,
                body,
                data,
            )
            return True

        payload: dict[str, Any] = {
            "to": token,
            "title": title,
            "body": body,
            "data": data,
            "sound": "default",
            "priority": "high",
            "channelId": "sos-alerts",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _EXPO_PUSH_URL,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()

        ticket: dict[str, Any] = result.get("data", {})
        status: str = ticket.get("status", "")

        if status == "ok":
            logger.info(
                "[PUSH OK → …%s | shield=%s] %s", token_preview, shield_id, title
            )
            return True

        if status == "error":
            details: dict[str, Any] = ticket.get("details", {})
            error_code: str = details.get("error", "")
            if error_code == "DeviceNotRegistered":
                logger.warning(
                    "[PUSH] DeviceNotRegistered for shield %s (…%s) — clearing token",
                    shield_id,
                    token_preview,
                )
                await clear_expired_token(db, shield_id)
            else:
                logger.warning(
                    "[PUSH] Expo error for shield %s (…%s): %s",
                    shield_id,
                    token_preview,
                    error_code or ticket,
                )
            return False

        logger.warning(
            "[PUSH] Unexpected Expo response for shield %s: %s", shield_id, result
        )
        return False

    except Exception:
        logger.exception("[PUSH] Failed to send notification to shield %s", shield_id)
        return False


async def clear_expired_token(db: AsyncSession, shield_id: UUID) -> None:
    """Wipe a stale/expired push token so it isn't retried."""
    shield: Shield | None = await db.get(Shield, shield_id)
    if shield:
        shield.expo_push_token = None
        shield.token_updated_at = None
        await db.commit()
