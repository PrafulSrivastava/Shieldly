"""Development-only endpoints — mounted only when APP_ENV=development.

This router is mounted ONLY when APP_ENV=development.  Never expose in
production — the endpoints bypass auth and exist purely for local verification.
"""

import logging
import random
from datetime import datetime, timezone
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.hotspot_data import HotspotData
from app.models.incident_responses import IncidentResponse
from app.models.incidents import Incident
from app.models.shields import Shield, ShieldStatus
from app.models.users import User, UserRole
from app.redis_client import get_redis
from app.schemas.incidents import RespondToIncidentResponse, TriggerSOSResponse
from app.services import incident_service
from app.services.hotspot_service import log_incident_to_hotspot
from app.services.location_service import update_shield_location
from app.services.sms_service import send_emergency_contact_sos
from app.utils.geo import encode_geohash

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Heilbronn seed constants ───────────────────────────────────────────────────
_CENTRE_LAT = 49.1427
_CENTRE_LNG = 9.2109

_PERSON_PHONE = "+491700000001"
_SHIELD_PHONES = [
    "+491700000002",
    "+491700000003",
    "+491700000004",
    "+491700000005",
    "+491700000006",
]

# At lat 49°: 1° lat ≈ 111 km, 1° lng ≈ 72.8 km
# Offsets produce spread of 500 m – 1 500 m from centre
_SHIELD_OFFSETS: list[tuple[float, float]] = [
    (+0.0045, +0.0085),  # ~720 m NE
    (-0.0060, -0.0090),  # ~820 m SW
    (+0.0090, -0.0070),  # ~1 060 m NW
    (-0.0050, +0.0145),  # ~1 210 m E-SE
    (+0.0135, +0.0105),  # ~1 520 m NNE
]

# ── Shared response schemas ────────────────────────────────────────────────────


class SeedUserInfo(BaseModel):
    user_id: UUID
    phone: str
    name: str
    role: str


class SeedShieldInfo(BaseModel):
    user_id: UUID
    shield_id: UUID
    phone: str
    name: str
    lat: float
    lng: float


class SeedResponse(BaseModel):
    seeded: bool
    users: list[SeedUserInfo]
    shields: list[SeedShieldInfo]


class MockShieldRespondResponse(BaseModel):
    incident_id: UUID
    shield_id: UUID
    convergence_point: dict[str, float] | None
    shield_moved_to: dict[str, float]


class TestSMSRequest(BaseModel):
    to: str = Field(..., description="Phone number in E.164 format, e.g. +447911123456")
    person_name: str = Field(default="Test User", description="Name shown in the SMS body")
    lat: float = Field(default=_CENTRE_LAT, description="Latitude for the Google Maps link")
    lng: float = Field(default=_CENTRE_LNG, description="Longitude for the Google Maps link")


