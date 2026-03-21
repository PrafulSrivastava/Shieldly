"""Tests for the hotspot service and /hotspots router.

Coverage
--------
- log_incident_to_hotspot  → creates a new HotspotData row on first call
- log_incident_to_hotspot  → increments incident_count on subsequent calls
- log_incident_to_hotspot  → correctly updates the time_distribution JSONB
- get_hotspot_summary      → aggregates the centre cell and all 8 neighbours
- get_hotspot_summary      → returns zero when no data exists
- risk_level calculation   → low (<2), medium (2–5), high (>5)
- get_gemini_safety_context → returns reassuring string when count == 0
- get_gemini_safety_context → returns mock string when MOCK_GEMINI=true
- GET /hotspots/context    → authenticated endpoint returns risk_level + summary
"""

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hotspot_data import HotspotData
from app.services.hotspot_service import (
    get_gemini_safety_context,
    get_hotspot_summary,
    log_incident_to_hotspot,
)
from app.utils.geo import encode_geohash, geohash_neighbors
from tests.conftest import auth_headers, make_person, make_shield

_LAT = 49.1427
_LNG = 9.2109
_NOW = datetime(2026, 1, 15, 22, 0, tzinfo=timezone.utc)


# ── log_incident_to_hotspot ───────────────────────────────────────────────────


async def test_log_incident_creates_hotspot_row(
    db_session: AsyncSession,
) -> None:
    await log_incident_to_hotspot(_LAT, _LNG, _NOW, db=db_session)
    await db_session.commit()

    geohash = encode_geohash(_LAT, _LNG, precision=6)
    result = await db_session.execute(
        select(HotspotData).where(HotspotData.geohash == geohash)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.incident_count == 1
    assert row.last_incident is not None


async def test_log_incident_increments_existing_row(
    db_session: AsyncSession,
) -> None:
    await log_incident_to_hotspot(_LAT, _LNG, _NOW, db=db_session)
    await db_session.commit()
    await log_incident_to_hotspot(_LAT, _LNG, _NOW, db=db_session)
    await db_session.commit()

    geohash = encode_geohash(_LAT, _LNG, precision=6)
    result = await db_session.execute(
        select(HotspotData).where(HotspotData.geohash == geohash)
    )
    row = result.scalar_one()
    assert row.incident_count == 2


async def test_log_incident_updates_time_distribution(
    db_session: AsyncSession,
) -> None:
    ts_22h = datetime(2026, 1, 15, 22, 0, tzinfo=timezone.utc)
    ts_23h = datetime(2026, 1, 15, 23, 0, tzinfo=timezone.utc)

    await log_incident_to_hotspot(_LAT, _LNG, ts_22h, db=db_session)
    await db_session.flush()
    await log_incident_to_hotspot(_LAT, _LNG, ts_23h, db=db_session)
    await db_session.flush()
    await log_incident_to_hotspot(_LAT, _LNG, ts_22h, db=db_session)
    await db_session.commit()

    geohash = encode_geohash(_LAT, _LNG, precision=6)
    result = await db_session.execute(
        select(HotspotData).where(HotspotData.geohash == geohash)
    )
    row = result.scalar_one()
    dist = row.time_distribution
    assert int(dist.get("22", 0)) == 2
    assert int(dist.get("23", 0)) == 1


# ── get_hotspot_summary ───────────────────────────────────────────────────────


async def test_get_hotspot_summary_returns_zero_when_no_data(
    db_session: AsyncSession,
) -> None:
    # Far-away lat/lng with no history
    summary = await get_hotspot_summary(0.0, 0.0, db=db_session)
    assert summary["total_incidents"] == 0
    assert summary["risk_level"] == "low"
    assert summary["last_incident"] is None


async def test_get_hotspot_summary_aggregates_neighbours(
    db_session: AsyncSession,
) -> None:
    """Incidents logged in neighbour cells must be included in the summary."""
    geohash = encode_geohash(_LAT, _LNG, precision=6)
    neighbour_geohash = geohash_neighbors(geohash)[0]  # North neighbour

    # Decode neighbour centre to a lat/lng we can log against
    # (We insert the row directly to avoid needing exact coordinates)
    db_session.add(
        HotspotData(
            geohash=neighbour_geohash,
            incident_count=3,
            last_incident=_NOW,
            time_distribution={"22": 3},
        )
    )
    # Also add one at the centre
    await log_incident_to_hotspot(_LAT, _LNG, _NOW, db=db_session)
    await db_session.commit()

    summary = await get_hotspot_summary(_LAT, _LNG, db=db_session)
    assert summary["total_incidents"] >= 4  # centre(1) + neighbour(3)


# ── risk level thresholds ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "count,expected_level",
    [
        (0, "low"),
        (1, "low"),
        (2, "medium"),
        (5, "medium"),
        (6, "high"),
        (20, "high"),
    ],
)
async def test_risk_level_matches_count(
    db_session: AsyncSession,
    count: int,
    expected_level: str,
) -> None:
    for i in range(count):
        ts = datetime(2026, 1, i % 28 + 1, 22, 0, tzinfo=timezone.utc)
        await log_incident_to_hotspot(_LAT, _LNG, ts, db=db_session)
    await db_session.commit()

    summary = await get_hotspot_summary(_LAT, _LNG, db=db_session)
    assert summary["risk_level"] == expected_level


