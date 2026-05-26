"""Recordatorios sin predicción — SPEC-032 tiers 1–3 (−60 / −30 / −15 min)."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    from src.services.match_lifecycle_service import MatchLifecycleService

    if event.get("sandbox"):
        logger.info("MATCH_REMINDER sandbox match=%s tier=%s", str(event.get("match_id", ""))[:8], event.get("reminder_tier"))

    match_id = event.get("match_id")
    if not match_id:
        return {"status": "ERROR", "error": "match_id required"}

    tier = int(event.get("reminder_tier") or event.get("tier") or 1)
    telegram_direct = bool(event.get("telegram_direct"))

    return MatchLifecycleService().send_match_reminders(
        match_id,
        tier,
        telegram_direct=telegram_direct,
        sandbox=bool(event.get("sandbox")),
    )
