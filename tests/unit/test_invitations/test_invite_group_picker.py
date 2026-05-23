"""Picker de grupo en /invitar — admin ve GLOBAL + grupos privados."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.invitation_callbacks import (
    handle_invitation_callback,
)
from src.services.invitation_telegram_ui import invite_destination_keyboard


def test_invite_keyboard_admin_shows_global_and_private_groups():
    groups = [
        {"group_id": "g1", "name": "Scaloneta", "avatar": "⚽", "is_global": False},
        {"group_id": "g2", "name": "Putiskys", "avatar": "🎯", "is_global": False},
    ]
    kb = invite_destination_keyboard(3, is_admin=True, owner_group=None, private_groups=groups)
    labels = [
        btn["text"]
        for row in kb["inline_keyboard"]
        for btn in row
    ]
    assert any("GLOBAL" in t for t in labels)
    assert any("Scaloneta" in t for t in labels)
    assert any("Putiskys" in t for t in labels)


def test_list_private_groups_merges_membership():
    from src.dao.dynamo.group_dao import GroupDAO

    def _get_group(gid: str):
        return {
            "GLOBAL": {"group_id": "GLOBAL", "name": "General", "is_global": True},
            "g1": {"group_id": "g1", "name": "Scaloneta", "is_global": False, "status": "ACTIVE"},
            "g2": {"group_id": "g2", "name": "Putiskys", "is_global": False, "status": "ACTIVE"},
        }.get(gid)

    with (
        patch.object(GroupDAO, "list_active_groups", return_value=[]),
        patch.object(
            GroupDAO, "list_group_ids_for_user", return_value=["GLOBAL", "g1", "g2"]
        ),
        patch.object(GroupDAO, "get_group", side_effect=_get_group),
    ):
        out = GroupDAO().list_private_groups_for_invite("admin-1", is_admin=True)
    names = {g["name"] for g in out}
    assert names == {"Putiskys", "Scaloneta"}


def test_admin_invitar_shows_private_on_first_screen():
    privates = [
        {"group_id": "g1", "name": "Scaloneta", "avatar": "⚽"},
        {"group_id": "g2", "name": "Putiskys", "avatar": "🎯"},
    ]
    with (
        patch(
            "infrastructure.lambdas.telegram_webhook.invitation_commands.UserDAO"
        ) as mock_users,
        patch(
            "infrastructure.lambdas.telegram_webhook.invitation_commands.AuthService"
        ) as mock_auth,
        patch(
            "infrastructure.lambdas.telegram_webhook.invitation_commands.GroupDAO"
        ) as mock_groups,
        patch(
            "infrastructure.lambdas.telegram_webhook.invitation_commands.InvitationService"
        ),
    ):
        mock_users.return_value.get_profile.return_value = {"is_admin": True}
        mock_auth.return_value.is_admin_global.return_value = True
        mock_groups.return_value.get_owner_group_id.return_value = None
        mock_groups.return_value.list_private_groups_for_invite.return_value = privates
        from infrastructure.lambdas.telegram_webhook.invitation_commands import (
            handle_invitation_command,
        )

        text, markup = handle_invitation_command("admin-1", "/invitar 3")

    callbacks = [
        btn.get("callback_data", "")
        for row in markup["inline_keyboard"]
        for btn in row
    ]
    assert any("inv:grp:g1:" in c for c in callbacks)
    assert any("inv:grp:g2:" in c for c in callbacks)
    assert any("inv:grp:GLOBAL:" in c for c in callbacks)
