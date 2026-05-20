"""Regresión update_profile con campos None (SPEC-026)."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.dao.dynamo.user_dao import UserDAO


def test_update_profile_remove_none_fields():
    table = MagicMock()
    dao = UserDAO.__new__(UserDAO)
    dao._table = table

    dao.update_profile(
        "u1",
        group_create_step="awaiting_name",
        group_draft_name=None,
    )

    call = table.update_item.call_args.kwargs
    expr = call["UpdateExpression"]
    assert expr.count("REMOVE") == 1
    assert "group_draft_name" in str(call.get("ExpressionAttributeNames", {}))
    assert "group_create_step" in str(call.get("ExpressionAttributeNames", {}))


def test_update_profile_multiple_remove_single_clause():
    """finish_create_group limpia group_create_step y group_draft_name a la vez."""
    table = MagicMock()
    dao = UserDAO.__new__(UserDAO)
    dao._table = table

    dao.update_profile(
        "u1",
        groups_owned=1,
        group_create_step=None,
        group_draft_name=None,
    )

    expr = table.update_item.call_args.kwargs["UpdateExpression"]
    assert expr.count("REMOVE") == 1
    assert "#f" in expr
