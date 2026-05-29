"""Re-export broadcast para handler Telegram — SPEC-2026-046."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.services.news_broadcast import broadcast_news_to_targets


def broadcast_news_message(
    *,
    delivery_targets: list[dict[str, Any]],
    news_id: str,
    caption: str,
    image_url: str,
    like_count: int,
    token: str,
    send_photo: Callable[..., None],
    article_url: str | None = None,
) -> tuple[int, int]:
    """Compatibilidad con inyección send_photo del webhook."""
    sent = 0
    from src.services.news_telegram_format import build_news_keyboard

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
            send_photo(
                int(chat_id),
                image_url,
                caption,
                token,
                reply_markup=keyboard,
            )
            sent += 1
        except Exception:
            pass
    return sent, max(0, len(delivery_targets) - sent)


__all__ = ["broadcast_news_message", "broadcast_news_to_targets"]
