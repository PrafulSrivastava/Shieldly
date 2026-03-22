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


class SeedHotspotCell(BaseModel):
    geohash: str
    incident_count: int
    time_distribution: dict[str, int]


class SeedHotspotsResponse(BaseModel):
    seeded: bool
    cells: list[SeedHotspotCell]


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
            expo_push_token=f"ExponentPushToken[SEED_SHIELD_{idx:04d}_FAKE_TOKEN]",
            token_updated_at=now,
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
    "/dev/mock-incident-respond/{incident_id}",
    summary="Simulate all notified shields accepting an incident",
    description=(
        "Finds every Shield still in 'notified' status for the incident and "
        "marks each one as 'responding', moving their position 30 % toward the "
        "person's location. **Development only.**"
    ),
)
async def mock_incident_respond(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    # Find all notified responses for this incident
    from app.models.incident_responses import ResponseStatus

    rows = (
        await db.execute(
            select(IncidentResponse, Shield)
            .join(Shield, IncidentResponse.shield_id == Shield.id)
            .where(
                IncidentResponse.incident_id == incident_id,
                IncidentResponse.status == ResponseStatus.notified,
            )
        )
    ).all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No notified shields found for this incident",
        )

    # Cap at nearest 3 shields (rows are already ordered by insertion which
    # mirrors distance order from get_active_shields_near)
    rows = rows[:3]

    responded = 0
    for _inc_resp, shield in rows:
        try:
            await incident_service.update_response_status(
                shield,
                incident_id,
                "responding",
                db=db,
                redis=redis,
            )
            responded += 1
        except Exception as exc:
            logger.warning("mock-incident-respond: shield %s skipped — %s", shield.id, exc)

    return {"incident_id": str(incident_id), "shields_responded": responded}


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


# ── Stuttgart route hotspot seed ───────────────────────────────────────────

_ROUTE_INCIDENTS: list[dict] = [
    {"lat": 48.7092, "lng": 9.1041, "count": 3, "days_ago": 8,  "hours": {21: 1, 22: 1, 23: 1}},
    {"lat": 48.7089, "lng": 9.1048, "count": 4, "days_ago": 14, "hours": {21: 2, 22: 1, 23: 1}},
    {"lat": 48.7085, "lng": 9.1055, "count": 2, "days_ago": 33, "hours": {22: 1, 23: 1}},
    {"lat": 48.7078, "lng": 9.1063, "count": 3, "days_ago": 51, "hours": {21: 1, 22: 2}},
]


@router.post(
    "/dev/seed-hotspots",
    response_model=SeedHotspotsResponse,
    summary="Seed Stuttgart-route hotspot data",
    description=(
        "Idempotent seed: deletes existing rows for the target geohash cells, "
        "then inserts 4 fake historical incidents along a Stuttgart walking route "
        "(48.7092,9.1041 → 48.7078,9.1063). Counts range 2–4, times concentrated "
        "in hours 21–23. **Development only.**"
    ),
)
async def seed_hotspots(
    db: AsyncSession = Depends(get_db),
) -> SeedHotspotsResponse:
    from datetime import timedelta
    from sqlalchemy.orm.attributes import flag_modified

    target_geohashes: set[str] = set()
    for inc in _ROUTE_INCIDENTS:
        target_geohashes.add(encode_geohash(inc["lat"], inc["lng"], precision=6))

    await db.execute(
        delete(HotspotData).where(HotspotData.geohash.in_(list(target_geohashes)))
    )

    now = datetime.now(timezone.utc)
    rows_by_gh: dict[str, HotspotData] = {}

    for inc in _ROUTE_INCIDENTS:
        gh = encode_geohash(inc["lat"], inc["lng"], precision=6)
        last = now - timedelta(days=inc["days_ago"], hours=random.randint(0, 5))

        if gh in rows_by_gh:
            row = rows_by_gh[gh]
            row.incident_count += inc["count"]
            if last > row.last_incident:
                row.last_incident = last
            td: dict[str, int] = dict(row.time_distribution or {})
            for h, c in inc["hours"].items():
                td[str(h)] = td.get(str(h), 0) + c
            row.time_distribution = td
            flag_modified(row, "time_distribution")
        else:
            rows_by_gh[gh] = HotspotData(
                geohash=gh,
                incident_count=inc["count"],
                last_incident=last,
                time_distribution={str(h): c for h, c in inc["hours"].items()},
            )

    for row in rows_by_gh.values():
        db.add(row)

    await db.flush()

    cells = [
        SeedHotspotCell(
            geohash=gh,
            incident_count=row.incident_count,
            time_distribution=row.time_distribution,
        )
        for gh, row in rows_by_gh.items()
    ]

    logger.info("Seeded %d hotspot cell(s) for Stuttgart route", len(cells))
    return SeedHotspotsResponse(seeded=True, cells=cells)


