"""Geospatial utility functions — pure Python, no PostGIS dependency."""

import math


EARTH_RADIUS_KM = 6371.0


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in kilometres between two coordinates."""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def is_within_radius(
    origin_lat: float,
    origin_lng: float,
    target_lat: float,
    target_lng: float,
    radius_km: float,
) -> bool:
    """Return True if target is within radius_km of origin."""
    return haversine_distance(origin_lat, origin_lng, target_lat, target_lng) <= radius_km


def encode_geohash(lat: float, lng: float, precision: int = 7) -> str:
    """Encode lat/lng to a geohash string of the given precision (default 7 ≈ 150m)."""
    BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_range = (-90.0, 90.0)
    lng_range = (-180.0, 180.0)
    bits = [16, 8, 4, 2, 1]
    bit_idx = 0
    geohash = []
    even = True
    char_bits = 0

    while len(geohash) < precision:
        if even:
            mid = (lng_range[0] + lng_range[1]) / 2
            if lng >= mid:
                char_bits |= bits[bit_idx]
                lng_range = (mid, lng_range[1])
            else:
                lng_range = (lng_range[0], mid)
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                char_bits |= bits[bit_idx]
                lat_range = (mid, lat_range[1])
            else:
                lat_range = (lat_range[0], mid)

        even = not even
        bit_idx += 1
        if bit_idx == 5:
            geohash.append(BASE32[char_bits])
            bit_idx = 0
            char_bits = 0

    return "".join(geohash)


def decode_geohash(geohash: str) -> tuple[float, float, float, float]:
    """Decode a geohash string to its bounding box ``(min_lat, max_lat, min_lng, max_lng)``."""
    BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_range = (-90.0, 90.0)
    lng_range = (-180.0, 180.0)
    even = True

    for char in geohash:
        val = BASE32.index(char)
        for bit in (16, 8, 4, 2, 1):
            if even:
                mid = (lng_range[0] + lng_range[1]) / 2
                if val & bit:
                    lng_range = (mid, lng_range[1])
                else:
                    lng_range = (lng_range[0], mid)
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if val & bit:
                    lat_range = (mid, lat_range[1])
                else:
                    lat_range = (lat_range[0], mid)
            even = not even

    return lat_range[0], lat_range[1], lng_range[0], lng_range[1]


def geohash_neighbors(geohash: str) -> list[str]:
    """Return the 8 neighbouring geohash cells (N, NE, E, SE, S, SW, W, NW).

    Uses the bounding-box decode/offset/re-encode approach so it works with the
    existing pure-Python ``encode_geohash`` without any lookup tables.  Duplicate
    cells near the poles are silently de-duplicated.
    """
    min_lat, max_lat, min_lng, max_lng = decode_geohash(geohash)
    precision = len(geohash)
    lat_step = max_lat - min_lat
    lng_step = max_lng - min_lng
    center_lat = (min_lat + max_lat) / 2
    center_lng = (min_lng + max_lng) / 2

    offsets = (
        (lat_step, 0),           # N
        (lat_step, lng_step),    # NE
        (0, lng_step),           # E
        (-lat_step, lng_step),   # SE
        (-lat_step, 0),          # S
        (-lat_step, -lng_step),  # SW
        (0, -lng_step),          # W
        (lat_step, -lng_step),   # NW
    )

    seen: set[str] = set()
    neighbors: list[str] = []
    for dlat, dlng in offsets:
        nlat = max(-90.0, min(90.0, center_lat + dlat))
        nlng = max(-180.0, min(180.0, center_lng + dlng))
        cell = encode_geohash(nlat, nlng, precision)
        if cell not in seen:
            seen.add(cell)
            neighbors.append(cell)

    return neighbors


def midpoint(lat1: float, lng1: float, lat2: float, lng2: float) -> tuple[float, float]:
    """Return the geographic midpoint between two coordinates."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlng_r = math.radians(lng2 - lng1)

    bx = math.cos(lat2_r) * math.cos(dlng_r)
    by = math.cos(lat2_r) * math.sin(dlng_r)

    mid_lat = math.degrees(
        math.atan2(
            math.sin(lat1_r) + math.sin(lat2_r),
            math.sqrt((math.cos(lat1_r) + bx) ** 2 + by**2),
        )
    )
    mid_lng = lng1 + math.degrees(math.atan2(by, math.cos(lat1_r) + bx))
    return mid_lat, mid_lng
