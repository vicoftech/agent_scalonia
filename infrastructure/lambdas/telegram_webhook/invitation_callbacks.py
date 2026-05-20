"""Callbacks inline inv:* — SPEC-029."""
from __future__ import annotations

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
from src.services.auth_service import AuthService
from src.services.invitation_service import InvitationService
from src.services.invitation_telegram_ui import (
    invite_destination_keyboard,
    invite_group_pick_keyboard,
)


def _parse_inv_grp(data: str) -> tuple[str, int] | None:
    if not data.startswith("inv:grp:"):
        return None
    rest = data[len("inv:grp:") :]
    gid, _, uses_s = rest.rpartition(":")
    try:
        return gid, max(1, int(uses_s))
    except ValueError:
        return None


def _groups_for_invite_picker(user_id: str) -> list[dict]:
    groups = GroupDAO().list_active_groups(limit=15)
    auth = AuthService()
    if auth.is_admin_global(user_id):
        return [g for g in groups if g.get("status") != "DELETED"]
    owned = GroupDAO().get_owner_group_id(user_id)
    return [g for g in groups if g.get("group_id") == owned and not g.get("is_global")]


def handle_invitation_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("inv:"):
        return None

    if data == "inv:cancel":
        return "Invitación cancelada.", None

    if data.startswith("inv:dest:"):
        try:
            max_uses = max(1, int(data.split(":", maxsplit=2)[2]))
        except (IndexError, ValueError):
            max_uses = 1
        auth = AuthService()
        is_admin = auth.is_admin_global(user_id)
        owner_gid = GroupDAO().get_owner_group_id(user_id)
        owner_group = GroupDAO().get_group(owner_gid) if owner_gid else None
        text = (
            f"Elegí el grupo destino ({max_uses} cupo{'s' if max_uses != 1 else ''}):"
        )
        return text, invite_destination_keyboard(
            max_uses, is_admin=is_admin, owner_group=owner_group
        )

    if data.startswith("inv:pick:"):
        try:
            max_uses = max(1, int(data.split(":", maxsplit=2)[2]))
        except (IndexError, ValueError):
            max_uses = 1
        pick_groups = _groups_for_invite_picker(user_id)
        if not pick_groups:
            return (
                "No hay otros grupos disponibles. Usá GLOBAL o creá un grupo con /crear-grupo.",
                invite_destination_keyboard(
                    max_uses,
                    is_admin=AuthService().is_admin_global(user_id),
                    owner_group=None,
                ),
            )
        return (
            f"Grupo destino ({max_uses} cupos):",
            invite_group_pick_keyboard(pick_groups, max_uses),
        )

    parsed = _parse_inv_grp(data)
    if parsed:
        group_id, max_uses = parsed
        try:
            result = InvitationService().create_invitation(
                user_id, max_uses=max_uses, group_id=group_id
            )
            return result["message"], None
        except ValueError as exc:
            return str(exc), None

    return None
