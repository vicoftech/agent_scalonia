"""Lambda cron noticias Mundial — SPEC-2026-046."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    os.environ.setdefault("ENV", os.environ.get("ENV", "dev"))

    from src.services.news_broadcast import broadcast_news_to_targets
    from src.services.world_cup_news_service import WorldCupNewsService

    def _broadcast(**kwargs) -> tuple[int, int]:
        svc_inner = WorldCupNewsService()
        return broadcast_news_to_targets(
            delivery_targets=svc_inner.list_delivery_targets(),
            news_id=kwargs["news_id"],
            caption=kwargs["caption"],
            image_url=kwargs["image_url"],
            like_count=kwargs["like_count"],
        )

    svc = WorldCupNewsService(broadcast_fn=_broadcast)
    phase = (event or {}).get("phase")
    slot = (event or {}).get("slot")
    force = bool((event or {}).get("force"))

    if phase == "PRE" and slot:
        result = svc.run_pre_slot(str(slot), force=force)
    elif phase == "LIVE" or (event or {}).get("job") == "live_poll":
        result = svc.run_live_poll(force=force)
    else:
        return {"statusCode": 400, "body": {"error": "unknown event", "event": event}}

    return {"statusCode": 200, "body": result}
