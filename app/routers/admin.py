import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.admin import (
    AdminIncidentListResponse,
    AdminStatsResponse,
    PendingShieldsResponse,
    VerifyShieldRequest,
    VerifyShieldResponse,
)
from app.services import admin_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_admin(
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    """
    Static API-key guard for all admin endpoints.

    Clients must send:  X-Admin-Key: <value of ADMIN_API_KEY env var>

    Replace with full RBAC in a future iteration.
    """
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing admin API key")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/shields/pending",
    response_model=PendingShieldsResponse,
    dependencies=[Depends(_require_admin)],
)
async def list_pending_shields(
    db: AsyncSession = Depends(get_db),
) -> PendingShieldsResponse:
    """List all shield applications awaiting review, ordered by application date."""
    return await admin_service.list_pending_shields(db=db)


@router.patch(
    "/shields/{shield_id}/verify",
    response_model=VerifyShieldResponse,
    dependencies=[Depends(_require_admin)],
)
async def verify_shield(
    shield_id: UUID,
    body: VerifyShieldRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyShieldResponse:
    """
    Approve or reject a shield volunteer application.

    - Approved: sets id_verified=True, status='inactive' — shield activates themselves.
    - Rejected: sets status='rejected' — shield may re-apply via POST /shields/apply.
    """
    return await admin_service.verify_shield(
        shield_id,
        approved=body.approved,
        rejection_reason=body.rejection_reason,
        db=db,
    )


@router.get(
    "/incidents",
    response_model=AdminIncidentListResponse,
    dependencies=[Depends(_require_admin)],
)
async def list_incidents(
    status: str | None = Query(
        default=None,
        description="Filter by status: active | resolved | escalated",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AdminIncidentListResponse:
    """Paginated list of all incidents with optional status filter."""
    return await admin_service.list_incidents(status, limit, offset, db=db)


@router.get(
    "/stats",
    response_model=AdminStatsResponse,
    dependencies=[Depends(_require_admin)],
)
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    """
    System-wide operational statistics.

    Returns total counts and average SOS-to-resolution time across all
    resolved incidents.
    """
    return await admin_service.get_stats(db=db)
