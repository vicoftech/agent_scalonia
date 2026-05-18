"""Consumer SQS — persiste enriquecimiento KB (SPEC-2026-023)."""
from __future__ import annotations

import json
import logging
import os

from src.kb.kb_enrichment_service import DataType, KBEnrichmentService

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def handler(event, context):
    svc = KBEnrichmentService()
    processed = 0
    for record in event.get("Records", []):
        body = json.loads(record["body"])
        query = body["query"]
        web_result = body["web_result"]
        data_type = DataType(body["data_type"])
        svc.enrich_from_web(query, web_result, data_type)
        processed += 1
        logger.info("enriched type=%s query=%r", data_type.value, query[:80])
    return {"processed": processed}
