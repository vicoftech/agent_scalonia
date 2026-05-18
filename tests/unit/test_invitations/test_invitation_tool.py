"""tests/unit/test_invitations/test_invitation_tool.py — SC-10 tool gate."""
from unittest.mock import MagicMock, patch

from agent.tools.invitation_tool import make_invitation_tool
from src.services.auth_service import INACTIVE_USER_MESSAGE


def test_invitation_tool_blocks_unregistered():
    tool = make_invitation_tool("unregistered")
    result = tool("list")
    assert result == INACTIVE_USER_MESSAGE


def test_invitation_tool_create_when_active():
    mock_svc = MagicMock()
    mock_svc.create_invitation.return_value = {"message": "✅ Invitación creada"}
    tool = make_invitation_tool("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    with patch("src.services.invitation_service.InvitationService", return_value=mock_svc):
        result = tool("create", max_uses=2)

    assert "Invitación creada" in result
    mock_svc.create_invitation.assert_called_once_with(
        "a1b2c3d4-e5f6-7890-abcd-ef1234567890", max_uses=2, group_id=None
    )
