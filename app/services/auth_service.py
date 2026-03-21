import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.shields import Shield, ShieldStatus
from app.models.users import User, UserRole

logger = logging.getLogger(__name__)

_JWT_EXPIRE_DAYS = 30


# ── Firebase token verification ───────────────────────────────────────────────

async def verify_firebase_token(id_token: str) -> dict[str, str]:
    """
    Verifies a Firebase ID token and returns {"phone": "+1...", "uid": "..."}.

    Mock mode (MOCK_FIREBASE=true): treats the raw token as the phone number
    when it starts with "+", otherwise falls back to +15555550000.  This lets
    tests pass any E.164 number as the token without real Firebase credentials.
    """
    if settings.mock_firebase:
        return _mock_verify(id_token)
    return await _real_verify(id_token)


def _mock_verify(id_token: str) -> dict[str, str]:
    phone = id_token if id_token.startswith("+") else "+15555550000"
    uid = f"mock-uid-{phone}"
    logger.debug("MOCK_FIREBASE: resolved token → phone=%s uid=%s", phone, uid)
    return {"phone": phone, "uid": uid}


async def _real_verify(id_token: str) -> dict[str, str]:
    """
    Calls the Firebase Identity Toolkit REST API to verify the ID token.
    Returns the phone number and Firebase UID on success.
    """
    if not settings.firebase_api_key:
        raise HTTPException(
            status_code=500,
            detail="FIREBASE_API_KEY is not configured",
        )

    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:lookup"
        f"?key={settings.firebase_api_key}"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json={"idToken": id_token})

    if resp.status_code != 200:
        logger.warning(
            "Firebase token verification failed: status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        raise HTTPException(status_code=401, detail="Invalid Firebase token")

    data = resp.json()
    users = data.get("users", [])
    if not users:
        raise HTTPException(status_code=401, detail="Firebase token has no associated user")

    firebase_user = users[0]
    phone: str | None = firebase_user.get("phoneNumber")
    if not phone:
        raise HTTPException(status_code=401, detail="Firebase account has no phone number")

    return {"phone": phone, "uid": firebase_user["localId"]}


# ── User upsert ───────────────────────────────────────────────────────────────

async def upsert_user(
    db: AsyncSession,
    *,
    phone: str,
    firebase_uid: str,
    name: str,
    role: str,
    emergency_contact_name: str | None,
    emergency_contact_phone: str | None,
) -> User:
    """
    Creates or updates the User row for the given phone number.

    On first-time registration with role='shield', a Shield profile row is
    also created (id_verified=False, status=pending) so the shield can be
    verified by an admin separately.

    On updates, if the user is upgrading from 'person' → 'shield' and no
    Shield profile exists yet, one is created automatically.
    """
    result = await db.execute(select(User).where(User.phone == phone))
    user: User | None = result.scalar_one_or_none()

    user_role = UserRole(role)

    if user is None:
        user = User(
            id=uuid4(),
            phone=phone,
            name=name,
            role=user_role,
            firebase_uid=firebase_uid,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
        )
        db.add(user)
        await db.flush()
        logger.info("Created new user id=%s phone=%s role=%s", user.id, phone, role)

        if user_role == UserRole.shield:
            await _ensure_shield_profile(db, user.id)
    else:
        was_person = user.role == UserRole.person
        user.name = name
        user.role = user_role
        user.firebase_uid = firebase_uid
        if emergency_contact_name is not None:
            user.emergency_contact_name = emergency_contact_name
        if emergency_contact_phone is not None:
            user.emergency_contact_phone = emergency_contact_phone

        await db.flush()
        logger.info("Updated existing user id=%s", user.id)

        if user_role == UserRole.shield and was_person:
            await _ensure_shield_profile(db, user.id)

    return user


async def _ensure_shield_profile(db: AsyncSession, user_id: UUID) -> None:
    result = await db.execute(select(Shield).where(Shield.user_id == user_id))
    if result.scalar_one_or_none() is None:
        shield = Shield(
            id=uuid4(),
            user_id=user_id,
            status=ShieldStatus.pending,
            id_verified=False,
            commitment_signed=False,
        )
        db.add(shield)
        await db.flush()
        logger.info("Created shield profile for user_id=%s", user_id)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_JWT_EXPIRE_DAYS)
    payload: dict[str, object] = {
        "user_id": str(user.id),
        "phone": user.phone,
        "role": user.role.value,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, str]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from exc
