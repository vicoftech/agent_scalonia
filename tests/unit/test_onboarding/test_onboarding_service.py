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


def test_suggest_alias_alternatives_returns_three():
    svc = OnboardingService(user_dao=MagicMock())
    alts = svc.suggest_alias_alternatives("GolazoFan")
    assert len(alts) == 3
    assert all(a.startswith("GolazoFan") for a in alts)


def test_save_m1_alias_taken_always_returns_alternatives():
    dao = MagicMock()
    dao.get_profile.return_value = {"alias_suggestions_shown": True, "alias_retry_clicked": True}
    dao.alias_taken.return_value = True
    svc = OnboardingService(user_dao=dao)
    result = svc.save_m1_alias("u1", "Taken")
    assert result["ok"] is False
    assert result["alias_taken"] is True
    assert len(result["alternatives"]) == 3
    dao.update_profile.assert_called_with("u1", alias_suggestions_shown=True)


def test_save_m1_alias_success_clears_retry_flags():
    dao = MagicMock()
    dao.alias_taken.return_value = False
    svc = OnboardingService(user_dao=dao)
    result = svc.save_m1_alias("u1", "FreeAlias")
    assert result["ok"] is True
    dao.update_profile.assert_called_with(
        "u1",
        alias="FreeAlias",
        m1_step="awaiting_team",
        alias_suggestions_shown=None,
        alias_retry_clicked=None,
    )


def test_mark_alias_retry_first_time_prompts():
    dao = MagicMock()
    dao.get_profile.return_value = {}
    svc = OnboardingService(user_dao=dao)
    result = svc.mark_alias_retry("u1")
    assert result["retry_prompt"] is True
    dao.update_profile.assert_called_with("u1", alias_retry_clicked=True)


def test_mark_alias_retry_second_time_assigns_temp():
    dao = MagicMock()
    dao.get_profile.return_value = {"alias_suggestions_shown": True}
    svc = OnboardingService(user_dao=dao)
    result = svc.mark_alias_retry("u1")
    assert result["ok"] is True
    assert result["used_temp"] is True
    assert result["alias"].startswith("Jugador_")
    dao.update_profile.assert_called_once()
    call_kw = dao.update_profile.call_args
    assert call_kw[0][0] == "u1"
    assert call_kw[1]["m1_step"] == "awaiting_team"


def test_first_post_start_instruction():
    from src.services.onboarding_service import FIRST_POST_START_INSTRUCTION

    assert "NO repitas bienvenida" in FIRST_POST_START_INSTRUCTION
