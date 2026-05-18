"""tests/unit/test_invitations/test_start_handler.py — SC-08 /start."""
from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.start_handler import handle_start_command
from src.services.auth_service import INACTIVE_USER_MESSAGE


def test_start_existing_active_user_ignores_invite():
    with patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users:
        mock_users.return_value.get_by_platform_hash.return_value = {
            "user_id": "u1",
            "alias": "Golazo",
            "status": "ACTIVE",
        }
        reply = handle_start_command(12345, "/start inviteIgnored")
    assert "Golazo" in reply
    assert "Ya estás registrado" in reply


def test_start_existing_banned_user():
    with patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users:
        mock_users.return_value.get_by_platform_hash.return_value = {
            "user_id": "u1",
            "alias": "X",
            "status": "BANNED",
        }
        reply = handle_start_command(12345, "/start")
    assert reply == INACTIVE_USER_MESSAGE
