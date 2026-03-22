import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.redis_client import close_redis, init_redis
from app.routers import admin, auth, hotspots, incidents, location, safecall, shields, tracking
from app.routers import dev as dev_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting ShieldHer API (env=%s)", settings.app_env)

    await init_redis(settings.redis_url)

    yield  # ── application is running ──

    logger.info("Shutting down ShieldHer API")
    await close_redis()
    await engine.dispose()
    logger.info("Connections closed")


# ── App factory ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ShieldHer API",
    description="Real-time women's safety broadcast network",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


# ── Domain routers ─────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(location.router, prefix="/api/v1/location", tags=["location"])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])
app.include_router(hotspots.router, prefix="/api/v1/hotspots", tags=["hotspots"])
app.include_router(shields.router, prefix="/api/v1/shields", tags=["shields"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(tracking.router, prefix="/api/v1/track", tags=["tracking"])
app.include_router(safecall.router, prefix="/api/v1/safecall", tags=["safecall"])

if settings.is_development:
    app.include_router(dev_router.router, prefix="/api/v1", tags=["dev"])
