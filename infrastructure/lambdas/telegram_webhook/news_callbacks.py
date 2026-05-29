"""Callbacks news:like — SPEC-2026-046."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def handle_news_callback(
    user_id: str,
    data: str,
    *,
    callback_query_id: str | None = None,
    chat_id: int | None = None,
    message: dict[str, Any] | None = None,
) -> None:
    from handler import _get_token, _post_json
    from src.services.news_telegram_format import build_news_keyboard
    from src.services.world_cup_news_service import WorldCupNewsService

    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "news" or parts[1] != "like":
        return
    news_id = parts[2]
    token = _get_token()
    svc = WorldCupNewsService()
    created, like_count = svc.record_like(user_id, news_id)
    answer = "¡Gracias!" if created else "Ya diste like"
    if callback_query_id:
        _post_json(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": answer},
            timeout=5,
        )
    if chat_id and message:
        article_url = (svc._news.get_details(news_id) or {}).get("article_url")
        keyboard = build_news_keyboard(
            news_id,
            user_id=user_id,
            like_count=like_count,
            article_url=article_url,
        )
        _post_json(
            f"https://api.telegram.org/bot{token}/editMessageReplyMarkup",
            {
                "chat_id": chat_id,
                "message_id": message.get("message_id"),
                "reply_markup": keyboard,
            },
            timeout=10,
        )
