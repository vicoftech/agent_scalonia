"""Registro global CONFIG#TRIVIA / USED_QUESTION_FPS."""
from unittest.mock import MagicMock

from src.dao.dynamo.trivia_dao import REGISTRY_PK, REGISTRY_SK, TriviaDAO


def test_register_and_get_fingerprints():
    store: dict = {}

    def get_item(Key, **kwargs):
        k = (Key["partition_key"], Key["sort_key"])
        item = store.get(k)
        return {"Item": item} if item else {}

    def put_item(Item, **kwargs):
        store[(Item["partition_key"], Item["sort_key"])] = dict(Item)

    table = MagicMock()
    table.get_item.side_effect = get_item
    table.put_item.side_effect = put_item

    dao = TriviaDAO()
    dao._table = table

    assert dao.get_used_question_fingerprints() == set()
    dao.register_question_fingerprint("abc")
    dao.register_question_fingerprint("abc")
    dao.register_question_fingerprint("def")

    assert dao.get_used_question_fingerprints() == {"abc", "def"}
    reg = store[(REGISTRY_PK, REGISTRY_SK)]
    assert reg["fingerprints"] == ["abc", "def"]