# ── Large-scale seed (1 000 users / 400 shields) ──────────────────────────────

_LARGE_SEED_PERSON_PREFIX = "+4915100"
_LARGE_SEED_SHIELD_PREFIX = "+4915200"

_FIRST_NAMES = [
    "Lena", "Sophie", "Anna", "Laura", "Julia", "Maria", "Sarah", "Lisa",
    "Emma", "Lea", "Hannah", "Mia", "Katharina", "Franziska", "Clara",
    "Nina", "Jana", "Sabine", "Petra", "Monika", "Claudia", "Stefanie",
    "Sandra", "Andrea", "Melanie", "Nadine", "Anja", "Tanja", "Karin",
    "Birgit", "Heike", "Ursula", "Gabi", "Ingrid", "Renate", "Martina",
    "Simone", "Sonja", "Silke", "Corinna", "Carla", "Miriam", "Johanna",
    "Luisa", "Alina", "Vanessa", "Jessica", "Carina", "Isabell", "Verena",
]

_LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter",
    "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann",
    "Braun", "Krüger", "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner",
    "Schmitz", "Krause", "Meier", "Lehmann", "Schmid", "Schulze", "Maier",
    "Köhler", "Herrmann", "König", "Walter", "Mayer", "Huber", "Kaiser",
    "Fuchs", "Peters", "Lang", "Scholz", "Möller", "Weiß", "Jung",
    "Hahn", "Schubert",
]

# Real neighbourhood anchor points for Heilbronn and Stuttgart
_HEILBRONN_AREAS: list[tuple[float, float, str]] = [
    (49.1427, 9.2109, "Heilbronn Centre"),
    (49.1380, 9.1780, "Böckingen"),
    (49.1650, 9.2150, "Neckargartach"),
    (49.1200, 9.2250, "Sontheim"),
    (49.1850, 9.1950, "Kirchhausen"),
    (49.1600, 9.1700, "Frankenbach"),
    (49.1200, 9.1750, "Horkheim"),
    (49.1050, 9.1900, "Flein"),
    (49.1750, 9.2400, "Klingenberg"),
    (49.1050, 9.2050, "Biberach"),
]

_STUTTGART_AREAS: list[tuple[float, float, str]] = [
    (48.7758, 9.1829, "Stuttgart Mitte"),
    (48.7950, 9.1800, "Stuttgart Nord"),
    (48.7600, 9.1700, "Stuttgart Süd"),
    (48.7700, 9.2100, "Stuttgart Ost"),
    (48.7700, 9.1500, "Stuttgart West"),
    (48.8000, 9.2300, "Bad Cannstatt"),
    (48.8300, 9.1800, "Zuffenhausen"),
    (48.8100, 9.1600, "Feuerbach"),
    (48.7350, 9.1200, "Vaihingen"),
    (48.7400, 9.1900, "Degerloch"),
    (48.7200, 9.1600, "Möhringen"),
    (48.7800, 9.2500, "Untertürkheim"),
    (48.7800, 9.2300, "Wangen"),
    (48.8400, 9.1700, "Stammheim"),
    (48.7050, 9.2100, "Plieningen"),
]

# Weighted pool: 150 Heilbronn slots + 250 Stuttgart slots = 400 total
_SHIELD_AREA_POOL: list[tuple[float, float, str]] = (
    _HEILBRONN_AREAS * 15   # 10 areas × 15 = 150
    + _STUTTGART_AREAS * 17  # 15 areas × 17 = 255 (trimmed to 250 in code)
)

