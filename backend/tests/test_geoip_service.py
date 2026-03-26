"""Unit tests for the GeoIP service: haversine distance and impossible travel."""

from __future__ import annotations

import pytest

from app.services.geoip_service import haversine_km, is_impossible_travel


class TestHaversineKm:
    def test_same_location_is_zero(self):
        assert haversine_km(51.5074, -0.1278, 51.5074, -0.1278) == pytest.approx(0, abs=0.01)

    def test_london_to_paris(self):
        # Approximate distance London to Paris: ~340 km
        dist = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        assert 330 < dist < 360

    def test_new_york_to_london(self):
        # ~5570 km
        dist = haversine_km(40.7128, -74.0060, 51.5074, -0.1278)
        assert 5400 < dist < 5700

    def test_antipodal_points(self):
        # Maximum possible distance on Earth ≈ 20015 km
        dist = haversine_km(0, 0, 0, 180)
        assert dist == pytest.approx(20015, rel=0.01)


class TestIsImpossibleTravel:
    def test_same_location_not_impossible(self):
        # Same city, 1 hour apart -> no impossible travel
        result = is_impossible_travel(
            51.5074,
            -0.1278,
            51.5074,
            -0.1278,
            time_delta_seconds=3600,
        )
        assert result is False

    def test_london_to_new_york_in_1_hour_is_impossible(self):
        # ~5560 km in 3600s = ~1544 km/h (faster than commercial aircraft)
        result = is_impossible_travel(
            51.5074,
            -0.1278,
            40.7128,
            -74.0060,
            time_delta_seconds=3600,
        )
        assert result is True

    def test_london_to_paris_in_8_hours_is_not_impossible(self):
        # ~340 km in 28800s = ~42 km/h
        result = is_impossible_travel(
            51.5074,
            -0.1278,
            48.8566,
            2.3522,
            time_delta_seconds=28800,
        )
        assert result is False

    def test_distance_below_threshold_not_impossible(self):
        # Same country, short distance, short time
        result = is_impossible_travel(
            51.5074,
            -0.1278,
            51.4545,
            -2.5872,
            time_delta_seconds=600,
            distance_threshold_km=500,
        )
        assert result is False

    def test_zero_time_delta_handled_safely(self):
        # Should not raise, treat as extremely fast
        result = is_impossible_travel(
            51.5074,
            -0.1278,
            40.7128,
            -74.0060,
            time_delta_seconds=0,
        )
        # Any non-zero distance with 0 time -> impossible
        assert result is True

    def test_custom_thresholds(self):
        # Distance ~7 km between two London-area points, distance_threshold=5 km.
        # At time_delta_seconds=20, implied speed = 7 / (20/3600) ≈ 1260 km/h > 900 → impossible.
        result = is_impossible_travel(
            51.5074,
            -0.1278,
            51.45,
            -0.13,
            time_delta_seconds=20,
            distance_threshold_km=5,
            speed_threshold_kmh=900,
        )
        assert result is True
