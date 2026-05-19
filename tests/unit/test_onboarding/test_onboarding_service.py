"""SPEC-019 / ISSUE-025 — onboarding service."""
from unittest.mock import MagicMock

from src.services.onboarding_service import (
    EVENT_FIRST_PREDICTION,
    EVENT_FIRST_RANKING,
    EVENT_FIRST_TRIVIA,
    MOMENT_M2_PLAYER,
    OnboardingService,
    STAGE_M1_COMPLETE,
    STAGE_M1_PENDING,
    STAGE_M3_COMPLETE,
)


def test_build_session_context_m1_pending():
    dao = MagicMock()
    dao.get_profile.return_value = {
        "alias": "Jugador",
        "onboarding_stage": STAGE_M1_PENDING,
        "is_admin": False,
    }
    ctx = OnboardingService(user_dao=dao).build_session_context("user-1")
    assert "M1_PENDING" in ctx
    assert "Telegram guía" in ctx


def test_build_session_context_m3_empty_extra():
    dao = MagicMock()
    dao.get_profile.return_value = {
        "alias": "Admin",
        "onboarding_stage": STAGE_M3_COMPLETE,
        "is_admin": True,
    }
    ctx = OnboardingService(user_dao=dao).build_session_context("admin-1")
    assert "M3_COMPLETE" in ctx
    assert "Onboarding M1" not in ctx


def test_validate_alias_rules():
    svc = OnboardingService(user_dao=MagicMock())
    assert svc.validate_alias("a")[0] is False
    assert svc.validate_alias("GolazoFan")[0] is True
    assert svc.validate_alias("bad alias")[0] is False


def test_should_trigger_m2_after_prediction():
    dao = MagicMock()
    dao.get_profile.return_value = {
        "onboarding_stage": STAGE_M1_COMPLETE,
        "onboarding_m2_player_done": False,
        "favorite_team": "ARG",
    }
    svc = OnboardingService(user_dao=dao)
    pending = svc.should_trigger("u1", EVENT_FIRST_PREDICTION)
    assert pending["moment"] == MOMENT_M2_PLAYER
    assert "Messi" in pending["suggested_players"]


def test_skip_m1_alias_advances_step():
    dao = MagicMock()
    dao.get_profile.return_value = {
        "onboarding_stage": STAGE_M1_PENDING,
        "m1_step": "awaiting_alias",
    }
    svc = OnboardingService(user_dao=dao)
    result = svc.skip_current_moment("u1")
    assert result.get("m1_step") == "awaiting_team"
    dao.update_profile.assert_called()


def test_get_pending_prompt_m3():
    dao = MagicMock()
    dao.get_profile.return_value = {
        "onboarding_stage": "M2_COMPLETE",
        "onboarding_m3_done": False,
    }
    svc = OnboardingService(user_dao=dao)
    text = svc.get_pending_prompt("u1", EVENT_FIRST_RANKING)
    assert text and "prode" in text.lower()


def test_first_post_start_instruction():
    from src.services.onboarding_service import FIRST_POST_START_INSTRUCTION

    assert "NO repitas bienvenida" in FIRST_POST_START_INSTRUCTION
