"""ElevenLabs Conversational AI service.

Handles server-side token generation for the ElevenLabs client SDK.
The API key never leaves the backend — only a short-lived signed URL
is returned to the frontend.
"""

import logging
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

_SIGNED_URL_ENDPOINT = (
    "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"
)
_MOCK_SIGNED_URL = "wss://mock-elevenlabs-url/conversation/mock-session-id"
_HTTP_TIMEOUT = 10.0


async def get_signed_conversation_url(
    incident_id: UUID, db: AsyncSession
) -> str:
    """Call ElevenLabs to obtain a short-lived signed WebSocket URL.

    The frontend passes this URL to the ElevenLabs SDK to start a
    conversation session.  The API key never leaves the server.
    """
    if settings.mock_elevenlabs:
        logger.info(
            "[MOCK ELEVENLABS] Returning mock signed URL for incident %s",
            incident_id,
        )
        return _MOCK_SIGNED_URL

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.get(
            _SIGNED_URL_ENDPOINT,
            headers={"xi-api-key": settings.elevenlabs_api_key},
            params={"agent_id": settings.elevenlabs_agent_id},
        )
        response.raise_for_status()
        return response.json()["signed_url"]
