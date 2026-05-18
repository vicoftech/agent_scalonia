"""Lookup PLATFORM# consistente tras alta."""
from unittest.mock import MagicMock

from src.dao.dynamo.user_dao import UserDAO, _platform_lookup_key


def test_get_by_platform_hash_uses_lookup_before_gsi():
    table = MagicMock()
    dao = UserDAO.__new__(UserDAO)
    dao._table = table
    table.get_item.return_value = {"Item": {"user_id": "u1"}}
    dao.get_profile = MagicMock(return_value={"user_id": "u1", "status": "ACTIVE"})

    result = dao.get_by_platform_hash("TELEGRAM", "hashabc")

    assert result["status"] == "ACTIVE"
    table.get_item.assert_called_once_with(
        Key=_platform_lookup_key("TELEGRAM", "hashabc"),
        ConsistentRead=True,
    )
    table.query.assert_not_called()
