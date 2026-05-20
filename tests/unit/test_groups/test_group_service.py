"""SPEC-026 — group_service unit tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.group_service import GroupService


def test_validate_group_name_ok():
    ok, name = GroupService().validate_group_name("Los Pibes")
    assert ok is True
    assert name == "Los Pibes"


def test_validate_group_name_too_short():
    ok, msg = GroupService().validate_group_name("A")
    assert ok is False


@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_can_create_free_user_without_group(mock_user, mock_group):
    mock_group.return_value.get_owner_group_id.return_value = None
    mock_user.return_value.get_profile.return_value = {"is_admin": False}
    svc = GroupService(group_dao=mock_group.return_value, user_dao=mock_user.return_value)
    ok, _ = svc.can_create_group("u1")
    assert ok is True


@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_cannot_create_second_group_free(mock_user, mock_group):
    mock_group.return_value.get_owner_group_id.return_value = "g1"
    mock_group.return_value.get_group.return_value = {"name": "Mi Grupo"}
    mock_user.return_value.get_profile.return_value = {"is_admin": False}
    svc = GroupService(group_dao=mock_group.return_value, user_dao=mock_user.return_value)
    ok, name = svc.can_create_group("u1")
    assert ok is False
    assert name == "Mi Grupo"


@patch("src.services.group_service.UserDAO")
def test_pending_awaiting_avatar_lets_slash_commands_through(mock_user):
    mock_user.return_value.get_profile.return_value = {
        "group_create_step": "awaiting_avatar",
        "group_draft_name": "Los Pibes",
    }
    svc = GroupService(user_dao=mock_user.return_value)
    assert svc.handle_pending_with_markup("u1", "/grupos") is None


@patch("src.services.group_service.UserDAO")
def test_pending_awaiting_avatar_hints_on_plain_text(mock_user):
    mock_user.return_value.get_profile.return_value = {
        "group_create_step": "awaiting_avatar",
        "group_draft_name": "Los Pibes",
    }
    svc = GroupService(user_dao=mock_user.return_value)
    text, markup = svc.handle_pending_with_markup("u1", "hola")
    assert "avatar" in text.lower()
    assert markup is not None


@patch("src.services.group_service.UserDAO")
def test_pending_cancel_clears_state(mock_user):
    mock_user.return_value.get_profile.return_value = {
        "group_create_step": "awaiting_avatar",
    }
    svc = GroupService(user_dao=mock_user.return_value)
    msg, _ = svc.handle_pending_with_markup("u1", "/cancel")
    assert "cancelad" in msg.lower()
    mock_user.return_value.update_profile.assert_called()


@patch("src.services.group_service.GroupDAO")
@patch("src.services.group_service.UserDAO")
def test_add_member_plain_alias_after_menu(mock_user, mock_group):
    mock_user.return_value.get_profile.return_value = {
        "group_add_member_group_id": "g1",
        "group_context_group_id": "g1",
    }
    mock_group.return_value.get_group.return_value = {
        "group_id": "g1",
        "name": "Los Pibes",
        "owner_id": "u1",
        "max_members": 10,
        "is_global": False,
        "status": "ACTIVE",
    }
    mock_group.return_value.is_member.return_value = False
    mock_group.return_value.count_members.return_value = 2
    target = {"user_id": "u2", "alias": "vic", "status": "ACTIVE"}
    with patch.object(GroupService, "resolve_alias_user", return_value=target):
        with patch.object(GroupService, "add_member_by_alias", return_value=(True, "✅ vic sumado")):
            with patch.object(
                GroupService,
                "format_edit_menu",
                return_value=('Editando "Los Pibes"', {"inline_keyboard": []}),
            ):
                svc = GroupService(
                    group_dao=mock_group.return_value,
                    user_dao=mock_user.return_value,
                )
                svc._auth = MagicMock()
                svc._auth.is_admin_global.return_value = True
                text, markup = svc._handle_add_member_text("u1", "vic")
    assert "vic sumado" in text
    assert markup is not None


@patch("src.services.group_service.GroupDAO")
def test_delete_global_forbidden(mock_group):
    mock_group.return_value.get_group.return_value = {
        "group_id": "GLOBAL",
        "is_global": True,
        "name": "General",
    }
    svc = GroupService(group_dao=mock_group.return_value)
    ok, msg = svc.delete_group("admin", "GLOBAL")
    assert ok is False
    assert "GLOBAL" in msg
