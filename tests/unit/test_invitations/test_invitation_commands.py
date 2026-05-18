"""Comandos /invitar en webhook."""
from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.invitation_commands import handle_invitation_command


def test_invitar_command_creates_invitation():
    mock_svc = MagicMock()
    mock_svc.create_invitation.return_value = {"message": "✅ link https://t.me/bot?start=abc"}

    with patch(
        "infrastructure.lambdas.telegram_webhook.invitation_commands.InvitationService",
        return_value=mock_svc,
    ):
        reply = handle_invitation_command("user-1", "/invitar 2")

    assert "link" in reply
    mock_svc.create_invitation.assert_called_once_with("user-1", max_uses=2)


def test_non_command_returns_none():
    assert handle_invitation_command("user-1", "hola") is None
