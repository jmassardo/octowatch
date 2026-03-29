"""Unit tests for org_config Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.org_config import OrgConfigResponse, OrgConfigUpdate


class TestOrgConfigResponse:
    """Tests for the OrgConfigResponse schema."""

    def test_default_cost_per_seat(self) -> None:
        resp = OrgConfigResponse(org_slug="my-org")
        assert resp.copilot_cost_per_seat == 19.0

    def test_custom_cost_per_seat(self) -> None:
        resp = OrgConfigResponse(org_slug="my-org", copilot_cost_per_seat=39.0)
        assert resp.copilot_cost_per_seat == 39.0

    def test_org_slug_required(self) -> None:
        with pytest.raises(ValidationError):
            OrgConfigResponse()  # type: ignore[call-arg]


class TestOrgConfigUpdate:
    """Tests for the OrgConfigUpdate schema."""

    def test_default_is_none(self) -> None:
        update = OrgConfigUpdate()
        assert update.copilot_cost_per_seat is None

    def test_accepts_float(self) -> None:
        update = OrgConfigUpdate(copilot_cost_per_seat=39.0)
        assert update.copilot_cost_per_seat == 39.0

    def test_accepts_zero(self) -> None:
        update = OrgConfigUpdate(copilot_cost_per_seat=0)
        assert update.copilot_cost_per_seat == 0

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            OrgConfigUpdate(copilot_cost_per_seat=-1.0)

    def test_accepts_none_explicitly(self) -> None:
        update = OrgConfigUpdate(copilot_cost_per_seat=None)
        assert update.copilot_cost_per_seat is None
