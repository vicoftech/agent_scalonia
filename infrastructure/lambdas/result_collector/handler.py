"""
Lambda result_collector — SPEC-2026-031.

Triggers:
  - scheduled: EventBridge rate(5 minutes)
  - match_ended: desde match_poller (SPEC-028)
  - manual: scripts/collect_result.py o invocación directa
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault(
        "DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev")
    )
    from src.services.result_service import ResultService

    svc = ResultService()
    trigger = event.get("trigger", "scheduled")
    processed = 0
    errors = 0

    if trigger == "scheduled":
        candidates = svc.find_incomplete_match_ids()
        if not candidates:
            return {"status": "OK", "trigger": trigger, "candidates": 0, "processed": 0}
        for match_id in candidates:
            try:
                if svc.collect_result(match_id):
                    processed += 1
                    logger.info("Result collected match=%s", match_id[:8])
            except Exception:
                errors += 1
                logger.exception("collect_result failed match=%s", match_id[:8])

    elif trigger == "match_ended":
        match_id = event.get("match_id")
        if not match_id:
            return {"status": "ERROR", "error": "match_id required"}
        result = svc.collect_result(match_id)
        return {
            "status": "OK",
            "trigger": trigger,
            "match_id": match_id,
            "collected": result is not None,
        }

    elif trigger == "manual":
        match_id = event.get("match_id")
        if not match_id:
            return {"status": "ERROR", "error": "match_id required"}
        result = svc.collect_result(match_id)
        return {
            "status": "OK",
            "trigger": trigger,
            "match_id": match_id,
            "result": result.to_dict() if result else None,
        }

    else:
        return {"status": "ERROR", "error": f"unknown trigger: {trigger}"}

    return {
        "status": "OK",
        "trigger": trigger,
        "candidates": len(candidates) if trigger == "scheduled" else None,
        "processed": processed,
        "errors": errors,
    }
