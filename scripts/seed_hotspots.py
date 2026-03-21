"""Seed hotspot_data with fake historical incidents along a Stuttgart walking route.

Usage:
    python -m scripts.seed_hotspots

Idempotent — deletes existing rows for the target geohash cells before inserting.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.hotspot_data import HotspotData
from app.utils.geo import encode_geohash

_GEOHASH_PRECISION = 6

ROUTE_POINTS: list[tuple[float, float]] = [
    (48.7092, 9.1041),  # start
    (48.7085, 9.1055),  # midpoint
    (48.7078, 9.1063),  # end
]

_INCIDENTS: list[dict] = [
    {
        "lat": 48.7092,
        "lng": 9.1041,
        "count": 3,
        "last_days_ago": 8,
        "hours": {21: 1, 22: 1, 23: 1},
    },
    {
        "lat": 48.7089,
        "lng": 9.1048,
        "count": 4,
        "last_days_ago": 14,
        "hours": {21: 2, 22: 1, 23: 1},
    },
    {
        "lat": 48.7085,
        "lng": 9.1055,
        "count": 2,
        "last_days_ago": 33,
        "hours": {22: 1, 23: 1},
    },
    {
        "lat": 48.7078,
        "lng": 9.1063,
        "count": 3,
        "last_days_ago": 51,
        "hours": {21: 1, 22: 2},
    },
]


async def _seed(db: AsyncSession) -> None:
    target_geohashes: set[str] = set()
    for point in ROUTE_POINTS:
        target_geohashes.add(encode_geohash(point[0], point[1], precision=_GEOHASH_PRECISION))
    for inc in _INCIDENTS:
        target_geohashes.add(encode_geohash(inc["lat"], inc["lng"], precision=_GEOHASH_PRECISION))

    await db.execute(
        delete(HotspotData).where(HotspotData.geohash.in_(list(target_geohashes)))
    )

    now = datetime.now(timezone.utc)
    rows_by_geohash: dict[str, HotspotData] = {}

    for inc in _INCIDENTS:
        gh = encode_geohash(inc["lat"], inc["lng"], precision=_GEOHASH_PRECISION)
        last_incident = now - timedelta(days=inc["last_days_ago"], hours=random.randint(0, 5))

        if gh in rows_by_geohash:
            existing = rows_by_geohash[gh]
            existing.incident_count += inc["count"]
            if last_incident > existing.last_incident:
                existing.last_incident = last_incident
            for h, c in inc["hours"].items():
                key = str(h)
                existing.time_distribution[key] = existing.time_distribution.get(key, 0) + c
        else:
            rows_by_geohash[gh] = HotspotData(
                geohash=gh,
                incident_count=inc["count"],
                last_incident=last_incident,
                time_distribution={str(h): c for h, c in inc["hours"].items()},
            )

    for row in rows_by_geohash.values():
        db.add(row)

    await db.commit()
    print(f"Seeded {len(rows_by_geohash)} hotspot cell(s):")
    for gh, row in rows_by_geohash.items():
        print(f"  {gh}  incidents={row.incident_count}  hours={row.time_distribution}")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await _seed(db)


if __name__ == "__main__":
    asyncio.run(main())
