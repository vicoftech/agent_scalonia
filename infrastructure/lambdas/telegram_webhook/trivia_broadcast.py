"""Envío masivo de trivias por Telegram — SPEC-025."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def broadcast_trivia_message(
    *,
    delivery_targets: list[dict[str, Any]],
    message: str,
    keyboard: dict[str, Any],
    token: str,
    send_message: Callable[..., None],
) -> tuple[int, int]:
    """
    Envía la trivia a cada chat_id. Retorna (enviados, omitidos_sin_chat).
    """
    sent = 0
    for target in delivery_targets:
        chat_id = target.get("tg_chat_id")
        if not chat_id:
            continue
        try:
            send_message(int(chat_id), message, token, reply_markup=keyboard)
            sent += 1
            time.sleep(0.05)
        except Exception:
            logger.exception(
                "trivia_broadcast failed user_prefix=%s",
                str(target.get("user_id", ""))[:8],
            )
    skipped = max(0, len(delivery_targets) - sent)
    return sent, skipped
