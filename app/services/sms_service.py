"""Twilio SMS service.

Uses Twilio's REST API directly via httpx (not the Twilio SDK) per project
convention.  Set MOCK_SMS=true in .env to skip real API calls during local
development — messages are printed to the console instead.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts"
    "/{account_sid}/Messages.json"
)


async def send_emergency_contact_sos(
    incident_id: str,
    person_name: str,
    contact_phone: str,
    lat: float,
    lng: float,
) -> None:
    """Notify an emergency contact that an SOS has been triggered.

    Includes a live Google Maps link to the trigger location.
    Called as a FastAPI BackgroundTask — must not raise.
    """
    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    body = (
        f"{person_name} has triggered an emergency alert. "
        f"Live location: {maps_link} \u2014 ShieldHer"
    )
    await _send(to=contact_phone, body=body, context=f"SOS incident_id={incident_id}")


async def send_emergency_contact_all_clear(
    person_name: str,
    contact_phone: str,
) -> None:
    """Notify an emergency contact that the person is safe.

    Called as a FastAPI BackgroundTask — must not raise.
    """
    body = f"{person_name} is safe. The ShieldHer alert has been resolved."
    await _send(to=contact_phone, body=body, context="all-clear")


async def _send(to: str, body: str, context: str = "") -> None:
    """Dispatch a single SMS message; swallows errors so background tasks stay alive."""
    if settings.mock_sms:
        print(
            f"[SMS MOCK] to={to!r} | context={context!r} | body={body!r}"
        )
        logger.info("[SMS MOCK] to=%s | context=%s | body=%r", to, context, body)
        return

    url = _TWILIO_MESSAGES_URL.format(account_sid=settings.twilio_account_sid)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={
                    "To": to,
                    "From": settings.twilio_phone_number,
                    "Body": body,
                },
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
        if resp.status_code in (200, 201):
            logger.info(
                "SMS delivered: to=%s context=%s sid=%s",
                to,
                context,
                resp.json().get("sid", "unknown"),
            )
        else:
            logger.error(
                "Twilio SMS failed: status=%s context=%s response=%s",
                resp.status_code,
                context,
                resp.text,
            )
    except Exception:
        logger.exception("Failed to deliver SMS: to=%s context=%s", to, context)
