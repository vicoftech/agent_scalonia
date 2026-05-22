"""SPEC-029 — /invitar respeta grupo en edición."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.invitation_commands import (
    handle_invitation_command,
)


def test_invitar_uses_group_context_without_picker():
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
            "group_context_group_id": "grp-abc",
        }
        mock_auth.return_value.is_admin_global.return_value = False
        mock_auth.return_value.check_can_invite.return_value = (True, "ok")
        mock_auth.return_value.slots_available.return_value = 5
        mock_groups.return_value.get_group.return_value = {
            "group_id": "grp-abc",
            "name": "Los Pibes",
        }
        mock_groups.return_value.get_owner_group_id.return_value = "grp-abc"
        mock_svc.return_value.create_invitation.return_value = {
            "message": "✅ Invitación creada\n\nlink",
        }

        text, markup = handle_invitation_command("user-1", "/invitar 3")

    assert "Invitación creada" in text
    assert markup is None
    mock_svc.return_value.create_invitation.assert_called_once_with(
        "user-1", max_uses=3, group_id="grp-abc"
    )
