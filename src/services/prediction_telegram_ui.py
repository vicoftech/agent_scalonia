"""Teclados inline predicciones — SPEC-2026-021."""
from __future__ import annotations

from typing import Any

KO_PHASES = frozenset(
    {"R16", "ROUND_OF_32", "ROUND_OF_16", "QF", "QUARTER_FINAL", "SF", "SEMI_FINAL", "FINAL", "THIRD_PLACE"}
)


def merge_button_rows(rows: list[list[dict[str, str]]]) -> dict:
    return {"inline_keyboard": rows}


def no_group_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "➕ Crear mi grupo", "callback_data": "grp:list"}],
        ],
    }


def score_picker_keyboard(match: dict, match_number: int, grp8: str) -> dict:
    scores = ["2-0", "1-0", "3-1", "1-1", "0-1"]
    rows: list[list[dict[str, str]]] = []
    for sc in scores:
        rows.append(
            [{"text": sc, "callback_data": f"prd:s:{match_number}:{sc}:{grp8}"}]
        )
    rows.append([{"text": "✏️ Otro (escribí /predecir)", "callback_data": f"prd:x:{match_number}:{grp8}"}])
    return {"inline_keyboard": rows}


def change_existing_keyboard(match_number: int, grp8: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Sí, cambiar", "callback_data": f"prd:o:{match_number}:{grp8}"},
                {"text": "No, mantener", "callback_data": "prd:noop"},
            ],
        ],
    }


def after_save_keyboard(match: dict, group_id: str) -> dict:
    g8 = group_id.replace("-", "")[:8]
    return {
        "inline_keyboard": [
            [{"text": "🎯 /completo", "callback_data": f"prd:c:{int(match.get('match_number', 0))}:{g8}"}],
        ],
    }


def completo_menu_keyboard(match_number: int, grp8: str) -> dict:
    n, g = match_number, grp8
    return {
        "inline_keyboard": [
            [{"text": "🟥 Expulsión +2pts", "callback_data": f"prd:rd:{n}:0:{g}"}],
            [{"text": "🟥 Sí habrá roja", "callback_data": f"prd:rd:{n}:1:{g}"}],
            [{"text": "✅ Listo", "callback_data": f"prd:done:{n}:{g}"}],
        ],
    }


def group_picker_keyboard(groups: list[dict[str, Any]]) -> dict:
    rows: list[list[dict[str, str]]] = []
    for g in groups:
        gid = g.get("group_id", "")
        g8 = gid.replace("-", "")[:8]
        label = f"{g.get('avatar', '⚽')} {(g.get('name') or gid)[:26]}"
        rows.append([{"text": label, "callback_data": f"prd:sg:{g8}"}])
    return {"inline_keyboard": rows}


def ko_playoff_keyboard(match: dict, match_number: int, score: str, grp8: str) -> dict:
    """Empate en KO: vía + ganador en un tap (prd:k:...)."""
    home = match.get("home_team", "LOC")
    away = match.get("away_team", "VIS")
    n, g = match_number, grp8
    return {
        "inline_keyboard": [
            [
                {"text": f"⏱️ ET → {home}", "callback_data": f"prd:k:{n}:{score}:ET:HOME:{g}"},
                {"text": f"⏱️ ET → {away}", "callback_data": f"prd:k:{n}:{score}:ET:AWAY:{g}"},
            ],
            [
                {"text": f"🥅 Pen → {home}", "callback_data": f"prd:k:{n}:{score}:PEN:HOME:{g}"},
                {"text": f"🥅 Pen → {away}", "callback_data": f"prd:k:{n}:{score}:PEN:AWAY:{g}"},
            ],
        ],
    }
