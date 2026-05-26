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
    event_type = event.get("event_type", "")
    if event_type == "MATCH_RESULT":
        trigger = event.get("trigger") or "match_ended"
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

    elif trigger in ("match_ended", "sandbox_devfast"):
        match_id = event.get("match_id")
        if not match_id:
            return {"status": "ERROR", "error": "match_id required"}
        if trigger == "sandbox_devfast" or event.get("sandbox"):
            logger.info("sandbox_devfast apply_manual_result match=%s", match_id[:8])
            home = int(os.environ.get("SANDBOX_RESULT_HOME_GOALS", "2"))
            away = int(os.environ.get("SANDBOX_RESULT_AWAY_GOALS", "1"))
            result = svc.apply_manual_result(
                match_id,
                home,
                away,
                mvp_name=os.environ.get("SANDBOX_RESULT_MVP", "Sandbox MVP"),
                replace=True,
            )
        else:
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
