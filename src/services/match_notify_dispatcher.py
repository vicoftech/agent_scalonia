"""Consumer SQS MATCH_RESULT → Telegram — SPEC-2026-031."""
from __future__ import annotations

import json
import logging
from typing import Any

from src.clients.telegram_client import get_bot_token, send_telegram_message
from src.dao.dynamo.user_dao import UserDAO

logger = logging.getLogger(__name__)

DISPATCH_SENT = "SENT"
DISPATCH_SKIPPED = "SKIPPED"
DISPATCH_SKIPPED_NO_CHAT = "SKIPPED_NO_CHAT"
DISPATCH_SKIPPED_DISABLED = "SKIPPED_DISABLED"
DISPATCH_SKIPPED_TYPE = "SKIPPED_TYPE"
DISPATCH_FAILED = "FAILED"


class MatchNotifyDispatcher:
    def __init__(
        self,
        *,
        users: UserDAO | None = None,
    ):
        self._users = users or UserDAO()

    def dispatch_payload(self, payload: dict[str, Any]) -> str:
        msg_type = payload.get("type")
        if msg_type != "MATCH_RESULT":
            logger.info("skip notify type=%s", msg_type)
            return DISPATCH_SKIPPED_TYPE

        user_id = payload.get("user_id")
        if not user_id:
            return DISPATCH_SKIPPED

        profile = self._users.get_profile(user_id) or {}
        if profile.get("notifications_enabled") is False:
            return DISPATCH_SKIPPED_DISABLED

        chat_id = profile.get("tg_chat_id")
        if chat_id is None:
            logger.info(
                "skip notify no tg_chat_id user=%s match=%s",
                str(user_id)[:8],
                str(payload.get("match_id", ""))[:8],
            )
            return DISPATCH_SKIPPED_NO_CHAT

        text = (payload.get("message") or "").strip()
        if not text:
            return DISPATCH_SKIPPED

        try:
            token = get_bot_token()
            send_telegram_message(int(chat_id), text, token)
            return DISPATCH_SENT
        except Exception:
            logger.exception(
                "Telegram send failed user=%s match=%s",
                str(user_id)[:8],
                str(payload.get("match_id", ""))[:8],
            )
            return DISPATCH_FAILED

    def dispatch_sqs_record(self, record: dict[str, Any]) -> str:
        body = record.get("body") or "{}"
        try:
            payload = json.loads(body) if isinstance(body, str) else body
        except json.JSONDecodeError:
            logger.exception("invalid SQS body messageId=%s", record.get("messageId"))
            return DISPATCH_FAILED

        try:
            return self.dispatch_payload(payload)
        except Exception:
            logger.exception(
                "MATCH_RESULT dispatch failed user=%s match=%s",
                str(payload.get("user_id", ""))[:8],
                str(payload.get("match_id", ""))[:8],
            )
            return DISPATCH_FAILED


def process_sqs_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Procesa batch SQS. Retorna batchItemFailures para reintentos parciales.
    """
    dispatcher = MatchNotifyDispatcher()
    sent = skipped = failed = 0
    batch_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        outcome = dispatcher.dispatch_sqs_record(record)
        if outcome == DISPATCH_SENT:
            sent += 1
        elif outcome == DISPATCH_FAILED:
            failed += 1
            mid = record.get("messageId")
            if mid:
                batch_failures.append({"itemIdentifier": mid})
        else:
            skipped += 1

    result = {
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
    }
    if batch_failures:
        result["batchItemFailures"] = batch_failures
    return result
