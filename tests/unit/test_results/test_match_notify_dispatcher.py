"""MATCH_RESULT SQS → Telegram dispatcher."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.services.match_notify_dispatcher import (
    DISPATCH_SENT,
    DISPATCH_SKIPPED_DISABLED,
    DISPATCH_SKIPPED_NO_CHAT,
    MatchNotifyDispatcher,
    process_sqs_event,
)


def _payload(**kwargs):
    base = {
        "type": "MATCH_RESULT",
        "user_id": "u1",
        "match_id": "m1",
        "group_id": "g1",
        "message": "🏁 RESULTADO FINAL\n\nARG 2-0 ALG",
    }
    base.update(kwargs)
    return base


def test_dispatch_sent():
    users = MagicMock()
    users.get_profile.return_value = {
        "user_id": "u1",
        "notifications_enabled": True,
        "tg_chat_id": 999,
    }
    groups = MagicMock()
    groups.get_group.return_value = {"name": "Los Pibes"}

    with patch("src.services.match_notify_dispatcher.get_bot_token", return_value="tok"):
        with patch("src.services.match_notify_dispatcher.send_telegram_message") as send:
            out = MatchNotifyDispatcher(users=users, groups=groups).dispatch_payload(
                _payload()
            )

    assert out == DISPATCH_SENT
    send.assert_called_once()
    assert send.call_args[0][0] == 999
    assert "Los Pibes" in send.call_args[0][1]


def test_skip_no_chat():
    users = MagicMock()
    users.get_profile.return_value = {
        "notifications_enabled": True,
        "tg_chat_id": None,
    }
    with patch("src.services.match_notify_dispatcher.send_telegram_message") as send:
        out = MatchNotifyDispatcher(users=users).dispatch_payload(_payload())
    assert out == DISPATCH_SKIPPED_NO_CHAT
    send.assert_not_called()


def test_skip_notifications_disabled():
    users = MagicMock()
    users.get_profile.return_value = {
        "notifications_enabled": False,
        "tg_chat_id": 111,
    }
    with patch("src.services.match_notify_dispatcher.send_telegram_message") as send:
        out = MatchNotifyDispatcher(users=users).dispatch_payload(_payload())
    assert out == DISPATCH_SKIPPED_DISABLED
    send.assert_not_called()


def test_process_sqs_event_batch():
    users = MagicMock()
    users.get_profile.return_value = {
        "notifications_enabled": True,
        "tg_chat_id": 42,
    }
    groups = MagicMock()
    groups.get_group.return_value = {}
    event = {
        "Records": [
            {"messageId": "1", "body": json.dumps(_payload())},
            {"messageId": "2", "body": json.dumps({"type": "OTHER"})},
        ]
    }
    with patch(
        "src.services.match_notify_dispatcher.UserDAO",
        return_value=users,
    ):
        with patch(
            "src.services.match_notify_dispatcher.GroupDAO",
            return_value=groups,
        ):
            with patch(
                "src.services.match_notify_dispatcher.get_bot_token",
                return_value="t",
            ):
                with patch(
                    "src.services.match_notify_dispatcher.send_telegram_message"
                ):
                    result = process_sqs_event(event)

    assert result["sent"] == 1
    assert result["skipped"] == 1


def test_telegram_client_send_mockable():
    from src.clients import telegram_client

    calls: list[tuple[int, str]] = []

    def fake_send(cid, text, token):
        calls.append((cid, text))

    telegram_client.set_send_fn(fake_send)
    telegram_client.set_token_provider(lambda: "fake-token")
    try:
        telegram_client.send_telegram_message(1, "hola", "fake-token")
    finally:
        telegram_client.set_send_fn(None)
        telegram_client.set_token_provider(None)

    assert calls == [(1, "hola")]
