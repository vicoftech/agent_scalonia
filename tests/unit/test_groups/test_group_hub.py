"""SPEC-2026-047 — group hub unit tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.group_service import GroupService


@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_is_group_name_unique_for_owner(mock_user, mock_group):
    mock_group.return_value.list_owned_group_ids.return_value = ["g1", "g2"]
    mock_group.return_value.get_group.side_effect = lambda gid: {
        "g1": {"name": "Scaloneta", "status": "ACTIVE", "is_global": False},
        "g2": {"name": "Los Pibes", "status": "ACTIVE", "is_global": False},
    }.get(gid)
    svc = GroupService(group_dao=mock_group.return_value, user_dao=mock_user.return_value)
    assert svc.is_group_name_unique_for_owner("u1", "Trabajo") is True
    assert svc.is_group_name_unique_for_owner("u1", "scaloneta") is False
    assert (
        svc.is_group_name_unique_for_owner("u1", "Scaloneta", exclude_group_id="g1")
        is True
    )


@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_list_hub_groups_excludes_global(mock_user, mock_group):
    mock_group.return_value.list_group_ids_for_user.return_value = [
        "global-id",
        "g-private",
    ]
    mock_group.return_value.get_group.side_effect = lambda gid: {
        "global-id": {"name": "Global", "is_global": True, "status": "ACTIVE"},
        "g-private": {
            "name": "Mi Grupo",
            "owner_id": "u1",
            "status": "ACTIVE",
            "avatar": "⚽",
            "max_members": 5,
        },
    }.get(gid)
    mock_group.return_value.count_members.return_value = 3
    svc = GroupService(group_dao=mock_group.return_value, user_dao=mock_user.return_value)
    groups = svc.list_hub_groups("u1")
    assert len(groups) == 1
    assert groups[0]["role"] == "owner"
    assert groups[0]["name"] == "Mi Grupo"


@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_submit_hub_create_name_duplicate(mock_user, mock_group):
    mock_group.return_value.list_owned_group_ids.return_value = ["g1"]
    mock_group.return_value.get_group.return_value = {
        "name": "Scaloneta",
        "status": "ACTIVE",
    }
    svc = GroupService(group_dao=mock_group.return_value, user_dao=mock_user.return_value)
    text, kb = svc.submit_hub_create_name("u1", "Scaloneta")
    assert "Ya tenés" in text
    assert kb is None


@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_start_hub_create_paywall(mock_user, mock_group):
    mock_group.return_value.list_owned_group_ids.return_value = ["g1"]
    mock_group.return_value.get_group.return_value = {"name": "Existente"}
    mock_user.return_value.get_profile.return_value = {"is_admin": False}
    svc = GroupService(group_dao=mock_group.return_value, user_dao=mock_user.return_value)
    text, kb = svc.start_hub_create("u1")
    assert "Ampliar" in text or "máximo" in text
    assert kb is not None
    assert kb["inline_keyboard"][0][0]["callback_data"] == "gup:start"


@patch("src.services.group_service.AuthService")
@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_start_hub_add_member_paywall_at_capacity(mock_auth, mock_user, mock_group):
    mock_auth.return_value.slots_available.return_value = 0
    mock_auth.return_value.is_admin_global.return_value = False
    mock_group.return_value.get_group.return_value = {
        "name": "Lleno",
        "max_members": 5,
        "owner_id": "u1",
    }
    svc = GroupService(
        group_dao=mock_group.return_value,
        user_dao=mock_user.return_value,
        auth=mock_auth.return_value,
    )
    mock_auth.return_value.is_group_owner.return_value = True
    text, kb = svc.start_hub_add_member("u1", "g1")
    assert "cupo" in text.lower()
    assert kb["inline_keyboard"][0][0]["callback_data"].startswith("gup:quickmem:")


@patch("src.services.auth_service.AuthService")
@patch("src.services.group_upgrade_service.UserDAO")
@patch("src.services.group_upgrade_service.GroupDAO")
def test_admin_grant_group_slots_notifies(mock_groups, mock_users, mock_auth):
    from src.services.group_upgrade_service import GroupUpgradeService

    mock_auth.return_value.is_admin_global.return_value = True
    mock_users.return_value.resolve_alias.return_value = {"user_id": "u1"}
    mock_users.return_value.get_profile.return_value = {"tg_chat_id": 123}
    notify = MagicMock()
    svc = GroupUpgradeService(
        users=mock_users.return_value,
        groups=mock_groups.return_value,
        telegram_notify=notify,
    )
    with patch.object(svc, "_notify", return_value=True) as mock_notify:
        msg = svc.admin_grant_group_slots("admin", "vic", 1)
    assert "✅" in msg
    mock_notify.assert_called_once()
    assert "Crear grupo nuevo" in mock_notify.call_args[0][2]


@patch("src.services.group_upgrade_service.UserDAO")
@patch("src.services.group_upgrade_service.GroupDAO")
def test_start_member_pack_upgrade(mock_groups, mock_users):
    from src.services.group_upgrade_service import GroupUpgradeService

    mock_groups.return_value.get_group.return_value = {
        "name": "Scaloneta",
        "owner_id": "u1",
        "max_members": 5,
    }
    mock_users.return_value.get_profile.return_value = {}
    svc = GroupUpgradeService(users=mock_users.return_value, groups=mock_groups.return_value)
    with patch.object(svc, "_set_quote", return_value=("quote", {})) as mock_quote:
        svc.start_member_pack_upgrade("u1", "g1")
    mock_quote.assert_called_once()
    alloc = mock_quote.call_args.kwargs["allocation"]
    assert alloc[0]["type"] == "MEMBER_PACK"
    assert alloc[0]["packs"] == 1
