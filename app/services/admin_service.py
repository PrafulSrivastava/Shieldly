import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incidents import Incident, IncidentStatus
from app.models.shields import Shield, ShieldStatus
from app.models.users import User
from app.schemas.admin import (
    AdminIncidentItem,
    AdminIncidentListResponse,
    AdminStatsResponse,
    PendingShieldItem,
    PendingShieldsResponse,
    VerifyShieldResponse,
)

logger = logging.getLogger(__name__)


async def list_pending_shields(*, db: AsyncSession) -> PendingShieldsResponse:
    """Return all shield applications that are awaiting admin review."""
    result = await db.execute(
        select(Shield, User)
        .join(User, Shield.user_id == User.id)
        .where(Shield.status == ShieldStatus.pending)
        .order_by(User.created_at.asc())
    )
    rows = result.all()

    items = [
        PendingShieldItem(
            shield_id=shield.id,
            user_id=user.id,
            name=user.name,
            phone=user.phone,
            commitment_signed=shield.commitment_signed,
            applied_at=user.created_at,
        )
        for shield, user in rows
    ]

    return PendingShieldsResponse(total=len(items), shields=items)


async def verify_shield(
    shield_id: UUID,
    approved: bool,
    rejection_reason: str | None,
    *,
    db: AsyncSession,
) -> VerifyShieldResponse:
    """
    Approve or reject a Shield volunteer.

    - Approved: sets id_verified=True, status='inactive'. The shield then
      activates themselves via PATCH /shields/me/status.
    - Rejected: sets status='rejected'. The shield can re-apply via
      POST /shields/apply.
    """
    result = await db.execute(select(Shield).where(Shield.id == shield_id))
    shield: Shield | None = result.scalar_one_or_none()

    if shield is None:
        raise HTTPException(status_code=404, detail="Shield not found")

    if shield.status not in (ShieldStatus.pending, ShieldStatus.rejected):
        raise HTTPException(
            status_code=409,
            detail=f"Shield is already '{shield.status.value}' and cannot be re-verified",
        )

    if approved:
        shield.id_verified = True
        shield.status = ShieldStatus.inactive
        message = "Shield approved; they can now activate themselves"
    else:
        shield.id_verified = False
        shield.status = ShieldStatus.rejected
        if rejection_reason:
            logger.info(
                "Shield %s rejected. Reason: %s",
                shield_id,
                rejection_reason,
            )
        message = "Shield application rejected"

    db.add(shield)

    return VerifyShieldResponse(
        shield_id=shield.id,
        id_verified=shield.id_verified,
        status=shield.status.value,
        message=message,
    )


async def list_incidents(
    status: str | None,
    limit: int,
    offset: int,
    *,
    db: AsyncSession,
) -> AdminIncidentListResponse:
    """Paginated incident list with optional status filter."""
    base = select(Incident)

    if status is not None:
        try:
            status_enum = IncidentStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be: active | resolved | escalated",
            )
        base = base.where(Incident.status == status_enum)

    count_result = await db.execute(
        select(func.count(Incident.id)).select_from(base.subquery())
    )
    total: int = count_result.scalar_one()

    rows_result = await db.execute(
        base.order_by(Incident.triggered_at.desc()).limit(limit).offset(offset)
    )
    incidents = rows_result.scalars().all()

    items = [
        AdminIncidentItem(
            incident_id=inc.id,
            triggered_by=inc.triggered_by,
            trigger_lat=inc.trigger_lat,
            trigger_lng=inc.trigger_lng,
            status=inc.status.value,
            triggered_at=inc.triggered_at,
            resolved_at=inc.resolved_at,
        )
        for inc in incidents
    ]

    return AdminIncidentListResponse(
        total=total,
        limit=limit,
        offset=offset,
        incidents=items,
    )


async def get_stats(*, db: AsyncSession) -> AdminStatsResponse:
    """Aggregate operational statistics across all entities."""
    total_users: int = (
        await db.execute(select(func.count(User.id)))
    ).scalar_one()

    total_shields: int = (
        await db.execute(select(func.count(Shield.id)))
    ).scalar_one()

    active_shields: int = (
        await db.execute(
            select(func.count(Shield.id)).where(Shield.status == ShieldStatus.active)
        )
    ).scalar_one()

    total_incidents: int = (
        await db.execute(select(func.count(Incident.id)))
    ).scalar_one()

    resolved_incidents: int = (
        await db.execute(
            select(func.count(Incident.id)).where(
                Incident.status == IncidentStatus.resolved
            )
        )
    ).scalar_one()

    # Average seconds from SOS trigger to incident resolution (resolved only)
    avg_rt: float | None = (
        await db.execute(
            select(
                func.avg(
                    extract("epoch", Incident.resolved_at - Incident.triggered_at)
                )
            ).where(
                Incident.status == IncidentStatus.resolved,
                Incident.resolved_at.isnot(None),
            )
        )
    ).scalar_one_or_none()

    return AdminStatsResponse(
        total_users=total_users,
        total_shields=total_shields,
        active_shields=active_shields,
        total_incidents=total_incidents,
        resolved_incidents=resolved_incidents,
        avg_response_time_seconds=round(avg_rt, 2) if avg_rt is not None else None,
    )
