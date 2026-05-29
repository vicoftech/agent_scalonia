"""SPEC-2026-043 — Ask IA créditos y sesión."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.services.ask_ia_service import AskIaService

DISPLAY_TZ = __import__(
    "src.services.ask_ia_service", fromlist=["DISPLAY_TZ"]
).DISPLAY_TZ


def _svc(**kwargs) -> AskIaService:
    users = kwargs.get("users") or MagicMock()
    profile_store = kwargs.get("profile_store") or {
        "user_id": "u1",
        "alias": "toti",
        "status": "ACTIVE",
        "ai_daily_remaining": 5,
        "ai_bonus_credits": 0,
        "ai_credits_reset_date": datetime.now(DISPLAY_TZ).date().isoformat(),
    }

    def _get(_uid):
        return dict(profile_store)

    users.get_profile.side_effect = _get
    users.update_profile.side_effect = lambda _u, **kw: profile_store.update(kw)
    users.resolve_alias.return_value = profile_store
    users.find_alias_suggestions.return_value = []

    purchases = MagicMock()
    invoke = kwargs.get("invoke_agent") or MagicMock(return_value="Respuesta del agente sobre el Mundial.")

    return AskIaService(users=users, purchases=purchases, invoke_agent=invoke)


def test_ensure_daily_reset_repone_cupo():
    store = {"user_id": "u1", "ai_credits_reset_date": "2000-01-01"}
    svc = _svc(profile_store=store)
    svc.ensure_daily_reset("u1")
    assert store.get("ai_daily_remaining") == 5


def test_start_session_sets_awaiting():
    today = datetime.now(DISPLAY_TZ).date().isoformat()
    store = {
        "user_id": "u1",
        "ai_daily_remaining": 3,
        "ai_bonus_credits": 0,
        "ai_credits_reset_date": today,
    }
    svc = _svc(profile_store=store)
    text, _kb = svc.start_session("u1")
    assert "consultas disponibles" in text
    assert store.get("ai_awaiting_prompt") is True


def test_handle_prompt_uses_kb_direct_reply_without_agent():
    store = {
        "user_id": "u1",
        "ai_daily_remaining": 2,
        "ai_bonus_credits": 0,
        "ai_awaiting_prompt": True,
        "ai_credits_reset_date": datetime.now(DISPLAY_TZ).date().isoformat(),
    }
    svc = _svc(profile_store=store)
    invoke = MagicMock()
    svc._invoke_agent = invoke
    from src.services.ask_ia_knowledge import AskIaTurnPrep

    with patch(
        "src.services.ask_ia_knowledge.prepare_ask_ia_turn",
        return_value=AskIaTurnPrep(direct_reply="📚 El primer gol fue en 1930."),
    ):
        text, kb = svc.handle_user_prompt("u1", "primer gol mundial")
    assert "1930" in text
    assert store["ai_daily_remaining"] == 1
    invoke.assert_not_called()


def test_handle_prompt_consumes_daily_credit():
    store = {
        "user_id": "u1",
        "ai_daily_remaining": 2,
        "ai_bonus_credits": 0,
        "ai_awaiting_prompt": True,
        "ai_credits_reset_date": datetime.now(DISPLAY_TZ).date().isoformat(),
    }
    svc = _svc(profile_store=store)
    text, kb = svc.handle_user_prompt("u1", "¿Quién ganó el 86?")
    assert "Respuesta del agente" in text
    assert store["ai_daily_remaining"] == 1
    assert store.get("ai_awaiting_prompt") is False
    assert kb is not None


def test_handle_prompt_no_charge_on_error_response():
    today = datetime.now(DISPLAY_TZ).date().isoformat()
    store = {
        "user_id": "u1",
        "ai_daily_remaining": 2,
        "ai_awaiting_prompt": True,
        "ai_credits_reset_date": today,
    }
    svc = _svc(
        profile_store=store,
        invoke_agent=MagicMock(return_value="Hubo un error procesando tu mensaje."),
    )
    svc.handle_user_prompt("u1", "pregunta")
    assert store["ai_daily_remaining"] == 2
    assert store.get("ai_awaiting_prompt") is False


def test_handle_prompt_transient_error_keeps_session():
    today = datetime.now(DISPLAY_TZ).date().isoformat()
    store = {
        "user_id": "u1",
        "ai_daily_remaining": 2,
        "ai_awaiting_prompt": True,
        "ai_credits_reset_date": today,
    }
    cold_start = (
        "⏳ El agente IA está arrancando.\n"
        "No se descontó una consulta. Reenviá la misma pregunta."
    )
    svc = _svc(profile_store=store, invoke_agent=MagicMock(return_value=cold_start))
    text, kb = svc.handle_user_prompt("u1", "¿Quién es favorito?")
    assert store["ai_daily_remaining"] == 2
    assert store.get("ai_awaiting_prompt") is True
    assert "reenviar" in text.lower()
    assert kb is None


def test_purchase_proof_credits_bonus():
    store = {
        "user_id": "u1",
        "alias": "toti",
        "ai_bonus_credits": 0,
        "ai_purchase_pending": True,
    }
    svc = _svc(profile_store=store)
    msg = svc.handle_purchase_proof("u1", file_id="file123", file_kind="photo")
    assert "Acreditamos" in msg
    assert store["ai_bonus_credits"] == 20
    assert store.get("ai_purchase_pending") is False


def test_purchase_cooldown_blocks_second():
    store = {
        "user_id": "u1",
        "ai_purchase_pending": True,
        "ai_last_auto_purchase_at": datetime.now(timezone.utc).isoformat(),
    }
    svc = _svc(profile_store=store)
    msg = svc.handle_purchase_proof("u1", file_id="f2", file_kind="photo")
    assert "24 h" in msg


def test_ia_otorgar_usage_without_args():
    from infrastructure.lambdas.telegram_webhook.ask_ia_commands import (
        handle_ask_ia_command,
    )

    text, kb = handle_ask_ia_command("u1", "/ia_otorgar")
    assert text is not None
    assert "ia_otorgar" in text.lower()
    assert kb is None


def test_admin_grant_requires_admin():
    from unittest.mock import patch

    svc = _svc()
    with patch("src.services.auth_service.AuthService") as auth:
        auth.return_value.is_admin_global.return_value = False
        assert "administrador" in svc.admin_grant("u1", "toti", 5).lower()


def test_admin_grant_notifies_recipient():
    from unittest.mock import patch

    store = {
        "user_id": "u2",
        "alias": "vic",
        "status": "ACTIVE",
        "ai_bonus_credits": 0,
        "ai_daily_remaining": 5,
        "ai_credits_reset_date": datetime.now(DISPLAY_TZ).date().isoformat(),
        "tg_chat_id": 999888777,
    }
    svc = _svc(profile_store=store)
    with (
        patch("src.services.auth_service.AuthService") as auth,
        patch("src.clients.telegram_client.send_telegram_message") as send,
        patch("src.clients.telegram_client.get_bot_token", return_value="tok"),
    ):
        auth.return_value.is_admin_global.return_value = True
        msg = svc.admin_grant("admin1", "vic", 10)
    assert "notificó" in msg.lower()
    send.assert_called_once()
    body = send.call_args[0][1]
    assert "+10" in body
    assert "999888777" == str(send.call_args[0][0])


def test_admin_grant_skips_notify_without_chat_id():
    from unittest.mock import patch

    store = {
        "user_id": "u2",
        "alias": "vic",
        "status": "ACTIVE",
        "ai_bonus_credits": 0,
        "ai_daily_remaining": 5,
        "ai_credits_reset_date": datetime.now(DISPLAY_TZ).date().isoformat(),
    }
    svc = _svc(profile_store=store)
    with (
        patch("src.services.auth_service.AuthService") as auth,
        patch("src.clients.telegram_client.send_telegram_message") as send,
    ):
        auth.return_value.is_admin_global.return_value = True
        msg = svc.admin_grant("admin1", "vic", 3)
    send.assert_not_called()
    assert "/start" in msg
