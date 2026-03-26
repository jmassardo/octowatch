"""GeoIP service using MaxMind GeoLite2 database.

Loaded once per process at startup into shared memory. Each ingestion worker
loads its own instance, which is acceptable given the 95 MB mmdb file size.
"""

from __future__ import annotations

import ipaddress
import os
from math import atan2, cos, radians, sin, sqrt
from typing import NamedTuple

import geoip2.database
import geoip2.errors
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class GeoLocation(NamedTuple):
    country_code: str | None
    city: str | None
    latitude: float | None
    longitude: float | None
    is_proxy: bool | None


_reader: geoip2.database.Reader | None = None


async def load_geoip_db() -> None:
    """Load the MaxMind GeoLite2 City database into process memory."""
    global _reader
    db_path = settings.GEOIP.GEOIP_DB_PATH
    if not os.path.exists(db_path):
        logger.warning(
            "geoip.db_not_found",
            path=db_path,
            message="GeoIP enrichment disabled — mmdb file not found",
        )
        return
    try:
        _reader = geoip2.database.Reader(db_path)
        logger.info("geoip.loaded", path=db_path)
    except Exception as exc:
        logger.error("geoip.load_failed", path=db_path, error=str(exc))
        _reader = None


def get_geoip_location(ip_str: str) -> GeoLocation:
    """Resolve IP address to geo location. Returns empty GeoLocation on error."""
    if _reader is None:
        return GeoLocation(None, None, None, None, None)

    try:
        # Validate IP address to prevent any injection
        ipaddress.ip_address(ip_str)
    except ValueError:
        return GeoLocation(None, None, None, None, None)

    try:
        record = _reader.city(ip_str)
        return GeoLocation(
            country_code=record.country.iso_code,
            city=record.city.name,
            latitude=record.location.latitude,
            longitude=record.location.longitude,
            is_proxy=getattr(record, "traits", None) is not None
            and getattr(record.traits, "is_anonymous_proxy", False),
        )
    except geoip2.errors.AddressNotFoundError:
        return GeoLocation(None, None, None, None, None)
    except Exception as exc:
        logger.debug("geoip.lookup_error", ip=ip_str, error=str(exc))
        return GeoLocation(None, None, None, None, None)


def is_geoip_available() -> bool:
    """Return True if the GeoIP database is loaded."""
    return _reader is not None


async def close_geoip_db() -> None:
    """Close the database reader."""
    global _reader
    if _reader is not None:
        _reader.close()
        _reader = None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in kilometers between two geo points."""
    R = 6371.0  # Earth radius in km
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)
    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def is_impossible_travel(
    prev_lat: float,
    prev_lon: float,
    current_lat: float,
    current_lon: float,
    time_delta_seconds: float,
    distance_threshold_km: float = 500.0,
    speed_threshold_kmh: float = 900.0,
) -> bool:
    """Return True if travel between two geo locations implies impossible speed."""
    distance = haversine_km(prev_lat, prev_lon, current_lat, current_lon)
    if distance < distance_threshold_km:
        return False

    # Guard: less than 1 second apart
    if time_delta_seconds < 1.0:
        return distance >= distance_threshold_km

    time_delta_hours = time_delta_seconds / 3600.0
    implied_speed = distance / time_delta_hours
    return implied_speed > speed_threshold_kmh
