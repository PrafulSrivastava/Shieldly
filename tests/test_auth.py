"""Tests for the auth domain.

Coverage
--------
- POST /api/v1/auth/verify-token creates a new Person user
- POST /api/v1/auth/verify-token creates a new Shield user (with Shield profile)
- Calling verify-token twice with the same phone upserts — no duplicate rows
- JWT encode + decode round-trip via auth_service helpers
- Invalid JWT on a protected endpoint → 401
- Missing Bearer token on a protected endpoint → 403
- get_current_user returns the right user for a valid token
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shields import Shield
from app.models.users import User, UserRole
from app.services.auth_service import create_access_token, decode_access_token
from tests.conftest import auth_headers, make_person


# ── /verify-token ─────────────────────────────────────────────────────────────


async def test_verify_token_creates_person_user(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/verify-token",
        json={
            "firebase_id_token": "+491700000001",
            "name": "Alice Person",
            "role": "person",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["phone"] == "+491700000001"
    assert data["role"] == "person"
    assert "access_token" in data
    assert "user_id" in data


async def test_verify_token_creates_shield_user_and_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    resp = await client.post(
        "/api/v1/auth/verify-token",
        json={
            "firebase_id_token": "+491700000002",
            "name": "Bob Shield",
            "role": "shield",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["role"] == "shield"
    user_id = data["user_id"]

    # Shield profile must have been auto-created
    from uuid import UUID

    result = await db_session.execute(
        select(Shield).where(Shield.user_id == UUID(user_id))
    )
    shield = result.scalar_one_or_none()
    assert shield is not None, "Shield profile was not created for shield user"
    assert shield.id_verified is False
    assert shield.status.value == "pending"


async def test_verify_token_is_idempotent(client: AsyncClient) -> None:
    """Same phone twice must upsert, not duplicate."""
    payload = {
        "firebase_id_token": "+491700000003",
        "name": "Carol",
        "role": "person",
    }
    r1 = await client.post("/api/v1/auth/verify-token", json=payload)
    r2 = await client.post("/api/v1/auth/verify-token", json=payload)
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["user_id"] == r2.json()["user_id"]


async def test_verify_token_with_emergency_contact(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/verify-token",
        json={
            "firebase_id_token": "+491700000004",
            "name": "Dana",
            "role": "person",
            "emergency_contact_name": "Mom",
            "emergency_contact_phone": "+491700000099",
        },
    )
    assert resp.status_code == 200


# ── JWT helpers ───────────────────────────────────────────────────────────────


async def test_jwt_encode_decode_round_trip() -> None:
    """create_access_token + decode_access_token must be inverse operations."""
    user = User(
        id=uuid4(),
        phone="+491700000010",
        name="JWT Tester",
        role=UserRole.person,
        is_active=True,
    )
    token = create_access_token(user)
    payload = decode_access_token(token)

    assert payload["user_id"] == str(user.id)
    assert payload["phone"] == "+491700000010"
    assert payload["role"] == "person"


async def test_decode_invalid_token_raises_http_401(client: AsyncClient) -> None:
    """A tampered / garbage token on an authenticated endpoint returns 401."""
    resp = await client.get(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert resp.status_code == 401


async def test_missing_bearer_token_returns_403(client: AsyncClient) -> None:
    """Omitting the Authorization header entirely returns 403 (no credentials)."""
    resp = await client.get(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 403


# ── get_current_user dependency ───────────────────────────────────────────────


async def test_authenticated_request_identifies_correct_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Bearer token must resolve to the right User via get_current_user."""
    user = await make_person(db_session, phone="+491700000020")

    # Hit an authenticated endpoint that only requires get_current_user (no
    # role check).  A non-existent incident returns 404, proving auth passed.
    resp = await client.get(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(user),
    )
    # 404 means the auth layer passed (401/403 would mean auth failed)
    assert resp.status_code == 404


async def test_inactive_user_token_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A deactivated user must not authenticate even with a valid JWT."""
    user = User(
        id=uuid4(),
        phone="+491700000021",
        name="Inactive User",
        role=UserRole.person,
        firebase_uid="test-uid-inactive",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/shields/me", headers=auth_headers(user)
    )
    assert resp.status_code == 401
