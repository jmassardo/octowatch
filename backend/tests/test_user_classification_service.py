"""Tests for user_classification_service.classify_single_user logic."""

from __future__ import annotations

from app.services.user_classification_service import (
    ALL_PERSONAS,
    PERSONA_ADMIN_ONLY,
    PERSONA_API_CLI_ONLY,
    PERSONA_CICD_BOT,
    PERSONA_COPILOT_ACTIVE,
    PERSONA_IDE_ONLY,
    PERSONA_LIGHTLY_ACTIVE,
    PERSONA_POWER_USER,
    PERSONA_TRULY_DORMANT,
    PERSONA_WEB_UI_ONLY,
    classify_single_user,
)


class TestClassifySingleUser:
    """Unit tests for the pure classification function."""

    def test_zero_events_is_truly_dormant(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=0,
            surface_counts={},
            is_bot=False,
            passive_count=0,
        )
        assert persona == PERSONA_TRULY_DORMANT
        assert confidence == 1.0
        assert surfaces == []

    def test_low_passive_only_is_lightly_active(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=3,
            surface_counts={"git": 3},
            is_bot=False,
            passive_count=3,
        )
        assert persona == PERSONA_LIGHTLY_ACTIVE
        assert confidence == 0.9

    def test_low_events_mixed_is_lightly_active(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=4,
            surface_counts={"web": 2, "git": 2},
            is_bot=False,
            passive_count=1,
        )
        assert persona == PERSONA_LIGHTLY_ACTIVE
        assert confidence == 0.75

    def test_bot_with_activity_is_cicd_bot(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=100,
            surface_counts={"api": 80, "git": 20},
            is_bot=True,
            passive_count=5,
        )
        assert persona == PERSONA_CICD_BOT
        assert 0.7 <= confidence <= 0.95

    def test_copilot_events_detected(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=50,
            surface_counts={"web": 30, "copilot": 20},
            is_bot=False,
            passive_count=0,
        )
        assert persona == PERSONA_COPILOT_ACTIVE
        assert 0.7 <= confidence <= 0.95

    def test_admin_only_pure(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=20,
            surface_counts={"admin": 20},
            is_bot=False,
            passive_count=0,
        )
        assert persona == PERSONA_ADMIN_ONLY
        assert confidence == 0.95

    def test_admin_mostly(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=100,
            surface_counts={"admin": 85, "web": 15},
            is_bot=False,
            passive_count=0,
        )
        assert persona == PERSONA_ADMIN_ONLY

    def test_power_user_multi_surface(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=100,
            surface_counts={"web": 40, "git": 30, "api": 30},
            is_bot=False,
            passive_count=5,
        )
        assert persona == PERSONA_POWER_USER
        assert 0.7 <= confidence <= 0.95

    def test_web_ui_dominant(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=50,
            surface_counts={"web": 45, "git": 5},
            is_bot=False,
            passive_count=2,
        )
        assert persona == PERSONA_WEB_UI_ONLY

    def test_ide_dominant(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=50,
            surface_counts={"git": 45, "web": 5},
            is_bot=False,
            passive_count=2,
        )
        assert persona == PERSONA_IDE_ONLY

    def test_api_cli_dominant(self) -> None:
        persona, confidence, surfaces = classify_single_user(
            event_count=50,
            surface_counts={"api": 45, "web": 5},
            is_bot=False,
            passive_count=2,
        )
        assert persona == PERSONA_API_CLI_ONLY

    def test_confidence_always_between_0_and_1(self) -> None:
        """Verify confidence is always in [0, 1] for various inputs."""
        test_cases = [
            {
                "event_count": 0,
                "surface_counts": {},
                "is_bot": False,
                "passive_count": 0,
            },
            {
                "event_count": 1000,
                "surface_counts": {"web": 500, "git": 300, "api": 200},
                "is_bot": False,
                "passive_count": 10,
            },
            {
                "event_count": 1,
                "surface_counts": {"web": 1},
                "is_bot": True,
                "passive_count": 1,
            },
            {
                "event_count": 500,
                "surface_counts": {"admin": 500},
                "is_bot": False,
                "passive_count": 0,
            },
        ]
        for kwargs in test_cases:
            _, confidence, _ = classify_single_user(**kwargs)
            assert 0.0 <= confidence <= 1.0, f"Confidence {confidence} out of range for {kwargs}"

    def test_all_personas_constant_list(self) -> None:
        assert len(ALL_PERSONAS) == 9

    def test_surfaces_returned_correctly(self) -> None:
        _, _, surfaces = classify_single_user(
            event_count=100,
            surface_counts={"web": 40, "git": 30, "api": 30},
            is_bot=False,
            passive_count=5,
        )
        assert set(surfaces) == {"web", "git", "api"}

    def test_bot_no_cicd_events_still_classified(self) -> None:
        """Bot with no api/git events should not be CI/CD bot."""
        persona, _, _ = classify_single_user(
            event_count=10,
            surface_counts={"web": 10},
            is_bot=True,
            passive_count=0,
        )
        # Bot but only web actions — shouldn't be CI/CD bot
        assert persona != PERSONA_CICD_BOT

    def test_power_user_fallback_two_surfaces(self) -> None:
        persona, confidence, _ = classify_single_user(
            event_count=30,
            surface_counts={"web": 15, "git": 15},
            is_bot=False,
            passive_count=2,
        )
        assert persona == PERSONA_POWER_USER
        assert confidence == 0.6


class TestClassifySingleUserEdgeCases:
    """Edge cases for classification logic."""

    def test_single_event_passive(self) -> None:
        persona, _, _ = classify_single_user(
            event_count=1,
            surface_counts={"git": 1},
            is_bot=False,
            passive_count=1,
        )
        assert persona == PERSONA_LIGHTLY_ACTIVE

    def test_exactly_five_events_not_lightly_active(self) -> None:
        """5 events should not be Lightly Active (threshold is <5)."""
        persona, _, _ = classify_single_user(
            event_count=5,
            surface_counts={"web": 5},
            is_bot=False,
            passive_count=0,
        )
        assert persona != PERSONA_LIGHTLY_ACTIVE

    def test_copilot_takes_priority_over_power_user(self) -> None:
        """If copilot events exist, Copilot Active should be assigned even with 3+ surfaces."""
        persona, _, _ = classify_single_user(
            event_count=100,
            surface_counts={"web": 30, "git": 30, "api": 20, "copilot": 20},
            is_bot=False,
            passive_count=0,
        )
        assert persona == PERSONA_COPILOT_ACTIVE
