"""Brevo Transactional SMS service.

Uses Brevo's REST API directly via httpx per project convention.
Set MOCK_SMS=true in .env to skip real API calls during local development —
messages are logged to the console instead.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/sms"


async def _send_brevo_sms(recipient_phone: str, message: str) -> bool:
    """Core Brevo SMS delivery function.

    recipient_phone must be E.164 format: +491700000001
    Returns True on success, False on any failure.
    Never raises — SMS failure must not break the SOS flow.
    """
    try:
        if settings.mock_sms:
            logger.info(
                "[MOCK SMS → %s]\n%s", recipient_phone[-4:], message
            )
            return True

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                BREVO_SMS_URL,
                headers={
                    "api-key": settings.brevo_api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "sender": settings.brevo_sender_name,
                    "recipient": recipient_phone,
                    "content": message,
                    "type": "transactional",
                },
            )

            if response.status_code == 201:
                logger.info("SMS delivered via Brevo to …%s", recipient_phone[-4:])
                return True
            else:
                logger.error(
                    "Brevo SMS failed — status %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return False

    except Exception:
        logger.exception("Brevo SMS exception for recipient ending …%s", recipient_phone[-4:])
        return False


async def send_emergency_contact_sos(
    contact_phone: str,
    person_name: str,
    lat: float,
    lng: float,
    tracking_url: str,
) -> None:
    """Fires immediately on SOS trigger as a BackgroundTask.

    Sends emergency contact the live tracking link.
    """
    message = (
        f"{person_name} has triggered a safety alert on ShieldHer.\n"
        f"Track her live location here: {tracking_url}\n"
        f"This link updates in real time. No login needed."
    )
    await _send_brevo_sms(contact_phone, message)


async def send_emergency_contact_all_clear(
    contact_phone: str,
    person_name: str,
) -> None:
    """Fires on all-clear / resolve as a BackgroundTask."""
    message = (
        f"{person_name} is safe. "
        f"The ShieldHer safety alert has been resolved."
    )
    await _send_brevo_sms(contact_phone, message)


async def send_emergency_contact_escalation(
    contact_phone: str,
    person_name: str,
    tracking_url: str,
) -> None:
    """Fires at T+90s if no Shield has responded."""
    message = (
        f"URGENT: {person_name} triggered a ShieldHer alert "
        f"and no responders have reached her yet.\n"
        f"Live location: {tracking_url}"
    )
    await _send_brevo_sms(contact_phone, message)


async def trigger_n8n_all_clear(
    incident_id: str,
    person_name: str,
    contact_phone: str,
    contact_name: str,
) -> None:
    """Keep the n8n webhook for workflow automation.

    n8n can use Brevo or any other provider on its side.
    """
    try:
        if settings.mock_sms:
            logger.info("[MOCK n8n] All-clear webhook for incident %s", incident_id)
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                settings.n8n_all_clear_webhook_url,
                json={
                    "incident_id": incident_id,
                    "person_name": person_name,
                    "contact_phone": contact_phone,
                    "contact_name": contact_name,
                    "message": f"{person_name} is safe. The ShieldHer alert has been resolved.",
                },
            )
    except Exception:
        logger.exception("n8n all-clear webhook failed for incident %s", incident_id)
