"""ISSUE-025 / SPEC-019 — contexto de onboarding en el agente."""
from unittest.mock import MagicMock

from src.services.onboarding_service import (
    FIRST_POST_START_INSTRUCTION,
    OnboardingService,
)


def test_build_session_context_m1_pending():
    dao = MagicMock()
    dao.get_profile.return_value = {
        "alias": "Jugador",
        "onboarding_stage": "M1_PENDING",
        "is_admin": False,
    }
    ctx = OnboardingService(user_dao=dao).build_session_context("user-1")
    assert "M1_PENDING" in ctx
    assert "respondé la pregunta primero" in ctx.lower()


def test_build_session_context_m3_empty_extra():
    dao = MagicMock()
    dao.get_profile.return_value = {
        "alias": "Admin",
        "onboarding_stage": "M3_COMPLETE",
        "is_admin": True,
    }
    ctx = OnboardingService(user_dao=dao).build_session_context("admin-1")
    assert "M3_COMPLETE" in ctx
    assert "Onboarding M1" not in ctx


def test_build_session_context_anonymous():
    assert OnboardingService().build_session_context("anonymous") == ""


def test_first_post_start_instruction_mentions_no_repeat():
    assert "NO repitas bienvenida" in FIRST_POST_START_INSTRUCTION
    assert "kb_retrieval_tool" in FIRST_POST_START_INSTRUCTION
