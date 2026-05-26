"""
Lambda: trivia pre-partido — 1h antes del kickoff (SPEC-025).

Programar con EventBridge Scheduler: trivia-pre-{match_id} o devfast-trivia (SPEC-041).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    from src.dao.dynamo.match_dao import MatchDAO
    from src.services.trivia_service import TriviaService

    match_id = event.get("match_id")
    event_type = event.get("event_type", "")
    if event.get("sandbox"):
        logger.info("MATCH_TRIVIA sandbox match=%s", str(match_id or "")[:8])
    force = bool(event.get("sandbox")) or event_type == "MATCH_TRIVIA"
    svc = TriviaService()
    dao = MatchDAO()

    if match_id:
        match = dao.get_match(match_id)
        if not match:
            return {"status": "NOT_FOUND", "match_id": match_id}
        matches = [match]
    else:
        matches = dao.list_matches()

    results: list[dict] = []
    for m in matches:
        if not force and m.get("status") != "SCHEDULED":
            continue
        out = svc.dispatch_pre_match_trivia(m)
        results.append(out)
        logger.info(
            "pre_match_trivia match=%s sent=%s",
            m.get("match_number"),
            out.get("telegram_sent"),
        )

    return {
        "status": "OK",
        "dispatched": len(results),
        "results": results,
    }
