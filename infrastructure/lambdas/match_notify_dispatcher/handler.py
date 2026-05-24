"""
Lambda: consume prode-match-notify-{env} → sendMessage Telegram.

SPEC-2026-031 TASK-031-005
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    os.environ.setdefault(
        "DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev")
    )

    from src.services.match_notify_dispatcher import process_sqs_event

    result = process_sqs_event(event)
    logger.info(
        "match_notify batch sent=%s skipped=%s failed=%s",
        result.get("sent"),
        result.get("skipped"),
        result.get("failed"),
    )
    # SQS partial batch response (Lambda event source mapping)
    if result.get("batchItemFailures"):
        return {"batchItemFailures": result["batchItemFailures"]}
    return result
