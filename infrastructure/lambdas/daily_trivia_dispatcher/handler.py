"""
Lambda: trivia diaria general — historias de mundiales.

Publica cuando now >= min(10:00 ART, primer_partido_del_día − 2 h).

EventBridge (UTC): cron(0 9-15 * * ? *)  → invoca cada hora 06:00–12:00 Argentina.
El job es idempotente; la primera ejecución tras la hora objetivo crea la trivia.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    from src.jobs.daily_trivia_job import run_daily_trivia_job

    created_by = event.get("created_by") or os.environ.get("DAILY_TRIVIA_CREATED_BY", "SYSTEM")
    result = run_daily_trivia_job(created_by=created_by)
    return {"statusCode": 200, "body": result}
