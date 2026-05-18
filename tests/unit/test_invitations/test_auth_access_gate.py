"""Gate usuario ACTIVE — SPEC-020 SC-10."""
from unittest.mock import MagicMock

from src.services.auth_service import INACTIVE_USER_MESSAGE, AuthService


def test_resolve_telegram_access_missing_profile():
    users = MagicMock()
    users.get_by_platform_hash.return_value = None
    auth = AuthService(user_dao=users)

    user_id, msg = auth.resolve_telegram_access("abc123")

    assert user_id is None
    assert msg == INACTIVE_USER_MESSAGE


def test_resolve_telegram_access_banned():
    users = MagicMock()
    users.get_by_platform_hash.return_value = {
        "user_id": "u1",
        "status": "BANNED",
    }
    auth = AuthService(user_dao=users)

    user_id, msg = auth.resolve_telegram_access("abc123")

    assert user_id is None
    assert msg == INACTIVE_USER_MESSAGE


def test_resolve_telegram_access_active():
    users = MagicMock()
    users.get_by_platform_hash.return_value = {
        "user_id": "u1",
        "status": "ACTIVE",
    }
    auth = AuthService(user_dao=users)

    user_id, msg = auth.resolve_telegram_access("abc123")

    assert user_id == "u1"
    assert msg is None


def test_require_active_user_id_unregistered():
    auth = AuthService(user_dao=MagicMock())
    ok, msg = auth.require_active_user_id("unregistered")
    assert not ok
    assert msg == INACTIVE_USER_MESSAGE
