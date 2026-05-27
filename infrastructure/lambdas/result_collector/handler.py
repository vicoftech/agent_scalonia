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
            sr = event.get("sandbox_result") or {}
            home = int(sr.get("home_goals", os.environ.get("SANDBOX_RESULT_HOME_GOALS", "2")))
            away = int(sr.get("away_goals", os.environ.get("SANDBOX_RESULT_AWAY_GOALS", "1")))

            def _sb_bool(key: str, env_key: str) -> bool | None:
                if key in sr:
                    return bool(sr[key])
                raw = os.environ.get(env_key, "").strip().lower()
                if raw in ("1", "true", "yes", "si", "sí"):
                    return True
                if raw in ("0", "false", "no"):
                    return False
                return None

            result = svc.apply_manual_result(
                match_id,
                home,
                away,
                mvp_name=sr.get("mvp_name") or os.environ.get("SANDBOX_RESULT_MVP", "Sandbox MVP"),
                red_cards=int(sr.get("red_cards", os.environ.get("SANDBOX_RESULT_RED_CARDS", "0"))),
                goal_before_5min=_sb_bool("goal_before_5min", "SANDBOX_RESULT_GOAL_BEFORE_5MIN"),
                var_used=_sb_bool("var_used", "SANDBOX_RESULT_VAR_USED"),
                free_kick_goal=_sb_bool("free_kick_goal", "SANDBOX_RESULT_FREE_KICK_GOAL"),
                penalty_saved=_sb_bool("penalty_saved", "SANDBOX_RESULT_PENALTY_SAVED"),
                penalty_scored=_sb_bool("penalty_scored", "SANDBOX_RESULT_PENALTY_SCORED"),
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
