"""Telegram onboarding handler — heurísticas M1 y alias duplicado."""
from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.onboarding_handler import (  # noqa: PLC0415
    _looks_like_question,
    handle_onboarding_callback,
    handle_onboarding_message,
)
from src.services.onboarding_service import STAGE_M1_PENDING


def test_looks_like_question():
    assert _looks_like_question("¿Cuándo juega Argentina?")
    assert not _looks_like_question("GolazoFan")


def test_alias_step_routes_question_to_agent():
    profile = {"onboarding_stage": STAGE_M1_PENDING, "m1_step": "awaiting_alias"}
    text, markup = handle_onboarding_message("u1", profile, "¿Cuándo juega Argentina?")
    assert text is None and markup is None


@patch("infrastructure.lambdas.telegram_webhook.onboarding_handler.OnboardingService")
def test_alias_taken_shows_three_alternatives_and_retry(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.save_m1_alias.return_value = {
        "ok": False,
        "alias_taken": True,
        "alternatives": ["GolazoFan1", "GolazoFan2", "GolazoFan47"],
    }
    profile = {"onboarding_stage": STAGE_M1_PENDING, "m1_step": "awaiting_alias"}
    text, markup = handle_onboarding_message("u1", profile, "GolazoFan")
    assert "tomado" in text.lower()
    kb = markup["inline_keyboard"]
    assert len(kb) == 4
    assert kb[0][0]["text"] == "GolazoFan1"
    assert kb[3][0]["text"] == "✏️ Escribir otro"
    assert kb[3][0]["callback_data"] == "onb:alias:retry"


@patch("infrastructure.lambdas.telegram_webhook.onboarding_handler.OnboardingService")
def test_alias_retry_callback_prompts_typing(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.mark_alias_retry.return_value = {"ok": False, "retry_prompt": True}
    text, markup = handle_onboarding_callback("u1", {}, "onb:alias:retry")
    assert "Escribí otro alias" in text
    assert markup is None
    svc.mark_alias_retry.assert_called_once_with("u1")


@patch("infrastructure.lambdas.telegram_webhook.onboarding_handler.OnboardingService")
def test_alias_retry_callback_assigns_temp(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.mark_alias_retry.return_value = {
        "ok": True,
        "used_temp": True,
        "alias": "Jugador_AB12",
    }
    text, markup = handle_onboarding_callback("u1", {}, "onb:alias:retry")
    assert "Jugador_AB12" in text
    assert markup is not None


@patch("infrastructure.lambdas.telegram_webhook.onboarding_handler.OnboardingService")
def test_alias_button_taken_shows_alternatives_again(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.save_m1_alias.return_value = {
        "ok": False,
        "alias_taken": True,
        "alternatives": ["Alt1", "Alt2", "Alt3"],
    }
    text, markup = handle_onboarding_callback("u1", {}, "onb:alias:TakenBtn")
    assert markup["inline_keyboard"][3][0]["callback_data"] == "onb:alias:retry"
