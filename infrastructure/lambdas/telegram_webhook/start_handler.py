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
from src.services.onboarding_service import M1_STEP_ALIAS, M1_STEP_LANG, M1_STEP_TEAM, STAGE_M1_PENDING
from src.utils.telegram_start import parse_start_payload

from onboarding_handler import m1_welcome_message
from src.services.onboarding_telegram_ui import language_keyboard, team_keyboard


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def handle_start_command(chat_id: int, text: str) -> tuple[str, dict | None] | None:
    """
    Procesa /start [invite_id].
    Retorna (mensaje, reply_markup) o None si no es /start.
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
        users.set_telegram_chat_id(existing["user_id"], chat_id)
        if existing.get("status") != USER_STATUS_ACTIVE:
            return INACTIVE_USER_MESSAGE, None
        if existing.get("onboarding_stage") == STAGE_M1_PENDING:
            step = existing.get("m1_step") or M1_STEP_ALIAS
            if step == M1_STEP_TEAM:
                return "Elegí tu selección con los botones 👇", team_keyboard()
            if step == M1_STEP_LANG:
                return "¿En qué idioma preferís que te responda?", language_keyboard()
            return m1_welcome_message(), None
        if invite_id:
            try:
                result = invitations.accept_invitation_for_existing_user(
                    existing["user_id"], invite_id
                )
            except ValueError as exc:
                code = str(exc)
                if code in (
                    "INVITATION_NOT_USABLE",
                    "INVITATION_NOT_ACTIVE",
                    "INVITATION_INVALID",
                ):
                    return (
                        "Esta invitación ya no está vigente. "
                        "Pedile a quien te la mandó que genere una nueva.",
                        None,
                    )
                if code == "INVITATION_EXPIRED":
                    return (
                        "Esta invitación expiró (tenía 24hs de vigencia). Pedí una nueva.",
                        None,
                    )
                if code == "LIMIT_REACHED_INVITES":
                    return (
                        "El grupo ya no tiene cupo. Pedile al admin que amplíe el límite.",
                        None,
                    )
                raise
            name = result.get("group_name", "el grupo")
            if result.get("joined_new"):
                return (
                    f'✅ Te sumamos a "{name}".\nUsá /grupos para ver tus grupos.',
                    None,
                )
            return f'ℹ️ Ya formás parte de "{name}".', None

        alias = existing.get("alias", "jugador")
        return f"¡Hola de nuevo, {alias}! Ya estás registrado.", None

    if invite_id:
        invite = invite_dao.get(invite_id)
        if not invite or invite.get("status") != "ACTIVE":
            return (
                "Esta invitación ya no está vigente. "
                "Pedile a quien te la mandó que genere una nueva.",
                None,
            )
        if invite.get("expires_at", "") < _now_iso():
            invite_dao.update_status(invite_id, "EXPIRED")
            return "Esta invitación expiró (tenía 24hs de vigencia). Pedí una nueva.", None

        new_user_id = str(uuid4())
        users.create_telegram_user(new_user_id, platform_id_hash, tg_chat_id=chat_id)
        try:
            result = invitations.validate_and_use(invite_id, new_user_id)
        except ValueError as exc:
            code = str(exc)
            if code in ("INVITATION_NOT_USABLE", "INVITATION_NOT_ACTIVE"):
                return (
                    "Esta invitación ya no está vigente. "
                    "Pedile a quien te la mandó que genere una nueva.",
                    None,
                )
            if code == "INVITATION_EXPIRED":
                return "Esta invitación expiró (tenía 24hs de vigencia). Pedí una nueva.", None
            raise
        users.set_pending_first_agent_turn(new_user_id)
        users.update_profile(new_user_id, m1_step=M1_STEP_ALIAS)
        return m1_welcome_message(group_name=result["group_name"]), None

    return INVITATION_REQUIRED_MESSAGE, None
