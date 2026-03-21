"""Push notification service.

MVP: all notifications are logged to the console so local testing works
without any external credentials.

TODO: Replace _send_push with a real provider before going to production:
  - Expo Push Notifications (recommended for React Native clients):
      POST https://exp.host/--/api/v2/push/send
      Docs: https://docs.expo.dev/push-notifications/sending-notifications/
  - Web Push (RFC 8030) via the `pywebpush` library:
      Docs: https://web.dev/push-notifications-overview/
  Production checklist:
    1. Add an `expo_push_token` (or web-push subscription JSON) column to the
       `shields` table and populate it on first device registration.
    2. Look the token up by shield_id and POST to the provider's send endpoint.
    3. Handle 429 rate-limits and DeviceNotRegistered / token-expired errors
       by removing stale tokens from the DB.
"""

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def send_to_shield(
    shield_id: UUID,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Fire a push notification to a single Shield volunteer.

    Currently logs to the console (MVP).  Swap the body of this function for
    real push delivery without touching any call-sites.
    """
    logger.info(
        "[PUSH] shield_id=%s | title=%r | body=%r | data=%s",
        shield_id,
        title,
        body,
        data or {},
    )
