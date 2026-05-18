"""agent/tools/invitation_tool.py — SPEC-020 invitaciones vía deep link Telegram."""
from __future__ import annotations

import json
import logging

from strands import tool

logger = logging.getLogger(__name__)


@tool
def invitation_tool(
    action: str,
    user_id: str,
    max_uses: int = 1,
    invite_id: str | None = None,
    status_filter: str | None = None,
    group_id: str | None = None,
) -> str:
    """
    Gestiona invitaciones al grupo (deep link t.me/Bot?start=<invite_id>).

    action='create'  → nueva invitación (max_uses, default 1). Requiere user_id.
    action='list'    → mis invitaciones (status_filter opcional: ACTIVE|EXHAUSTED|...).
    action='revoke'  → cancela invitación activa (invite_id requerido).
    action='uses'    → quiénes usaron una invitación (solo creador o admin).

    user_id es el UUID interno del usuario (no el chat_id de Telegram).
    """
    try:
        from src.services.auth_service import AuthService
        from src.services.invitation_service import InvitationService

        allowed, deny_message = AuthService().require_active_user_id(user_id)
        if not allowed:
            return deny_message

        svc = InvitationService()
        action = (action or "").strip().lower()

        if action == "create":
            result = svc.create_invitation(user_id, max_uses=max_uses, group_id=group_id)
            return result["message"]

        if action == "list":
            rows = svc.list_my_invitations(user_id, status_filter=status_filter)
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
            svc.revoke_invitation(invite_id, user_id)
            return f"Invitación {invite_id} revocada."

        if action == "uses":
            if not invite_id:
                return "Falta invite_id."
            uses = svc.get_invitation_uses(invite_id, user_id)
            if not uses:
                return f"Nadie usó aún la invitación {invite_id}."
            return json.dumps(uses, ensure_ascii=False, indent=2)

        return f"action desconocida: {action}. Usá create|list|revoke|uses."

    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        logger.warning("invitation_tool error: %s", exc, exc_info=True)
        return f"Error al gestionar invitaciones: {exc}"
