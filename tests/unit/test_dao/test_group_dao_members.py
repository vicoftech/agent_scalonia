"""GroupDAO.list_member_user_ids — evita duplicados por GSI-3."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.dao.dynamo.group_dao import GroupDAO


def test_list_member_user_ids_uses_pk_not_gsi():
    table = MagicMock()
    table.query.return_value = {
        "Items": [
            {
                "partition_key": "GROUP#g1",
                "sort_key": "MEMBER#u1",
                "user_id": "u1",
            },
            {
                "partition_key": "GROUP#g1",
                "sort_key": "MEMBER#u2",
                "user_id": "u2",
            },
        ],
    }
    dao = GroupDAO.__new__(GroupDAO)
    dao._table = table

    ids = dao.list_member_user_ids("g1")

    assert ids == ["u1", "u2"]
    kwargs = table.query.call_args.kwargs
    assert "IndexName" not in kwargs
    assert kwargs["KeyConditionExpression"] is not None


def test_list_member_user_ids_deduplicates_legacy_rows():
    table = MagicMock()
    table.query.return_value = {
        "Items": [
            {"sort_key": "MEMBER#u1", "user_id": "u1"},
            {"sort_key": "MEMBER#u1", "user_id": "u1"},
        ],
    }
    dao = GroupDAO.__new__(GroupDAO)
    dao._table = table

    assert dao.list_member_user_ids("g1") == ["u1"]
