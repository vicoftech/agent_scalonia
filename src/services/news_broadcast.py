"""Broadcast noticias por Telegram — SPEC-2026-046."""
from __future__ import annotations

import logging
import time
from typing import Any

from src.clients.telegram_client import get_bot_token, send_telegram_photo
from src.services.news_telegram_format import build_news_keyboard

logger = logging.getLogger(__name__)


def broadcast_news_to_targets(
    *,
    delivery_targets: list[dict[str, Any]],
    news_id: str,
    caption: str,
    image_url: str,
    like_count: int = 0,
    article_url: str | None = None,
    token: str | None = None,
) -> tuple[int, int]:
    tok = token or get_bot_token()
    sent = 0
    for target in delivery_targets:
        chat_id = target.get("tg_chat_id")
        user_id = target.get("user_id")
        if not chat_id or not user_id:
            continue
        keyboard = build_news_keyboard(
            news_id,
            user_id=user_id,
            like_count=like_count,
            article_url=article_url,
        )
        try:
            send_telegram_photo(
                int(chat_id),
                image_url,
                caption,
                tok,
                reply_markup=keyboard,
            )
            sent += 1
            time.sleep(0.05)
        except Exception:
            logger.exception(
                "news_broadcast failed user_prefix=%s",
                str(user_id)[:8],
            )
    skipped = max(0, len(delivery_targets) - sent)
    return sent, skipped