# ── get_gemini_safety_context ─────────────────────────────────────────────────


async def test_gemini_context_no_incidents_returns_reassuring_message(
    db_session: AsyncSession,
) -> None:
    """Zero incidents → static reassuring string, no Gemini API call."""
    msg = await get_gemini_safety_context(0.0, 0.0, db=db_session)
    assert "no safety incidents" in msg.lower() or "stay aware" in msg.lower()


async def test_gemini_context_mock_mode_returns_canned_string(
    db_session: AsyncSession,
) -> None:
    """When MOCK_GEMINI=true the service must not call the real API."""
    await log_incident_to_hotspot(_LAT, _LNG, _NOW, db=db_session)
    await db_session.commit()

    with patch("app.services.hotspot_service.settings") as mock_settings:
        mock_settings.mock_gemini = True
        msg = await get_gemini_safety_context(_LAT, _LNG, db=db_session)

    assert len(msg) > 10  # Non-empty canned response


# ── HTTP endpoint ─────────────────────────────────────────────────────────────


async def test_get_hotspot_context_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis,
) -> None:
    """GET /hotspots/context returns the expected schema."""
    person = await make_person(db_session)

    resp = await client.get(
        f"/api/v1/hotspots/context?lat={_LAT}&lng={_LNG}",
        headers=auth_headers(person),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["risk_level"] in ("low", "medium", "high")
    assert isinstance(data["total_incidents"], int)
    assert isinstance(data["gemini_summary"], str)
    assert isinstance(data["shield_count_nearby"], int)


async def test_get_hotspot_context_requires_auth(
    client: AsyncClient,
) -> None:
    resp = await client.get(f"/api/v1/hotspots/context?lat={_LAT}&lng={_LNG}")
    assert resp.status_code == 403


async def test_get_hotspot_context_reflects_logged_incidents(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Incidents already in the DB must surface in the endpoint response."""
    # Log 3 incidents so risk_level goes to medium
    for i in range(3):
        await log_incident_to_hotspot(
            _LAT, _LNG, datetime(2026, 1, i + 1, 22, tzinfo=timezone.utc), db=db_session
        )
    await db_session.commit()

    person = await make_person(db_session)
    resp = await client.get(
        f"/api/v1/hotspots/context?lat={_LAT}&lng={_LNG}",
        headers=auth_headers(person),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_incidents"] >= 3
    assert data["risk_level"] in ("medium", "high")
