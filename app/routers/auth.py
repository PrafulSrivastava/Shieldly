import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.shields import Shield
from app.models.users import User, UserRole
from app.schemas.auth import TokenResponse, VerifyTokenRequest
from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    upsert_user,
    verify_firebase_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_bearer = HTTPBearer()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/verify-token", response_model=TokenResponse, status_code=200)
async def verify_token(
    body: VerifyTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange a Firebase phone OTP ID token for a ShieldHer JWT.

    - Verifies the Firebase token (or uses the mock verifier in dev).
    - Upserts the user record in Postgres.
    - Returns a signed HS256 JWT valid for 30 days.
    """
    firebase_data = await verify_firebase_token(body.firebase_id_token)

    user = await upsert_user(
        db,
        phone=firebase_data["phone"],
        firebase_uid=firebase_data["uid"],
        name=body.name,
        role=body.role,
        emergency_contact_name=body.emergency_contact_name,
        emergency_contact_phone=body.emergency_contact_phone,
    )

    token = create_access_token(user)

    return TokenResponse(
        access_token=token,
        user_id=user.id,
        phone=user.phone,
        role=user.role.value,
    )


# ── Reusable auth dependencies ────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — extracts and validates the Bearer JWT, then loads the
    User from the database.  Raises HTTP 401 on any failure.

    Usage::

        @router.get("/me")
        async def me(user: User = Depends(get_current_user)):
            ...
    """
    payload = decode_access_token(credentials.credentials)

    user_id: str | None = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Malformed token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    return user


async def require_shield(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Shield:
    """
    FastAPI dependency — asserts the caller is a verified Shield volunteer.
    Raises HTTP 403 if the user's role is not 'shield' or their identity has
    not yet been verified by an admin.

    Returns the Shield profile (not the User) so callers get direct access to
    shield-specific fields (location, status, active hours, etc.).

    Usage::

        @router.post("/respond")
        async def respond(shield: Shield = Depends(require_shield)):
            ...
    """
    if user.role != UserRole.shield:
        raise HTTPException(status_code=403, detail="Shield role required")

    result = await db.execute(select(Shield).where(Shield.user_id == user.id))
    shield: Shield | None = result.scalar_one_or_none()

    if shield is None or not shield.id_verified:
        raise HTTPException(
            status_code=403,
            detail="Shield identity verification pending",
        )

    return shield
