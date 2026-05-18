"""GSI-1 devuelve proyección parcial — el DAO debe hidratar PROFILE completo."""
from unittest.mock import MagicMock

from src.dao.dynamo.user_dao import UserDAO


def test_get_by_platform_hash_hydrates_status_from_profile():
    table = MagicMock()
    dao = UserDAO.__new__(UserDAO)
    dao._table = table

    table.query.return_value = {
        "Items": [
            {
                "user_id": "u1",
                "platform": "TELEGRAM",
                "platform_id_hash": "abc",
                "alias": "Admin",
            }
        ]
    }
    table.get_item.return_value = {
        "Item": {
            "user_id": "u1",
            "status": "ACTIVE",
            "is_admin": True,
        }
    }

    profile = dao.get_by_platform_hash("TELEGRAM", "abc")

    assert profile is not None
    assert profile["status"] == "ACTIVE"
    assert profile["is_admin"] is True
    table.get_item.assert_called_once()
