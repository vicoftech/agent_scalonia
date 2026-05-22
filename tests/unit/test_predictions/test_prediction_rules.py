"""Reglas de puntuación — SPEC-021 v3."""
from src.services.prediction_rules import (
    PTS_EXTENDED_BOOL,
    PTS_EXACT,
    help_scoring_text,
    max_possible_points,
)


def test_help_includes_basic_and_extended():
    text = help_scoring_text()
    assert "Básica" in text
    assert "Extendida" in text
    assert "Playoff" in text
    assert "5 pts" in text


def test_max_possible_basic_only():
    assert max_possible_points({"home_goals": 1, "away_goals": 0}) == PTS_EXACT


def test_max_possible_with_extras():
    pred = {
        "home_goals": 2,
        "away_goals": 1,
        "has_red_card": True,
        "pred_var_used": False,
        "playoff_via": "ET",
        "playoff_winner": "ARG",
    }
    assert max_possible_points(pred) == PTS_EXACT + 2 * PTS_EXTENDED_BOOL + 2
