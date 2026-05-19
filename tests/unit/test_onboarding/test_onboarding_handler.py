"""Telegram onboarding handler — heurísticas M1."""
from infrastructure.lambdas.telegram_webhook.onboarding_handler import (  # noqa: PLC0415
    _looks_like_question,
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
