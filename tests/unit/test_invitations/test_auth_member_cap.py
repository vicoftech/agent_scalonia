"""Reglas de cupos: admin sin tope, owner con max_members."""
from unittest.mock import MagicMock

from src.services.auth_service import AuthService


def test_admin_bypasses_member_cap_slots():
    users = MagicMock()
    users.get_profile.return_value = {"is_admin": True}
    groups = MagicMock()
    groups.get_group.return_value = {
        "group_id": "grp-1",
        "max_members": 5,
    }
    groups.count_members.return_value = 5

    auth = AuthService(user_dao=users, group_dao=groups)
    assert auth.bypasses_member_cap("admin-1") is True
    assert auth.slots_available("grp-1", actor_user_id="admin-1") is None


def test_owner_sees_zero_slots_when_full():
    users = MagicMock()
    users.get_profile.return_value = {"is_admin": False}
    groups = MagicMock()
    groups.get_group.return_value = {
        "group_id": "grp-1",
        "max_members": 5,
    }
    groups.count_members.return_value = 5

    auth = AuthService(user_dao=users, group_dao=groups)
    assert auth.slots_available("grp-1", actor_user_id="owner-1") == 0


def test_global_group_always_unlimited_for_owner():
    users = MagicMock()
    users.get_profile.return_value = {"is_admin": False}
    groups = MagicMock()
    groups.get_group.return_value = {
        "group_id": "GLOBAL",
        "is_global": True,
        "max_members": None,
    }

    auth = AuthService(user_dao=users, group_dao=groups)
    assert auth.slots_available("GLOBAL", actor_user_id="owner-1") is None
