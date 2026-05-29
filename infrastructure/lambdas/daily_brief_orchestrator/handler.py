"""Lambda: orquestador diario de briefs — SPEC-2026-045."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    os.environ.setdefault(
        "BRIEF_TABLE", os.environ.get("BRIEF_TABLE", "ProdeBriefTable-dev")
    )
    os.environ.setdefault("ENV", os.environ.get("ENV", "dev"))

    job = (event or {}).get("job") or "daily_brief"
    if job != "daily_brief":
        return {"statusCode": 400, "body": {"error": f"unknown job {job}"}}

    from src.services.brief_orchestrator import run_daily_brief_job

    result = run_daily_brief_job()
    return {"statusCode": 200, "body": result}
