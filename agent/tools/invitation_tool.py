"""agent/tools/invitation_tool.py — SPEC-020 invitaciones vía deep link Telegram."""
from __future__ import annotations

import json
import logging
from typing import Callable

from strands import tool

logger = logging.getLogger(__name__)

_UUID_RE = __import__("re").compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    __import__("re").IGNORECASE,
)


def _execute_invitation_tool(
    caller_user_id: str,
    action: str,
    max_uses: int = 1,
    invite_id: str | None = None,
    status_filter: str | None = None,
    group_id: str | None = None,
) -> str:
    from src.services.invitation_service import InvitationService

    if not caller_user_id or caller_user_id in ("anonymous", "unregistered"):
        from src.services.auth_service import INACTIVE_USER_MESSAGE

        return INACTIVE_USER_MESSAGE
    if not _UUID_RE.match(caller_user_id):
        return f"user_id de sesión inválido: {caller_user_id!r}"

    svc = InvitationService()
    action = (action or "").strip().lower()

    if action == "create":
        result = svc.create_invitation(caller_user_id, max_uses=max_uses, group_id=group_id)
        return result["message"]

    if action == "list":
        rows = svc.list_my_invitations(caller_user_id, status_filter=status_filter)
        if not rows:
            return "No tenés invitaciones con ese filtro."
        lines = []
        for r in rows:
            lines.append(
                f"- {r['invite_id']} [{r['status']}] "
                f"{r['uses_count']}/{r['max_uses']} · {r['group_name']} · expira {r['expires_at']}\n"
                f"  {r['link']}"
            )
        return "Tus invitaciones:\n" + "\n".join(lines)

    if action == "revoke":
        if not invite_id:
            return "Falta invite_id para revocar."
        svc.revoke_invitation(invite_id, caller_user_id)
        return f"Invitación {invite_id} revocada."

    if action == "uses":
        if not invite_id:
            return "Falta invite_id."
        uses = svc.get_invitation_uses(invite_id, caller_user_id)
        if not uses:
            return f"Nadie usó aún la invitación {invite_id}."
        return json.dumps(uses, ensure_ascii=False, indent=2)

    return f"action desconocida: {action}. Usá create|list|revoke|uses."


def make_invitation_tool(caller_user_id: str) -> Callable:
    """Tool ligado al user_id de la invocación (el LLM no debe adivinar el UUID)."""

    @tool
    def invitation_tool(
        action: str,
        max_uses: int = 1,
        invite_id: str | None = None,
        status_filter: str | None = None,
        group_id: str | None = None,
    ) -> str:
        """
        Gestiona invitaciones al grupo (deep link t.me/Bot?start=<invite_id>).

        action='create'  → nueva invitación (max_uses, default 1).
        action='list'    → mis invitaciones (status_filter opcional: ACTIVE|EXHAUSTED|...).
        action='revoke'  → cancela invitación activa (invite_id requerido).
        action='uses'    → quiénes usaron una invitación (solo creador o admin).
        """
        try:
            return _execute_invitation_tool(
                caller_user_id,
                action,
                max_uses=max_uses,
                invite_id=invite_id,
                status_filter=status_filter,
                group_id=group_id,
            )
        except ValueError as exc:
            return str(exc)
        except Exception as exc:
            logger.warning("invitation_tool error: %s", exc, exc_info=True)
            return f"Error al gestionar invitaciones: {exc}"

    return invitation_tool
