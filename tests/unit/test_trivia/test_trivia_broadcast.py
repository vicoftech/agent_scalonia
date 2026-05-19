"""Destinos de envío masivo de trivias."""
from unittest.mock import MagicMock

from src.dao.dynamo.user_dao import UserDAO


def test_list_telegram_delivery_targets_filters():
    table = MagicMock()
    dao = UserDAO()
    dao._table = table

    def fake_get(uid):
        if uid == "u1":
            return {"user_id": "u1", "notifications_enabled": True, "tg_chat_id": 111}
        if uid == "u2":
            return {"user_id": "u2", "notifications_enabled": False, "tg_chat_id": 222}
        if uid == "u3":
            return {"user_id": "u3", "notifications_enabled": True}
        return None

    dao.get_profile = fake_get  # type: ignore[method-assign]
    targets = dao.list_telegram_delivery_targets(["u1", "u2", "u3"])
    assert len(targets) == 1
    assert targets[0]["tg_chat_id"] == 111
