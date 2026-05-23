"""Callbacks inline inv:* — SPEC-029."""
from __future__ import annotations

from src.dao.dynamo.group_dao import GroupDAO
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
    auth = AuthService()
    return GroupDAO().list_private_groups_for_invite(
        user_id, is_admin=auth.is_admin_global(user_id)
    )


def handle_invitation_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("inv:"):
        return None

    if data == "inv:cancel":
        return "Invitación cancelada.", None

    auth = AuthService()
    is_admin = auth.is_admin_global(user_id)
    groups_dao = GroupDAO()

    if data.startswith("inv:dest:"):
        try:
            max_uses = max(1, int(data.split(":", maxsplit=2)[2]))
        except (IndexError, ValueError):
            max_uses = 1
        owner_gid = groups_dao.get_owner_group_id(user_id)
        owner_group = groups_dao.get_group(owner_gid) if owner_gid else None
        privates = (
            groups_dao.list_private_groups_for_invite(user_id, is_admin=is_admin)
            if is_admin
            else []
        )
        text = (
            f"Elegí el grupo destino ({max_uses} cupo{'s' if max_uses != 1 else ''}):"
        )
        return text, invite_destination_keyboard(
            max_uses,
            is_admin=is_admin,
            owner_group=owner_group,
            private_groups=privates,
        )

    if data.startswith("inv:pick:"):
        try:
            max_uses = max(1, int(data.split(":", maxsplit=2)[2]))
        except (IndexError, ValueError):
            max_uses = 1
        pick_groups = _groups_for_invite_picker(user_id)
        if not pick_groups:
            return (
                "No hay grupos privados cargados. Usá GLOBAL o creá uno con /crear-grupo.",
                invite_destination_keyboard(
                    max_uses,
                    is_admin=is_admin,
                    owner_group=None,
                    private_groups=[],
                ),
            )
        return (
            f"Todos los grupos ({max_uses} cupos):",
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
