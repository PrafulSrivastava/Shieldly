"""Shared pytest fixtures for ShieldHer test suite.

Architecture
------------
- test_engine   (session-scoped) — creates the test DB + schema once per run.
- _clear_tables (function-scoped, autouse) — truncates every table before each
  test so each test starts with a clean slate.
- db_session    (function-scoped) — a live AsyncSession for service-level tests
  that need direct DB access without going through HTTP.
- fake_redis    (function-scoped) — isolated in-process FakeRedis instance.
- client        (function-scoped) — httpx AsyncClient wired to the FastAPI app
  with get_db and get_redis overridden to use test doubles.

Test DB creation
----------------
conftest creates `shieldher_test` automatically if it doesn't exist by
connecting to the main `shieldher` DB as the same postgres user.

Running tests
-------------
  Inside Docker:  docker compose exec app pytest tests/ -v
  Outside Docker: (requires local Postgres + Redis) pytest tests/ -v
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import asyncpg
import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure all ORM models are registered on Base.metadata before create_all
import app.models  # noqa: F401
from app.database import Base, get_db
from app.main import app
from app.models.shields import Shield, ShieldStatus
from app.models.users import User, UserRole
from app.redis_client import get_redis
from app.services.auth_service import create_access_token

logger = logging.getLogger(__name__)

TEST_DATABASE_URL: str = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://shieldher:shieldher@localhost:5433/shieldher_test",
)


# ── DB bootstrap ──────────────────────────────────────────────────────────────


async def _ensure_test_db(url: str) -> None:
    """Create the test database if it does not already exist.

    Connects to the sibling ``shieldher`` DB (same host / credentials) and
    issues ``CREATE DATABASE`` only when the test DB is absent.
    """
    # Strip driver prefix; build raw asyncpg DSN pointing at main DB
    raw = url.replace("postgresql+asyncpg://", "postgresql://")
    db_name = raw.rsplit("/", 1)[-1]
    admin_dsn = raw.rsplit("/", 1)[0] + "/shieldher"

    conn: asyncpg.Connection = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if not exists:
            # CREATE DATABASE cannot run inside a transaction
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            logger.info("Created test database '%s'", db_name)
    finally:
        await conn.close()


# ── Session-scoped engine ─────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create (or re-use) the test DB and build fresh tables for this run."""
    await _ensure_test_db(TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)

    async with engine.begin() as conn:
        # Always start from a known-clean schema
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


# ── Per-test table wipe ───────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _clear_tables(test_engine) -> AsyncGenerator[None, None]:
    """Truncate every table *before* each test so tests never share state."""
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield


# ── Function-scoped DB session ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Raw AsyncSession for service-level unit tests.

    Commits are honoured so that data written here is visible to a subsequent
    ``client`` fixture request within the same test.  The autouse
    ``_clear_tables`` fixture ensures clean state for the next test.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


# ── Function-scoped fake Redis ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def fake_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Isolated in-process FakeRedis — no real Redis required for tests."""
    redis: fakeredis.aioredis.FakeRedis = fakeredis.aioredis.FakeRedis(
        decode_responses=True
    )
    yield redis
    await redis.flushall()
    await redis.aclose()


# ── HTTP test client ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(
    test_engine, fake_redis
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient pointed at the FastAPI app with test-double dependencies.

    The ``get_db`` override uses the test engine (not the app's production
    engine), and ``get_redis`` returns the per-test FakeRedis instance.

    The app lifespan still runs (and connects to real Redis for its ping), but
    all request-handling code goes through the overridden dependencies.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_redis() -> fakeredis.aioredis.FakeRedis:
        return fake_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Reusable factory helpers ──────────────────────────────────────────────────


async def make_person(
    db: AsyncSession,
    *,
    phone: str = "+491700000001",
    name: str = "Test Person",
    emergency_contact_phone: str | None = "+491700000099",
) -> User:
    """Insert a Person user and commit."""
    user = User(
        id=uuid4(),
        phone=phone,
        name=name,
        role=UserRole.person,
        firebase_uid=f"test-uid-{phone}",
        emergency_contact_name="EC Name",
        emergency_contact_phone=emergency_contact_phone,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def make_shield(
    db: AsyncSession,
    redis: Any,
    *,
    phone: str,
    lat: float,
    lng: float,
    name: str | None = None,
    status: ShieldStatus = ShieldStatus.active,
    id_verified: bool = True,
) -> tuple[User, Shield]:
    """Insert a Shield user + Shield profile, write location to Redis, commit."""
    from app.services.location_service import update_shield_location

    user = User(
        id=uuid4(),
        phone=phone,
        name=name or f"Shield {phone[-3:]}",
        role=UserRole.shield,
        firebase_uid=f"test-uid-{phone}",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    shield = Shield(
        id=uuid4(),
        user_id=user.id,
        status=status,
        id_verified=id_verified,
        commitment_signed=True,
        current_lat=lat,
        current_lng=lng,
        location_updated_at=datetime.now(timezone.utc),
    )
    db.add(shield)
    await db.commit()

    await update_shield_location(str(shield.id), lat, lng, redis=redis)
    return user, shield


def auth_headers(user: User) -> dict[str, str]:
    """Return a Bearer Authorization header for the given user."""
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}
