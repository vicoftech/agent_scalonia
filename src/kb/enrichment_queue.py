"""Encola enriquecimiento KB (SQS) o ejecuta en background si no hay cola."""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Callable

import boto3

from src.kb.kb_enrichment_service import DataType, KBEnrichmentService

logger = logging.getLogger(__name__)

_dispatch_fn: Callable[[str, str, str], None] | None = None


def _default_dispatch(query: str, web_result: str, data_type_value: str) -> None:
    data_type = DataType(data_type_value)
    KBEnrichmentService().enrich_from_web(query, web_result, data_type)


def enqueue_enrichment(query: str, web_result: str, data_type: DataType) -> None:
    """Fire-and-forget: no bloquea al agente."""
    payload = {
        "query": query,
        "web_result": web_result,
        "data_type": data_type.value,
    }
    queue_url = os.environ.get("KB_ENRICHMENT_QUEUE_URL", "").strip()
    if queue_url:
        try:
            boto3.client("sqs").send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(payload, ensure_ascii=False),
            )
            logger.info("enrichment queued type=%s", data_type.value)
            return
        except Exception:
            logger.exception("SQS enqueue failed; fallback thread")

    fn = _dispatch_fn or _default_dispatch
    threading.Thread(
        target=fn,
        args=(query, web_result, data_type.value),
        daemon=True,
    ).start()
