"""Comandos /invitar sin LLM — SPEC-020."""
from __future__ import annotations

import re

from src.services.invitation_service import InvitationService

_INVITAR = re.compile(r"^/invitar(?:@[\w_]+)?(?:\s+(\d+))?\s*$", re.IGNORECASE)
_LISTAR = re.compile(r"^/mis-invitaciones\s*$", re.IGNORECASE)
_REVOCAR = re.compile(r"^/revocar(?:@[\w_]+)?\s+([A-Za-z0-9]{8})\s*$", re.IGNORECASE)


def handle_invitation_command(user_id: str, text: str) -> str | None:
    """Respuesta fija o None si el mensaje no es comando de invitación."""
    text = (text or "").strip()
    svc = InvitationService()

    m = _INVITAR.match(text)
    if m:
        max_uses = int(m.group(1) or 1)
        try:
            return svc.create_invitation(user_id, max_uses=max_uses)["message"]
        except ValueError as exc:
            return str(exc)

    if _LISTAR.match(text):
        rows = svc.list_my_invitations(user_id)
        if not rows:
            return "No tenés invitaciones activas."
        lines = [
            f"- {r['invite_id']} [{r['status']}] {r['uses_count']}/{r['max_uses']}\n  {r['link']}"
            for r in rows
        ]
        return "Tus invitaciones:\n" + "\n".join(lines)

    m = _REVOCAR.match(text)
    if m:
        invite_id = m.group(1)
        try:
            svc.revoke_invitation(invite_id, user_id)
            return f"Invitación {invite_id} revocada."
        except ValueError as exc:
            return str(exc)

    return None
