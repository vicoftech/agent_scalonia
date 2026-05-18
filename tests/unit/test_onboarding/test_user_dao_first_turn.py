"""Flag pending_first_agent_turn — ISSUE-025."""
from unittest.mock import MagicMock

from src.dao.dynamo.user_dao import UserDAO


def test_consume_pending_when_false():
    dao = UserDAO()
    dao._table = MagicMock()
    dao.get_profile = MagicMock(return_value={"pending_first_agent_turn": False})
    assert dao.consume_pending_first_agent_turn("u1") is False
    dao._table.update_item.assert_not_called()


def test_consume_pending_when_true():
    dao = UserDAO()
    dao._table = MagicMock()
    dao.get_profile = MagicMock(return_value={"pending_first_agent_turn": True})
    assert dao.consume_pending_first_agent_turn("u1") is True
    dao._table.update_item.assert_called_once()
    assert "REMOVE pending_first_agent_turn" in dao._table.update_item.call_args.kwargs[
        "UpdateExpression"
    ]


def test_set_pending_first_agent_turn():
    dao = UserDAO()
    dao._table = MagicMock()
    dao.set_pending_first_agent_turn("u1")
    dao._table.update_item.assert_called_once()
    assert dao._table.update_item.call_args.kwargs["ExpressionAttributeValues"][":p"] is True
