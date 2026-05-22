"""Teclados del wizard de predicción (onboarding-style)."""
from __future__ import annotations

from src.services.prediction_telegram_ui import KO_PHASES, merge_button_rows


def wizard_skip_row(match_number: int, grp8: str) -> list[dict[str, str]]:
    return [{"text": "⏭️ Saltar paso", "callback_data": f"prd:w:skip:{match_number}:{grp8}"}]


def wizard_finish_row(match_number: int, grp8: str) -> list[dict[str, str]]:
    return [{"text": "✅ Terminar ahora", "callback_data": f"prd:w:done:{match_number}:{grp8}"}]


def wizard_yes_no_keyboard(
    match_number: int, grp8: str, step_id: str
) -> dict:
    """Sí/No para variable extendida — prd:w:yn:{step}:{0|1}:{n}:{g}."""
    n, g = match_number, grp8
    return merge_button_rows(
        [
            [
                {"text": "✅ Sí", "callback_data": f"prd:w:yn:{step_id}:1:{n}:{g}"},
                {"text": "❌ No", "callback_data": f"prd:w:yn:{step_id}:0:{n}:{g}"},
            ],
            wizard_skip_row(n, g),
            wizard_finish_row(n, g),
        ]
    )


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


def _is_ko(match: dict) -> bool:
    return (match.get("phase") or "GROUP").upper() in KO_PHASES
