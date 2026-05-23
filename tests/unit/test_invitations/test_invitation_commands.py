"""Comandos /invitar en webhook."""
from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.invitation_commands import handle_invitation_command


def test_invitar_command_shows_destination_keyboard():
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
    ):
        mock_users.return_value.get_profile.return_value = {}
        mock_auth.return_value.is_admin_global.return_value = True
        mock_groups.return_value.get_owner_group_id.return_value = None
        reply = handle_invitation_command("user-1", "/invitar 2")

    text, markup = reply
    assert "GLOBAL" in text or "grupo destino" in text.lower()
    assert markup is not None
    assert any(
        "inv:grp" in btn.get("callback_data", "")
        for row in markup.get("inline_keyboard", [])
        for btn in row
    )


def test_unirme_accepts_existing_user():
    with patch(
        "infrastructure.lambdas.telegram_webhook.invitation_commands.InvitationService"
    ) as mock_svc:
        mock_svc.return_value.accept_invitation_for_existing_user.return_value = {
            "group_name": "Los Pibes",
            "joined_new": True,
        }
        text, markup = handle_invitation_command("user-1", "/unirme inv12345")
    assert markup is None
    assert "Los Pibes" in text


def test_invitar_stale_group_context_admin_shows_keyboard():
    """Tras purge, contexto a grupo borrado no debe devolver '0 slots'."""
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
            "group_context_group_id": "grp-deleted",
        }
        mock_auth.return_value.is_admin_global.return_value = True
        mock_groups.return_value.get_group.return_value = None
        mock_groups.return_value.get_owner_group_id.return_value = None
        mock_groups.return_value.list_private_groups_for_invite.return_value = [
            {"group_id": "g1", "name": "Putiskys", "avatar": "🎯"},
        ]
        text, markup = handle_invitation_command("admin-1", "/invitar 3")

    assert "0 slot" not in text.lower()
    assert markup is not None
    mock_svc.return_value.create_invitation.assert_not_called()
    mock_users.return_value.update_profile.assert_called_once_with(
        "admin-1", group_context_group_id=None
    )


def test_non_command_returns_none():
    assert handle_invitation_command("user-1", "hola") is None
