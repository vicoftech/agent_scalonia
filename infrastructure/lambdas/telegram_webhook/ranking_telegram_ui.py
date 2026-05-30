"""UI Telegram para Mi ranking — SPEC-2026-042."""
from __future__ import annotations

from typing import Any

from src.services.ranking_service import RANKING_TOP_N


def group_picker_keyboard(groups: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    for g in groups:
        gid = str(g.get("group_id") or "")
        g8 = gid.replace("-", "")[:8]
        label = f"{g.get('avatar', '⚽')} {str(g.get('name') or gid)[:64]}"
        rows.append([{"text": label, "callback_data": f"rnk:g:{g8}"}])
    return {"inline_keyboard": rows}


def _format_row(row: dict[str, Any]) -> str:
    prefix = "👉 " if row.get("is_viewer") else ""
    alias = "vos" if row.get("is_viewer") else str(row.get("alias") or "?")
    return f"{prefix}#{int(row.get('position') or 0)} {alias} — {int(row.get('points') or 0)} pts"


def format_ranking_message(
    ranking: dict[str, Any],
    *,
    page: int = 0,
    page_size: int = RANKING_TOP_N,
) -> str:
    rows = list(ranking.get("rows") or [])
    group_name = str(ranking.get("group_name") or "Grupo")
    lines = [f"🏆 Ranking — {group_name}", ""]

    start = page * page_size
    end = start + page_size
    page_rows = rows[start:end]
    viewer_row = next((r for r in rows if r.get("is_viewer")), None)

    for row in page_rows:
        lines.append(_format_row(row))

    if viewer_row and viewer_row not in page_rows:
        lines.append("")
        lines.append(_format_row(viewer_row))

    remaining = max(len(rows) - end, 0)
    if remaining > 0:
        lines.append(f"\n… y {remaining} más")

    lines.append("\nActualizado tras cada partido puntuado.")
    return "\n".join(lines)


def ranking_pagination_keyboard(
    *,
    group_id: str,
    page: int,
    total_rows: int,
    page_size: int = RANKING_TOP_N,
) -> dict[str, Any] | None:
    g8 = group_id.replace("-", "")[:8]
    buttons: list[dict[str, str]] = []
    if page > 0:
        buttons.append({"text": "◀️ Anterior", "callback_data": f"rnk:pg:{page - 1}:{g8}"})
    if (page + 1) * page_size < total_rows:
        buttons.append({"text": "Siguiente ▶️", "callback_data": f"rnk:pg:{page + 1}:{g8}"})
    if not buttons:
        return None
    return {
        "inline_keyboard": [
            buttons,
            [{"text": "↩️ Elegir otro grupo", "callback_data": "rnk:back"}],
        ]
    }
