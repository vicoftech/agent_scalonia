"""Colas SQS scoring y notificaciones — SPEC-2026-031."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.dao.dynamo.table import get_session

logger = logging.getLogger(__name__)


def _sqs_client():
    return get_session().client("sqs")


def lookup_queue_url(queue_name: str) -> str | None:
    """Resuelve URL de cola por nombre (scripts locales con --profile)."""
    try:
        resp = _sqs_client().get_queue_url(QueueName=queue_name)
        return resp.get("QueueUrl")
    except Exception:
        logger.debug("Queue not found or no access: %s", queue_name)
        return None


def ensure_queue_urls(*, env: str) -> dict[str, str | None]:
    """
    Completa NOTIFICATION_QUEUE_URL y SCORING_QUEUE_URL desde nombres estándar.
    prode-match-notify-{env} / prode-scoring-{env}
    """
    found: dict[str, str | None] = {}
    notify_name = f"prode-match-notify-{env}"
    scoring_name = f"prode-scoring-{env}"

    if not os.environ.get("NOTIFICATION_QUEUE_URL", "").strip():
        url = lookup_queue_url(notify_name)
        if url:
            os.environ["NOTIFICATION_QUEUE_URL"] = url
            logger.info("NOTIFICATION_QUEUE_URL ← %s", notify_name)
        found["notification"] = url
    else:
        found["notification"] = os.environ["NOTIFICATION_QUEUE_URL"]

    if not os.environ.get("SCORING_QUEUE_URL", "").strip():
        url = lookup_queue_url(scoring_name)
        if url:
            os.environ["SCORING_QUEUE_URL"] = url
            logger.info("SCORING_QUEUE_URL ← %s", scoring_name)
        found["scoring"] = url
    else:
        found["scoring"] = os.environ.get("SCORING_QUEUE_URL")

    return found


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
        _sqs_client().send_message(
            QueueUrl=url,
            MessageBody=json.dumps(payload, default=str),
        )
        return True
    except Exception:
        logger.exception("Scoring SQS enqueue failed match=%s", match_id[:8])
        return False


def enqueue_lifecycle_notification(
    *,
    user_id: str,
    match_id: str,
    message: str,
    msg_type: str,
    group_id: str | None = None,
) -> bool:
    """MATCH_REMINDER | MATCH_VEDA — misma cola que resultados."""
    url = os.environ.get("NOTIFICATION_QUEUE_URL", "").strip()
    if not url:
        return False
    payload = {
        "type": msg_type,
        "user_id": user_id,
        "match_id": match_id,
        "message": message,
    }
    if group_id:
        payload["group_id"] = group_id
    try:
        _sqs_client().send_message(
            QueueUrl=url,
            MessageBody=json.dumps(payload, default=str),
        )
        return True
    except Exception:
        logger.exception(
            "Lifecycle notify SQS failed user=%s match=%s type=%s",
            user_id[:8],
            match_id[:8],
            msg_type,
        )
        return False


def enqueue_match_result_notification(
    *,
    user_id: str,
    match_id: str,
    group_id: str,
    message: str,
    match_info: dict[str, Any],
    result: dict[str, Any],
    group_ids: list[str] | None = None,
) -> bool:
    url = os.environ.get("NOTIFICATION_QUEUE_URL", "").strip()
    if not url:
        logger.warning(
            "NOTIFICATION_QUEUE_URL unset; no se encoló notify user=%s match=%s",
            user_id[:8],
            match_id[:8],
        )
        return False
    payload = {
        "type": "MATCH_RESULT",
        "user_id": user_id,
        "match_id": match_id,
        "group_id": group_id,
        "group_ids": group_ids or [group_id],
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
        _sqs_client().send_message(
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
