"""Provision / cancel schedules DEV_FAST — SPEC-2026-041."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    os.environ.setdefault("ENABLE_MATCH_LIFECYCLE_SANDBOX", "true")

    action = (event.get("action") or "").lower()
    match_id = event.get("match_id")
    if not match_id:
        return {"status": "ERROR", "error": "match_id required"}

    from src.services.match_schedule_sandbox import MatchScheduleSandboxManager

    mgr = MatchScheduleSandboxManager()

    if action == "provision":
        mode = event.get("mode") or "DEV_FAST"
        result = mgr.provision_sandbox_schedules(match_id, mode=mode)
    elif action == "cancel":
        result = mgr.cancel_sandbox_schedules(match_id)
    else:
        return {"status": "ERROR", "error": f"unknown action: {action}"}

    logger.info("match_schedule_manager action=%s match=%s status=%s", action, match_id[:8], result.get("status"))
    return result
