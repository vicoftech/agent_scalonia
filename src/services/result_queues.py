"""Colas SQS scoring y notificaciones — SPEC-2026-031."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)


def enqueue_scoring(match_id: str, result: dict[str, Any]) -> bool:
    url = os.environ.get("SCORING_QUEUE_URL", "").strip()
    if not url:
        logger.info(
            "SCORING_QUEUE_URL unset; skip scoring enqueue match=%s",
            match_id[:8],
        )
        return False
    payload = {
        "event_type": "FINISH_MATCH",
        "match_id": match_id,
        "result": result,
    }
    try:
        boto3.client("sqs").send_message(
            QueueUrl=url,
            MessageBody=json.dumps(payload, default=str),
        )
        return True
    except Exception:
        logger.exception("Scoring SQS enqueue failed match=%s", match_id[:8])
        return False


def enqueue_match_result_notification(
    *,
    user_id: str,
    match_id: str,
    group_id: str,
    message: str,
    match_info: dict[str, Any],
    result: dict[str, Any],
) -> bool:
    url = os.environ.get("NOTIFICATION_QUEUE_URL", "").strip()
    if not url:
        logger.debug(
            "NOTIFICATION_QUEUE_URL unset; skip notify user=%s match=%s",
            user_id[:8],
            match_id[:8],
        )
        return False
    payload = {
        "type": "MATCH_RESULT",
        "user_id": user_id,
        "match_id": match_id,
        "group_id": group_id,
        "message": message,
        "result": result,
        "match_info": {
            k: match_info.get(k)
            for k in (
                "match_id",
                "match_number",
                "home_team",
                "away_team",
                "phase",
                "group_letter",
                "venue",
                "city",
            )
        },
    }
    try:
        boto3.client("sqs").send_message(
            QueueUrl=url,
            MessageBody=json.dumps(payload, default=str),
        )
        return True
    except Exception:
        logger.exception(
            "Notification SQS failed user=%s match=%s",
            user_id[:8],
            match_id[:8],
        )
        return False
