"""
Lambda scoring_processor — consume prode-scoring-{env} (FINISH_MATCH).

SPEC-2026-022 / encolado desde result_service.
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

    from src.dao.dynamo.result_dao import ResultDAO
    from src.services.scoring_service import ScoringService

    if not event.get("Records") and event.get("event_type") == "MATCH_SCORING_CATCHUP":
        match_id = event.get("match_id")
        if event.get("sandbox"):
            logger.info("MATCH_SCORING_CATCHUP sandbox match=%s", str(match_id or "")[:8])
        if not match_id:
            return {"status": "ERROR", "error": "match_id required"}
        results = ResultDAO()
        if not results.get_raw(match_id):
            return {"status": "SKIP", "reason": "no_result"}
        outcome = ScoringService().process_finish_match(match_id)
        return {
            "status": "OK",
            "event_type": "MATCH_SCORING_CATCHUP",
            "scored": outcome.scored,
            "already_processed": outcome.already_processed,
        }

    svc = ScoringService()
    scored = 0
    skipped = 0
    failed = 0
    batch_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        mid = record.get("messageId")
        try:
            import json

            body = record.get("body") or "{}"
            payload = json.loads(body) if isinstance(body, str) else body
            outcome = svc.process_sqs_payload(payload)
            if outcome is None:
                skipped += 1
            else:
                scored += outcome.scored
                skipped += outcome.skipped
        except Exception:
            failed += 1
            logger.exception("Scoring record failed messageId=%s", mid)
            if mid:
                batch_failures.append({"itemIdentifier": mid})

    result = {"scored": scored, "skipped": skipped, "failed": failed}
    if batch_failures:
        result["batchItemFailures"] = batch_failures
    return result
