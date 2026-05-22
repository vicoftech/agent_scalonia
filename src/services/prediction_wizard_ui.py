"""Teclados del wizard de predicción (onboarding-style)."""
from __future__ import annotations

from typing import Any

from src.services.prediction_telegram_ui import KO_PHASES, merge_button_rows


def wizard_skip_row(match_number: int, grp8: str) -> list[dict[str, str]]:
    return [{"text": "⏭️ Saltar paso", "callback_data": f"prd:w:skip:{match_number}:{grp8}"}]


def wizard_finish_row(match_number: int, grp8: str) -> list[dict[str, str]]:
    return [{"text": "✅ Terminar ahora", "callback_data": f"prd:w:done:{match_number}:{grp8}"}]


def wizard_ko_keyboard(match: dict, match_number: int, score: str, grp8: str) -> dict:
    """Eliminatoria con empate: tiempo extra o penales + ganador."""
    home = match.get("home_team", "LOC")
    away = match.get("away_team", "VIS")
    n, g = match_number, grp8
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"⏱️ Gana {home} en alargue",
                    "callback_data": f"prd:w:ko:{n}:{score}:ET:HOME:{g}",
                },
            ],
            [
                {
                    "text": f"⏱️ Gana {away} en alargue",
                    "callback_data": f"prd:w:ko:{n}:{score}:ET:AWAY:{g}",
                },
            ],
            [
                {
                    "text": f"🥅 Gana {home} en penales",
                    "callback_data": f"prd:w:ko:{n}:{score}:PEN:HOME:{g}",
                },
            ],
            [
                {
                    "text": f"🥅 Gana {away} en penales",
                    "callback_data": f"prd:w:ko:{n}:{score}:PEN:AWAY:{g}",
                },
            ],
        ],
    }


def wizard_red_keyboard(match_number: int, grp8: str) -> dict:
    n, g = match_number, grp8
    return merge_button_rows(
        [
            [
                {"text": "🟥 No habrá roja", "callback_data": f"prd:w:red:0:{n}:{g}"},
                {"text": "🟥 Sí habrá roja", "callback_data": f"prd:w:red:1:{n}:{g}"},
            ],
            wizard_skip_row(n, g),
            wizard_finish_row(n, g),
        ]
    )


def wizard_scorer_keyboard(
    players: list[str], match_number: int, grp8: str
) -> dict:
    n, g = match_number, grp8
    rows: list[list[dict[str, str]]] = []
    for idx, name in enumerate(players[:4]):
        rows.append(
            [{"text": f"⚽ {name}", "callback_data": f"prd:w:sc:{idx}:{n}:{g}"}]
        )
    rows.append(
        [{"text": "✏️ Otro jugador", "callback_data": f"prd:w:scother:{n}:{g}"}]
    )
    rows.append(wizard_skip_row(n, g))
    rows.append(wizard_finish_row(n, g))
    return merge_button_rows(rows)


def wizard_scorer_goals_keyboard(match_number: int, grp8: str) -> dict:
    n, g = match_number, grp8
    return merge_button_rows(
        [
            [
                {"text": "1 gol", "callback_data": f"prd:w:sg:1:{n}:{g}"},
                {"text": "2 goles", "callback_data": f"prd:w:sg:2:{n}:{g}"},
            ],
            [{"text": "3 goles", "callback_data": f"prd:w:sg:3:{n}:{g}"}],
            wizard_skip_row(n, g),
        ]
    )


def wizard_mvp_keyboard(
    players: list[str], match_number: int, grp8: str
) -> dict:
    n, g = match_number, grp8
    rows: list[list[dict[str, str]]] = []
    for idx, name in enumerate(players[:4]):
        rows.append(
            [{"text": f"⭐ {name}", "callback_data": f"prd:w:mvp:{idx}:{n}:{g}"}]
        )
    rows.append(
        [{"text": "✏️ Otro jugador", "callback_data": f"prd:w:mvpother:{n}:{g}"}]
    )
    rows.append(wizard_skip_row(n, g))
    rows.append(wizard_finish_row(n, g))
    return merge_button_rows(rows)


def _is_ko(match: dict) -> bool:
    return (match.get("phase") or "GROUP").upper() in KO_PHASES
