"""Comando /mi_ranking y flujo selector — SPEC-2026-042."""
from __future__ import annotations

import re

from ranking_telegram_ui import (
    format_ranking_message,
    group_picker_keyboard,
    ranking_pagination_keyboard,
)
from src.services.prediction_service import PredictionService
from src.services.ranking_service import RankingService

_MI_RANKING = re.compile(r"^/mi[_-]ranking(?:@[\w_]+)?\s*$", re.IGNORECASE)
_MI_PUNTUACION = re.compile(r"^/mi[_-]puntuacion(?:@[\w_]+)?\s*$", re.IGNORECASE)


def matches_mi_ranking_command(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(_MI_RANKING.match(stripped) or _MI_PUNTUACION.match(stripped))


def show_group_ranking(
    user_id: str,
    group_id: str,
    *,
    page: int = 0,
) -> tuple[str, dict | None]:
    ranking = RankingService().build_group_ranking(group_id, viewer_user_id=user_id)
    if not ranking:
        return "No encontré ese grupo.", None
    text = format_ranking_message(ranking, page=page)
    markup = ranking_pagination_keyboard(
        group_id=group_id,
        page=page,
        total_rows=len(ranking.get("rows") or []),
    )
    return text, markup


def handle_mi_ranking_command(user_id: str, text: str = "") -> tuple[str, dict | None]:
    groups = RankingService().list_user_groups_for_ranking(user_id)
    if not groups:
        return PredictionService().no_group_message()
    if len(groups) == 1:
        return show_group_ranking(user_id, groups[0]["group_id"])
    if text and _MI_PUNTUACION.match(text.strip()):
        prefix = "Usá /mi_ranking o el botón 🏆 Mi ranking.\n\n"
        body, markup = "Elegí el grupo:", group_picker_keyboard(groups)
        return prefix + body, markup
    return "Elegí el grupo:", group_picker_keyboard(groups)