class TestSMSResponse(BaseModel):
    queued: bool
    to: str
    mock_mode: bool


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _delete_seed_data(db: AsyncSession) -> None:
    """Remove all rows that belong to the standard seed phones."""
    all_phones = [_PERSON_PHONE, *_SHIELD_PHONES]
    existing = (
        await db.execute(select(User).where(User.phone.in_(all_phones)))
    ).scalars().all()

    if not existing:
        return

    user_ids = [u.id for u in existing]

    # Find incidents triggered by seed users
    incidents = (
        await db.execute(
            select(Incident).where(Incident.triggered_by.in_(user_ids))
        )
    ).scalars().all()
    incident_ids = [i.id for i in incidents]

    if incident_ids:
        await db.execute(
            delete(IncidentResponse).where(
                IncidentResponse.incident_id.in_(incident_ids)
            )
        )
        await db.execute(
            delete(Incident).where(Incident.id.in_(incident_ids))
        )

    await db.execute(delete(Shield).where(Shield.user_id.in_(user_ids)))
    await db.execute(delete(User).where(User.id.in_(user_ids)))

    # Wipe hotspot bucket for the Heilbronn geohash cell
    seed_geohash = encode_geohash(_CENTRE_LAT, _CENTRE_LNG, precision=6)
    await db.execute(
        delete(HotspotData).where(HotspotData.geohash == seed_geohash)
    )

    await db.flush()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/dev/seed",
    response_model=SeedResponse,
    summary="Wipe and re-seed the local DB",
    description=(
        "Removes all existing seed rows and recreates 1 test Person + 5 test Shields "
        "spread 500 m–1 500 m around Heilbronn centre, plus 3 historical hotspot entries. "
        "**Development only.**"
    ),
)
async def seed_database(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SeedResponse:
    await _delete_seed_data(db)

    now = datetime.now(timezone.utc)

    # ── Test Person ───────────────────────────────────────────────────────────
    person = User(
        id=uuid4(),
        phone=_PERSON_PHONE,
        name="Test Person",
        role=UserRole.person,
        firebase_uid=f"mock-uid-{_PERSON_PHONE}",
        emergency_contact_name="Emergency Contact",
        emergency_contact_phone="+491700000099",
        is_active=True,
    )
    db.add(person)
    await db.flush()

    seed_users: list[SeedUserInfo] = [
        SeedUserInfo(
            user_id=person.id,
            phone=person.phone,
            name=person.name,
            role=person.role.value,
        )
    ]
    seed_shields: list[SeedShieldInfo] = []

    # ── 5 test Shields ────────────────────────────────────────────────────────
    for idx, phone in enumerate(_SHIELD_PHONES):
        lat_off, lng_off = _SHIELD_OFFSETS[idx]
        shield_lat = round(_CENTRE_LAT + lat_off, 6)
        shield_lng = round(_CENTRE_LNG + lng_off, 6)
        name = f"Test Shield {idx + 1}"

        user = User(
            id=uuid4(),
            phone=phone,
            name=name,
            role=UserRole.shield,
            firebase_uid=f"mock-uid-{phone}",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        shield = Shield(
            id=uuid4(),
            user_id=user.id,
            status=ShieldStatus.active,
            id_verified=True,
            commitment_signed=True,
            current_lat=shield_lat,
            current_lng=shield_lng,
            location_updated_at=now,
        )
        db.add(shield)
        await db.flush()

        # Write location to Redis so trigger-test-sos finds them immediately
        await update_shield_location(str(shield.id), shield_lat, shield_lng, redis=redis)

        seed_users.append(
            SeedUserInfo(
                user_id=user.id,
                phone=user.phone,
                name=user.name,
                role=user.role.value,
            )
        )
        seed_shields.append(
            SeedShieldInfo(
                user_id=user.id,
                shield_id=shield.id,
                phone=user.phone,
                name=user.name,
                lat=shield_lat,
                lng=shield_lng,
            )
        )

    # ── 3 past hotspot incidents (for Gemini context demo) ────────────────────
    past_incidents: list[tuple[float, float, datetime]] = [
        (
            _CENTRE_LAT + random.uniform(-0.001, 0.001),
            _CENTRE_LNG + random.uniform(-0.001, 0.001),
            datetime(2025, 11, 15, 22, 30, tzinfo=timezone.utc),
        ),
        (
            _CENTRE_LAT + random.uniform(-0.001, 0.001),
            _CENTRE_LNG + random.uniform(-0.001, 0.001),
            datetime(2025, 12, 3, 23, 15, tzinfo=timezone.utc),
        ),
        (
            _CENTRE_LAT + random.uniform(-0.001, 0.001),
            _CENTRE_LNG + random.uniform(-0.001, 0.001),
            datetime(2026, 1, 7, 21, 0, tzinfo=timezone.utc),
        ),
    ]
    for lat, lng, ts in past_incidents:
        await log_incident_to_hotspot(lat, lng, ts, db=db)

    logger.info(
        "Dev seed complete: 1 person, %d shields, 3 hotspot entries", len(_SHIELD_PHONES)
    )
    return SeedResponse(seeded=True, users=seed_users, shields=seed_shields)


@router.post(
    "/dev/trigger-test-sos",
    response_model=TriggerSOSResponse,
    summary="Trigger a fake SOS from the seeded test Person",
    description=(
        "Fires an SOS from the test Person at Heilbronn centre. Refreshes shield "
        "location timestamps first so stale-location checks pass even if seed ran "
        "> 5 min ago. Uses mock SMS — no real side effects. **Development only.**"
    ),
)
async def trigger_test_sos(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TriggerSOSResponse:
    result = await db.execute(select(User).where(User.phone == _PERSON_PHONE))
    person: User | None = result.scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Test Person not found — run POST /api/v1/dev/seed first",
        )

    # Refresh shield location timestamps so the stale-location filter passes
    shields = (
        await db.execute(
            select(Shield)
            .join(User, Shield.user_id == User.id)
            .where(
                User.phone.in_(_SHIELD_PHONES),
                Shield.status == ShieldStatus.active,
                Shield.id_verified.is_(True),
            )
        )
    ).scalars().all()

    fresh_now = datetime.now(timezone.utc)
    for shield in shields:
        if shield.current_lat is not None and shield.current_lng is not None:
            await db.execute(
                update(Shield)
                .where(Shield.id == shield.id)
                .values(location_updated_at=fresh_now)
            )
            await update_shield_location(
                str(shield.id), shield.current_lat, shield.current_lng, redis=redis
            )

    await db.flush()

    return await incident_service.trigger_sos(
        person,
        _CENTRE_LAT,
        _CENTRE_LNG,
        db=db,
        redis=redis,
        background_tasks=background_tasks,
    )


@router.post(
    "/dev/mock-shield-respond/{incident_id}/{shield_id}",
    response_model=MockShieldRespondResponse,
    summary="Simulate a Shield responding to an incident",
    description=(
        "Marks the given Shield as responding to the incident and moves its "
        "location 30 % of the way toward the convergence point to simulate "
        "approach. **Development only.**"
    ),
)
async def mock_shield_respond(
    incident_id: UUID,
    shield_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> MockShieldRespondResponse:
    result = await db.execute(select(Shield).where(Shield.id == shield_id))
    shield: Shield | None = result.scalar_one_or_none()
    if shield is None:
        raise HTTPException(status_code=404, detail="Shield not found")

    response: RespondToIncidentResponse | None = await incident_service.update_response_status(
        shield,
        incident_id,
        "responding",
        db=db,
        redis=redis,
    )

    conv_point: dict[str, float] | None = None
    moved_to: dict[str, float] = {}

    if response is not None and response.convergence_point is not None:
        conv_lat = response.convergence_point.lat
        conv_lng = response.convergence_point.lng
        conv_point = {"lat": conv_lat, "lng": conv_lng}

        origin_lat = shield.current_lat or _CENTRE_LAT
        origin_lng = shield.current_lng or _CENTRE_LNG

        # Move 30 % of the way toward convergence
        moved_lat = round(origin_lat + 0.30 * (conv_lat - origin_lat), 6)
        moved_lng = round(origin_lng + 0.30 * (conv_lng - origin_lng), 6)

        await db.execute(
            update(Shield)
            .where(Shield.id == shield_id)
            .values(
                current_lat=moved_lat,
                current_lng=moved_lng,
                location_updated_at=datetime.now(timezone.utc),
            )
        )
        await update_shield_location(str(shield_id), moved_lat, moved_lng, redis=redis)
        moved_to = {"lat": moved_lat, "lng": moved_lng}
    elif shield.current_lat is not None and shield.current_lng is not None:
        moved_to = {"lat": shield.current_lat, "lng": shield.current_lng}

    return MockShieldRespondResponse(
        incident_id=incident_id,
        shield_id=shield_id,
        convergence_point=conv_point,
        shield_moved_to=moved_to,
    )


@router.post(
    "/dev/test/sms",
    response_model=TestSMSResponse,
    summary="Send a test SOS SMS",
    description=(
        "Fires a test SOS SMS through the SMS pipeline (real Twilio call or mock "
        "depending on MOCK_SMS). Useful for verifying Twilio credentials locally "
        "without triggering a real incident. **Development only.**"
    ),
)
async def send_test_sms(
    body: TestSMSRequest,
    background_tasks: BackgroundTasks,
) -> TestSMSResponse:
    background_tasks.add_task(
        send_emergency_contact_sos,
        incident_id="test-00000000-0000-0000-0000-000000000000",
        person_name=body.person_name,
        contact_phone=body.to,
        lat=body.lat,
        lng=body.lng,
    )
    return TestSMSResponse(
        queued=True,
        to=body.to,
        mock_mode=settings.mock_sms,
    )
