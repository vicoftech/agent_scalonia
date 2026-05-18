"""Registro vía /start y deep links de invitación (SPEC-020)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.dao.dynamo.group_dao import GroupDAO
from src.dao.dynamo.invitation_dao import InvitationDAO
from src.dao.dynamo.user_dao import UserDAO
from src.services.auth_service import (
    INACTIVE_USER_MESSAGE,
    INVITATION_REQUIRED_MESSAGE,
    USER_STATUS_ACTIVE,
)
from src.services.invitation_service import InvitationService
from src.utils.telegram_start import parse_start_payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def handle_start_command(chat_id: int, text: str) -> str | None:
    """
    Procesa /start [invite_id]. Retorna mensaje de respuesta o None si no es /start.
    """
    if not text.startswith("/start"):
        return None

    invite_id = parse_start_payload(text)
    platform_id_hash = __import__("hashlib").sha256(str(chat_id).encode()).hexdigest()

    users = UserDAO()
    groups = GroupDAO()
    invite_dao = InvitationDAO()
    invitations = InvitationService(invitation_dao=invite_dao, user_dao=users, group_dao=groups)

    existing = users.get_by_platform_hash("TELEGRAM", platform_id_hash)
    if existing:
        if existing.get("status") != USER_STATUS_ACTIVE:
            return INACTIVE_USER_MESSAGE
        alias = existing.get("alias", "jugador")
        return f"¡Hola de nuevo, {alias}! Ya estás registrado."

    if invite_id:
        invite = invite_dao.get(invite_id)
        if not invite or invite.get("status") != "ACTIVE":
            return (
                "Esta invitación ya no está vigente. "
                "Pedile a quien te la mandó que genere una nueva."
            )
        if invite.get("expires_at", "") < _now_iso():
            invite_dao.update_status(invite_id, "EXPIRED")
            return "Esta invitación expiró (tenía 24hs de vigencia). Pedí una nueva."

        new_user_id = str(uuid4())
        users.create_telegram_user(new_user_id, platform_id_hash)
        try:
            result = invitations.validate_and_use(invite_id, new_user_id)
        except ValueError as exc:
            code = str(exc)
            if code in ("INVITATION_NOT_USABLE", "INVITATION_NOT_ACTIVE"):
                return (
                    "Esta invitación ya no está vigente. "
                    "Pedile a quien te la mandó que genere una nueva."
                )
            if code == "INVITATION_EXPIRED":
                return "Esta invitación expiró (tenía 24hs de vigencia). Pedí una nueva."
            raise
        return (
            f"¡Bienvenido al Prode Mundial 2026! "
            f"Te uniste al grupo {result['group_name']}."
        )

    return INVITATION_REQUIRED_MESSAGE
