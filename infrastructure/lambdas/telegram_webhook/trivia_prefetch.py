"""Entrega la trivia diaria general en el primer mensaje del día (sin push masivo)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def try_deliver_daily_trivia(
    user_id: str,
    profile: dict,
    *,
    text: str,
) -> tuple[str, dict] | None:
    """
    Si hay trivia DAILY_GENERAL pendiente, devuelve (mensaje, keyboard).
    No interrumpe comandos explícitos (/trivia, /start, etc.).
    """
    if not user_id or not profile:
        return None
    if text.startswith("/"):
        return None

    try:
        from src.services.trivia_service import TriviaService

        delivery = TriviaService().build_daily_delivery_for_user(user_id, profile)
        if not delivery:
            return None
        return delivery["message"], delivery["keyboard"]
    except Exception:
        logger.exception("daily_trivia_prefetch failed")
        return None
