"""Comandos y callbacks Ask IA — SPEC-2026-043."""
from __future__ import annotations

import re

from src.services.ask_ia_service import AskIaService, INVALID_COMMAND, RESULTADOS_DEPRECATED

_ASK_IA = re.compile(r"^/ask[_-]ia(?:@[\w_]+)?\s*$", re.IGNORECASE)
_IA_OTORGAR = re.compile(
    r"^/ia[_-]otorgar(?:@[\w_]+)?\s+(\S+)\s+(-?\d+)\s*$",
    re.IGNORECASE,
)
_RESULTADOS = re.compile(r"^/resultados(?:@[\w_]+)?\s*$", re.IGNORECASE)
_CANCEL = re.compile(r"^/(?:cancel|cancelar)(?:@[\w_]+)?\s*$", re.IGNORECASE)


def _service() -> AskIaService:
    from handler import _invoke_agent

    return AskIaService(invoke_agent=_invoke_agent)


def handle_ask_ia_command(user_id: str, text: str) -> tuple[str, dict | None] | None:
    stripped = (text or "").strip()

    if _RESULTADOS.match(stripped):
        return RESULTADOS_DEPRECATED, None

    if _ASK_IA.match(stripped):
        return _service().start_session(user_id)

    m = _IA_OTORGAR.match(stripped)
    if m:
        return _service().admin_grant(user_id, m.group(1), int(m.group(2))), None

    return None


def handle_ask_ia_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("ia:"):
        return None
    return _service().callback(user_id, data)


def handle_ask_ia_pending_text(user_id: str, text: str) -> tuple[str, dict | None] | None:
    from src.dao.dynamo.user_dao import UserDAO

    profile = UserDAO().get_profile(user_id) or {}
    if _CANCEL.match((text or "").strip()):
        if profile.get("ai_awaiting_prompt") or profile.get("ai_purchase_pending"):
            return _service().end_session(user_id), None
        return None
    if profile.get("ai_awaiting_prompt"):
        return _service().handle_user_prompt(user_id, text)
    return None


def handle_ask_ia_purchase_proof(
    user_id: str, *, file_id: str, file_kind: str
) -> str | None:
    from src.dao.dynamo.user_dao import UserDAO

    profile = UserDAO().get_profile(user_id) or {}
    if not profile.get("ai_purchase_pending"):
        return None
    return _service().handle_purchase_proof(
        user_id, file_id=file_id, file_kind=file_kind
    )


def invalid_command_message() -> str:
    return INVALID_COMMAND
