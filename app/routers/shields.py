import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.shields import Shield
from app.models.users import User, UserRole
from app.redis_client import get_redis
from app.routers.auth import get_current_user
from app.schemas.shields import (
    ApplyShieldRequest,
    ApplyShieldResponse,
    ShieldProfileResponse,
    UpdateActiveHoursRequest,
    UpdateActiveHoursResponse,
    UpdateShieldStatusRequest,
    UpdateShieldStatusResponse,
)
from app.services import shield_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_current_shield(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Shield]:
    """
    Dependency: verifies the caller has role='shield' and loads their shield
    record.  Does NOT enforce id_verified — use `require_shield` from auth for
    endpoints that require a fully verified, active shield.
    """
    if user.role != UserRole.shield:
        raise HTTPException(status_code=403, detail="Shield role required")

    result = await db.execute(select(Shield).where(Shield.user_id == user.id))
    shield: Shield | None = result.scalar_one_or_none()

    if shield is None:
        raise HTTPException(status_code=404, detail="Shield profile not found")

    return user, shield


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/apply", response_model=ApplyShieldResponse, status_code=201)
async def apply_as_shield(
    body: ApplyShieldRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplyShieldResponse:
    """
    Apply to become a Shield volunteer.

    - Any authenticated user may call this endpoint.
    - Promotes the caller's role to 'shield' and creates (or resets) a shield
      record with status='pending' and id_verified=False.
    - A rejected shield may re-apply — their status returns to 'pending'.
    """
    if not body.commitment_accepted:
        raise HTTPException(
            status_code=422,
            detail="commitment_accepted must be true to submit an application",
        )

    return await shield_service.apply_as_shield(
        user,
        name=body.name,
        commitment_accepted=body.commitment_accepted,
        db=db,
    )


@router.patch("/me/status", response_model=UpdateShieldStatusResponse)
async def update_my_status(
    body: UpdateShieldStatusRequest,
    user_and_shield: tuple[User, Shield] = Depends(_get_current_shield),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> UpdateShieldStatusResponse:
    """
    Toggle between active and inactive.

    - Going active requires id_verified=True (admin must have approved first).
    - Going inactive removes the shield's live location from Redis.
    """
    _, shield = user_and_shield
    return await shield_service.update_shield_status(
        shield,
        status=body.status,
        db=db,
        redis=redis,
    )


@router.patch("/me/active-hours", response_model=UpdateActiveHoursResponse)
async def update_my_active_hours(
    body: UpdateActiveHoursRequest,
    user_and_shield: tuple[User, Shield] = Depends(_get_current_shield),
    db: AsyncSession = Depends(get_db),
) -> UpdateActiveHoursResponse:
    """Set the preferred availability window (both times in HH:MM format)."""
    _, shield = user_and_shield
    return await shield_service.update_active_hours(
        shield,
        active_hours_start=body.active_hours_start,
        active_hours_end=body.active_hours_end,
        db=db,
    )


@router.get("/me", response_model=ShieldProfileResponse)
async def get_my_profile(
    user_and_shield: tuple[User, Shield] = Depends(_get_current_shield),
) -> ShieldProfileResponse:
    """Return the caller's shield profile, status, active hours, and verification state."""
    user, shield = user_and_shield
    return await shield_service.get_shield_profile(user, shield)
