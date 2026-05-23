"""Picker de grupo en /invitar — admin ve todos los grupos privados."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.invitation_callbacks import (
    _groups_for_invite_picker,
    handle_invitation_callback,
)


def test_groups_for_invite_picker_admin_excludes_global_only():
    groups = [
        {"group_id": "GLOBAL", "name": "General", "is_global": True, "status": "ACTIVE"},
        {"group_id": "g1", "name": "Scaloneta", "is_global": False, "status": "ACTIVE"},
        {"group_id": "g2", "name": "Putiskys", "is_global": False, "status": "ACTIVE"},
    ]
    with (
        patch(
            "infrastructure.lambdas.telegram_webhook.invitation_callbacks.GroupDAO"
        ) as mock_dao,
        patch(
            "infrastructure.lambdas.telegram_webhook.invitation_callbacks.AuthService"
        ) as mock_auth,
    ):
        mock_dao.return_value.list_active_groups.return_value = groups
        mock_auth.return_value.is_admin_global.return_value = True
        picked = _groups_for_invite_picker("admin-1")

    ids = {g["group_id"] for g in picked}
    assert ids == {"g1", "g2"}


def test_inv_pick_shows_both_private_groups():
    groups = [
        {"group_id": "g1", "name": "Scaloneta", "avatar": "⚽", "is_global": False},
        {"group_id": "g2", "name": "Putiskys", "avatar": "🎯", "is_global": False},
    ]
    with (
        patch(
            "infrastructure.lambdas.telegram_webhook.invitation_callbacks._groups_for_invite_picker",
            return_value=groups,
        ),
    ):
        text, markup = handle_invitation_callback("admin-1", "inv:pick:3")

    labels = [
        btn["text"]
        for row in markup["inline_keyboard"]
        for btn in row
        if btn.get("callback_data", "").startswith("inv:grp:")
    ]
    assert len(labels) == 2
    assert any("Scaloneta" in t for t in labels)
    assert any("Putiskys" in t for t in labels)


def test_admin_invitar_ignores_group_context():
    """Admin en edición de un grupo sigue viendo teclado GLOBAL + elegir otro."""
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
        ) as mock_svc,
    ):
        mock_users.return_value.get_profile.return_value = {
            "group_context_group_id": "g-scaloneta",
            "is_admin": True,
        }
        mock_auth.return_value.is_admin_global.return_value = True
        mock_groups.return_value.get_owner_group_id.return_value = "g-scaloneta"
        mock_groups.return_value.get_group.return_value = {
            "group_id": "g-scaloneta",
            "name": "Scaloneta",
        }
        from infrastructure.lambdas.telegram_webhook.invitation_commands import (
            handle_invitation_command,
        )

        text, markup = handle_invitation_command("admin-1", "/invitar 3")

    mock_svc.return_value.create_invitation.assert_not_called()
    assert markup is not None
    callbacks = [
        btn.get("callback_data", "")
        for row in markup["inline_keyboard"]
        for btn in row
    ]
    assert any(c.startswith("inv:grp:GLOBAL") for c in callbacks)
    assert any(c == "inv:pick:3" for c in callbacks)
