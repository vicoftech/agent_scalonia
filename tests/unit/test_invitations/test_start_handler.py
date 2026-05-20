"""tests/unit/test_invitations/test_start_handler.py — SC-08 /start + SPEC-029."""
from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.start_handler import handle_start_command
from src.services.auth_service import INACTIVE_USER_MESSAGE


def test_start_existing_active_user_accepts_invite():
    with (
        patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users,
        patch("infrastructure.lambdas.telegram_webhook.start_handler.GroupDAO"),
        patch("infrastructure.lambdas.telegram_webhook.start_handler.InvitationDAO"),
        patch(
            "infrastructure.lambdas.telegram_webhook.start_handler.InvitationService"
        ) as mock_inv_svc,
    ):
        mock_users.return_value.get_by_platform_hash.return_value = {
            "user_id": "u1",
            "alias": "Golazo",
            "status": "ACTIVE",
            "onboarding_stage": "M3_COMPLETE",
        }
        mock_inv_svc.return_value.accept_invitation_for_existing_user.return_value = {
            "group_name": "Los Pibes",
            "joined_new": True,
        }
        msg, _ = handle_start_command(12345, "/start inviteIgnored")
    assert "Los Pibes" in msg
    mock_inv_svc.return_value.accept_invitation_for_existing_user.assert_called_once_with(
        "u1", "inviteIgnored"
    )


def test_start_existing_active_user_without_invite():
    with patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users:
        mock_users.return_value.get_by_platform_hash.return_value = {
            "user_id": "u1",
            "alias": "Golazo",
            "status": "ACTIVE",
            "onboarding_stage": "M3_COMPLETE",
        }
        msg, _ = handle_start_command(12345, "/start")
    assert "Golazo" in msg
    assert "Ya estás registrado" in msg


def test_start_existing_banned_user():
    with patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users:
        mock_users.return_value.get_by_platform_hash.return_value = {
            "user_id": "u1",
            "alias": "X",
            "status": "BANNED",
        }
        msg, markup = handle_start_command(12345, "/start")
    assert msg == INACTIVE_USER_MESSAGE
    assert markup is None


def test_start_without_invite_does_not_register():
    with patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users:
        mock_users.return_value.get_by_platform_hash.return_value = None
        mock_users.return_value.create_telegram_user = MagicMock()
        msg, _ = handle_start_command(99999, "/start")
    assert "invitación" in msg.lower()
    mock_users.return_value.create_telegram_user.assert_not_called()


def test_start_with_valid_invite_sets_first_agent_turn_pending():
    with (
        patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users,
        patch("infrastructure.lambdas.telegram_webhook.start_handler.GroupDAO"),
        patch("infrastructure.lambdas.telegram_webhook.start_handler.InvitationDAO") as mock_inv_dao,
        patch(
            "infrastructure.lambdas.telegram_webhook.start_handler.InvitationService"
        ) as mock_inv_svc,
    ):
        mock_users.return_value.get_by_platform_hash.return_value = None
        mock_inv_dao.return_value.get.return_value = {
            "status": "ACTIVE",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        mock_inv_svc.return_value.validate_and_use.return_value = {
            "group_name": "Los Pibes",
        }
        msg, _ = handle_start_command(12345, "/start abc12345")
    assert "Bienvenido al Prode Mundial 2026" in msg
    mock_users.return_value.set_pending_first_agent_turn.assert_called_once()