# Hotspot anchor incidents for both cities (seeded alongside users)
_LARGE_SEED_HOTSPOTS: list[dict] = [
    # Heilbronn late-night clusters
    {"lat": 49.1427, "lng": 9.2109, "days_ago": 5,  "hours": {21: 2, 22: 3, 23: 1}},
    {"lat": 49.1380, "lng": 9.1780, "days_ago": 12, "hours": {22: 2, 23: 3}},
    {"lat": 49.1650, "lng": 9.2150, "days_ago": 20, "hours": {21: 1, 23: 2}},
    {"lat": 49.1200, "lng": 9.2250, "days_ago": 35, "hours": {22: 1, 23: 1}},
    {"lat": 49.1050, "lng": 9.1900, "days_ago": 60, "hours": {21: 1, 22: 1}},
    # Stuttgart late-night clusters
    {"lat": 48.7758, "lng": 9.1829, "days_ago": 3,  "hours": {21: 3, 22: 4, 23: 2}},
    {"lat": 48.7700, "lng": 9.2100, "days_ago": 9,  "hours": {22: 3, 23: 4}},
    {"lat": 48.8000, "lng": 9.2300, "days_ago": 18, "hours": {21: 2, 22: 2, 23: 1}},
    {"lat": 48.7600, "lng": 9.1700, "days_ago": 27, "hours": {21: 1, 22: 2}},
    {"lat": 48.7350, "lng": 9.1200, "days_ago": 45, "hours": {22: 1, 23: 2}},
    {"lat": 48.8300, "lng": 9.1800, "days_ago": 55, "hours": {21: 2, 23: 1}},
    {"lat": 48.7400, "lng": 9.1900, "days_ago": 70, "hours": {22: 2, 23: 1}},
]


class LargeSeedResponse(BaseModel):
    seeded: bool
    persons: int
    shields: int
    active_shields: int
    inactive_shields: int
    pending_shields: int
    hotspot_cells_seeded: int


async def _delete_large_seed_data(db: AsyncSession) -> None:
    """Remove all rows created by a previous seed-large run."""
    person_rows = (
        await db.execute(
            select(User).where(User.phone.like(_LARGE_SEED_PERSON_PREFIX + "%"))
        )
    ).scalars().all()
    shield_rows = (
        await db.execute(
            select(User).where(User.phone.like(_LARGE_SEED_SHIELD_PREFIX + "%"))
        )
    ).scalars().all()

    all_users = person_rows + shield_rows
    if not all_users:
        return

    user_ids = [u.id for u in all_users]

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
        await db.execute(delete(Incident).where(Incident.id.in_(incident_ids)))

    await db.execute(delete(Shield).where(Shield.user_id.in_(user_ids)))
    await db.execute(delete(User).where(User.id.in_(user_ids)))
    await db.flush()


