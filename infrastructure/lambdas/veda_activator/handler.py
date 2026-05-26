"""Activa veda −30 min y notifica — SPEC-032 / ADR-005."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    from src.services.match_lifecycle_service import MatchLifecycleService

    match_id = event.get("match_id")
    if not match_id:
        return {"status": "ERROR", "error": "match_id required"}

    return MatchLifecycleService().activate_veda(
        match_id,
        telegram_direct=bool(event.get("telegram_direct")),
        force=bool(event.get("force")),
    )
