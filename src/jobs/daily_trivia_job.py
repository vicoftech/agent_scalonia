"""Job diario: trivia general «historias de mundiales» (SPEC-025)."""
from __future__ import annotations

import logging
from typing import Any

from src.services.trivia_service import TriviaService

logger = logging.getLogger(__name__)


def run_daily_trivia_job(*, created_by: str = "SYSTEM") -> dict[str, Any]:
    svc = TriviaService()
    result = svc.publish_daily_general(created_by=created_by)
    logger.info(
        "daily_trivia_job status=%s trivia_id=%s",
        result.get("status"),
        result.get("trivia_id"),
    )
    return result
