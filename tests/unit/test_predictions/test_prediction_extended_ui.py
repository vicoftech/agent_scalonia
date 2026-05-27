"""Iconografía y brief de predicción extendida."""
from __future__ import annotations

from src.services.prediction_rules import (
    EXTENDED_STEPS,
    extended_brief_lines,
    extended_icons_compact,
    extended_item_line,
    format_prediction_brief,
)


def test_extended_brief_always_six_items_with_dash_when_empty():
    pred = {"home_goals": 2, "away_goals": 1, "has_red_card": True}
    lines = extended_brief_lines(pred)
    assert len(lines) == len(EXTENDED_STEPS)
    assert lines[0].startswith("🟥 Tarjeta roja: Sí")
    assert "—" in lines[1]


def test_extended_icons_compact_all_six():
    pred = {"home_goals": 1, "away_goals": 0}
    assert extended_icons_compact(pred) == " 🟥⚡📺🎯🧤⚽"


def test_format_prediction_brief_includes_extended_section():
    pred = {
        "home_goals": 2,
        "away_goals": 2,
        "pred_var_used": False,
    }
    text = format_prediction_brief(
        pred,
        match_title="#10 ARG vs ALG",
        group_name="Los Pibes",
        minutes_to_veda="45 min",
    )
    assert "── Extendida ──" in text
    assert "📺 Intervención VAR: No" in text
    assert "⚡ Gol antes del 5': —" in text
    assert "¿Querés cambiarla?" in text


def test_format_prediction_brief_veda_locked():
    pred = {"home_goals": 1, "away_goals": 2}
    text = format_prediction_brief(
        pred,
        match_title="MEX vs RSA",
        group_name="Test",
        minutes_to_veda="cerrada",
        change_prompt=False,
        veda_locked=True,
    )
    assert "🔒 Veda activa" in text
    assert "── Extendida ──" in text
    assert "¿Querés cambiarla?" not in text


def test_extended_item_line_points_hint_only_when_answered():
    step = EXTENDED_STEPS[0]
    pred = {"has_red_card": True}
    assert "+1" in extended_item_line(pred, step, show_points_hint=True)
    assert "+1" not in extended_item_line(pred, step, show_points_hint=False)
