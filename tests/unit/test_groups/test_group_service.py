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
