import logging
from datetime import time

import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shields import Shield, ShieldStatus
from app.models.users import User, UserRole
from app.schemas.shields import (
    ApplyShieldResponse,
    ShieldProfileResponse,
    UpdateActiveHoursResponse,
    UpdateShieldStatusResponse,
)

logger = logging.getLogger(__name__)

_SHIELD_LOCATION_KEY = "shieldher:shield:location:{shield_id}"


async def apply_as_shield(
    user: User,
    name: str,
    commitment_accepted: bool,
    *,
    db: AsyncSession,
) -> ApplyShieldResponse:
    """
    Register or re-register the authenticated user as a Shield volunteer.

    - Updates the user's name and promotes role to 'shield'.
    - Creates a shield record if one doesn't exist, or resets an existing one
      back to pending (covers re-application after rejection).
    """
    user.name = name
    user.role = UserRole.shield
    db.add(user)

    result = await db.execute(select(Shield).where(Shield.user_id == user.id))
    shield: Shield | None = result.scalar_one_or_none()

    if shield is None:
        shield = Shield(
            user_id=user.id,
            status=ShieldStatus.pending,
            id_verified=False,
            commitment_signed=commitment_accepted,
        )
        db.add(shield)
    else:
        shield.status = ShieldStatus.pending
        shield.id_verified = False
        shield.commitment_signed = commitment_accepted
        db.add(shield)

    await db.flush()

    return ApplyShieldResponse(
        shield_id=shield.id,
        status=ShieldStatus.pending.value,
        message="Your application is under review",
    )


async def update_shield_status(
    shield: Shield,
    status: str,
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> UpdateShieldStatusResponse:
    """
    Toggle a shield's operational status.

    Going active requires id_verified=True — the admin must have approved the
    shield first. Going inactive removes the shield's live location from Redis
    so they no longer appear in nearby-shield queries.
    """
    new_status = ShieldStatus(status)

    if new_status == ShieldStatus.active and not shield.id_verified:
        raise HTTPException(
            status_code=403,
            detail="Identity verification required before going active",
        )

    shield.status = new_status
    db.add(shield)
    await db.flush()

    if new_status == ShieldStatus.inactive:
        location_key = _SHIELD_LOCATION_KEY.format(shield_id=str(shield.id))
        await redis.delete(location_key)

    return UpdateShieldStatusResponse(
        shield_id=shield.id,
        status=new_status.value,
    )


def _parse_hhmm(value: str) -> time:
    """Convert a validated HH:MM string into a datetime.time."""
    h, m = value.split(":")
    return time(int(h), int(m))


async def update_active_hours(
    shield: Shield,
    active_hours_start: str,
    active_hours_end: str,
    *,
    db: AsyncSession,
) -> UpdateActiveHoursResponse:
    """Update the shield's preferred availability window."""
    shield.active_hours_start = _parse_hhmm(active_hours_start)
    shield.active_hours_end = _parse_hhmm(active_hours_end)
    db.add(shield)
    await db.flush()

    return UpdateActiveHoursResponse(
        shield_id=shield.id,
        active_hours_start=active_hours_start,
        active_hours_end=active_hours_end,
    )


async def get_shield_profile(
    user: User,
    shield: Shield,
) -> ShieldProfileResponse:
    """Build the full shield profile response from the ORM objects."""
    return ShieldProfileResponse(
        shield_id=shield.id,
        user_id=user.id,
        name=user.name,
        phone=user.phone,
        status=shield.status.value,
        id_verified=shield.id_verified,
        commitment_signed=shield.commitment_signed,
        active_hours_start=(
            shield.active_hours_start.strftime("%H:%M")
            if shield.active_hours_start is not None
            else None
        ),
        active_hours_end=(
            shield.active_hours_end.strftime("%H:%M")
            if shield.active_hours_end is not None
            else None
        ),
    )
