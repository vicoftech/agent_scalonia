"""tests/unit/test_invitations/test_invitation_tool.py — SC-10 tool gate."""
from unittest.mock import MagicMock, patch

from agent.tools.invitation_tool import invitation_tool
from src.services.auth_service import INACTIVE_USER_MESSAGE


def test_invitation_tool_blocks_unregistered():
    with patch("src.services.auth_service.UserDAO"):
        result = invitation_tool("list", user_id="unregistered")
    assert result == INACTIVE_USER_MESSAGE


def test_invitation_tool_create_when_active():
    mock_svc = MagicMock()
    mock_svc.create_invitation.return_value = {"message": "✅ Invitación creada"}

    with patch("src.services.auth_service.AuthService") as mock_auth:
        mock_auth.return_value.require_active_user_id.return_value = (True, "")
        with patch("src.services.invitation_service.InvitationService", return_value=mock_svc):
            result = invitation_tool("create", user_id="user-active-1", max_uses=2)

    assert "Invitación creada" in result
    mock_svc.create_invitation.assert_called_once_with("user-active-1", max_uses=2, group_id=None)