@router.post(
    "/dev/seed-large",
    response_model=LargeSeedResponse,
    summary="Seed 1 000 users + 400 shields across Heilbronn & Stuttgart",
    description=(
        "Idempotent large-scale seed. Deletes previous large-seed rows, then creates: "
        "600 test Persons, 400 Shield volunteers (280 active / 60 inactive / 60 pending) "
        "spread across real neighbourhoods in Heilbronn (150 shields) and Stuttgart "
        "(250 shields), plus hotspot data for both cities. "
        "Active shield locations are written to Redis. **Development only.**"
    ),
)
async def seed_large(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> LargeSeedResponse:
    from datetime import timedelta
    from sqlalchemy.orm.attributes import flag_modified

    rng = random.Random(42)  # fixed seed → deterministic, idempotent names/positions

    await _delete_large_seed_data(db)

    now = datetime.now(timezone.utc)

    # ── 600 Persons ───────────────────────────────────────────────────────────
    n_persons = 600
    for i in range(1, n_persons + 1):
        phone = f"{_LARGE_SEED_PERSON_PREFIX}{i:06d}"
        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        has_ec = rng.random() < 0.80  # 80 % have emergency contact

        user = User(
            id=uuid4(),
            phone=phone,
            name=f"{first} {last}",
            role=UserRole.person,
            firebase_uid=f"mock-uid-{phone}",
            emergency_contact_name=f"{rng.choice(_FIRST_NAMES)} {last}" if has_ec else None,
            emergency_contact_phone=f"+4916{rng.randint(10000000, 99999999)}" if has_ec else None,
            is_active=True,
        )
        db.add(user)

        if i % 50 == 0:
            await db.flush()

    await db.flush()

    # ── 400 Shields ───────────────────────────────────────────────────────────
    # Status breakdown: 0–279 → active, 280–339 → inactive, 340–399 → pending
    n_shields = 400
    n_active = 280
    n_inactive = 60
    # n_pending = 60 (remainder)

    # Build area pool: 150 Heilbronn + 250 Stuttgart
    heilbronn_pool = _HEILBRONN_AREAS * 15          # 150 slots
    stuttgart_pool = (_STUTTGART_AREAS * 17)[:250]  # 255 → trim to 250
    area_pool = heilbronn_pool + stuttgart_pool      # 400 total

    active_shields_written = 0

    for i in range(n_shields):
        phone = f"{_LARGE_SEED_SHIELD_PREFIX}{(i + 1):06d}"
        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)

        if i < n_active:
            status = ShieldStatus.active
            id_verified = True
        elif i < n_active + n_inactive:
            status = ShieldStatus.inactive
            id_verified = True
        else:
            status = ShieldStatus.pending
            id_verified = False

        base_lat, base_lng, _ = area_pool[i]
        jitter_lat = rng.uniform(-0.003, 0.003)
        jitter_lng = rng.uniform(-0.003, 0.003)
        shield_lat = round(base_lat + jitter_lat, 6)
        shield_lng = round(base_lng + jitter_lng, 6)

        # Active hours: 60 % of active/inactive shields get an evening window
        active_start = None
        active_end = None
        if status in (ShieldStatus.active, ShieldStatus.inactive) and rng.random() < 0.60:
            start_h = rng.choice([17, 18, 19, 20])
            end_h = rng.choice([22, 23])
            from datetime import time as dt_time
            active_start = dt_time(start_h, 0)
            active_end = dt_time(end_h, 0)

        user = User(
            id=uuid4(),
            phone=phone,
            name=f"{first} {last}",
            role=UserRole.shield,
            firebase_uid=f"mock-uid-{phone}",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        shield = Shield(
            id=uuid4(),
            user_id=user.id,
            status=status,
            id_verified=id_verified,
            commitment_signed=(status != ShieldStatus.pending),
            current_lat=shield_lat if status != ShieldStatus.pending else None,
            current_lng=shield_lng if status != ShieldStatus.pending else None,
            location_updated_at=now if status != ShieldStatus.pending else None,
            active_hours_start=active_start,
            active_hours_end=active_end,
            expo_push_token=(
                f"ExponentPushToken[LARGE_SEED_{i:04d}_FAKE]"
                if status == ShieldStatus.active
                else None
            ),
            token_updated_at=now if status == ShieldStatus.active else None,
        )
        db.add(shield)

        # Write active shields to Redis so SOS can find them immediately
        if status == ShieldStatus.active:
            await db.flush()
            await update_shield_location(str(shield.id), shield_lat, shield_lng, redis=redis)
            active_shields_written += 1

        if (i + 1) % 50 == 0:
            await db.flush()

    await db.flush()

    # ── Hotspot data for Heilbronn + Stuttgart ─────────────────────────────────
    hotspot_geohashes: set[str] = {
        encode_geohash(h["lat"], h["lng"], precision=6)
        for h in _LARGE_SEED_HOTSPOTS
    }
    await db.execute(
        delete(HotspotData).where(HotspotData.geohash.in_(list(hotspot_geohashes)))
    )

    rows_by_gh: dict[str, HotspotData] = {}
    for h in _LARGE_SEED_HOTSPOTS:
        gh = encode_geohash(h["lat"], h["lng"], precision=6)
        last_ts = now - timedelta(days=h["days_ago"], hours=rng.randint(0, 4))

        if gh in rows_by_gh:
            row = rows_by_gh[gh]
            total = sum(h["hours"].values())
            row.incident_count += total
            if last_ts > row.last_incident:
                row.last_incident = last_ts
            td: dict[str, int] = dict(row.time_distribution or {})
            for hr, cnt in h["hours"].items():
                td[str(hr)] = td.get(str(hr), 0) + cnt
            row.time_distribution = td
            flag_modified(row, "time_distribution")
        else:
            rows_by_gh[gh] = HotspotData(
                geohash=gh,
                incident_count=sum(h["hours"].values()),
                last_incident=last_ts,
                time_distribution={str(hr): cnt for hr, cnt in h["hours"].items()},
            )

    for row in rows_by_gh.values():
        db.add(row)

    await db.flush()

    logger.info(
        "Large seed complete: %d persons, %d shields (%d active), %d hotspot cells",
        n_persons, n_shields, active_shields_written, len(rows_by_gh),
    )

    return LargeSeedResponse(
        seeded=True,
        persons=n_persons,
        shields=n_shields,
        active_shields=n_active,
        inactive_shields=n_inactive,
        pending_shields=n_shields - n_active - n_inactive,
        hotspot_cells_seeded=len(rows_by_gh),
    )
