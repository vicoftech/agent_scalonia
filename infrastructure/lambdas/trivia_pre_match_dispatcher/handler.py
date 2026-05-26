"""
Lambda: trivia pre-partido — 1h antes del kickoff (SPEC-025).

Programar con EventBridge Scheduler: trivia-pre-{match_id}
MVP: invocación manual con {"match_id": "..."} o scan de partidos próximos.

Deploy: pendiente (no incluido en este sprint de código).
"""
from __future__ import annotations

import json
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

    sent = 0
    for m in matches:
        if not force and m.get("status") != "SCHEDULED":
            continue
        q = svc.generate_pre_match_trivia(m)
        trivia_id = q.get("match_id", "")[:8] or m.get("match_number")
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        svc._trivia.put_broadcast_trivia(
            {
                "trivia_id": str(trivia_id)[:8],
                "type": "PRE_MATCH",
                "level": "EXPERT",
                "points": 5,
                "match_id": m.get("match_id"),
                "group_id": "GLOBAL",
                "status": "SENT",
                "sent_at": now.isoformat(),
                "closes_at": (now + timedelta(hours=2)).isoformat(),
                **q,
            }
        )
        sent += 1
        logger.info("pre_match_trivia match=%s trivia=%s", m.get("match_number"), trivia_id)

    return {"status": "OK", "sent": sent}
