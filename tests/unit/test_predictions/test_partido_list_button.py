"""Etiquetas de botones /partidos."""
from src.services.prediction_telegram_ui import (
    TELEGRAM_INLINE_BUTTON_TEXT_MAX,
    partido_list_button_label,
)


def test_partido_list_button_label_open_without_prediction():
    label = partido_list_button_label(
        {"home_team": "ARG", "away_team": "ALG"},
        match_number=1,
        group_letter="J",
        date_label="16/06",
        has_prediction=False,
        is_predictable=True,
    )
    assert "Match #1" in label
    assert "ARG" in label and "ALG" in label
    assert "Grupo J" in label
    assert "16/06" in label
    assert "⏳" in label
    assert len(label) <= TELEGRAM_INLINE_BUTTON_TEXT_MAX


def test_partido_list_button_label_with_prediction():
    label = partido_list_button_label(
        {"home_team": "MEX", "away_team": "RSA"},
        match_number=12,
        group_letter="A",
        date_label="11/06",
        has_prediction=True,
        is_predictable=True,
    )
    assert "✅" in label
    assert "Match #12" in label


def test_partido_list_button_label_veda_shows_lock():
    label = partido_list_button_label(
        {"home_team": "BRA", "away_team": "MAR"},
        match_number=3,
        group_letter="C",
        date_label="20/06",
        has_prediction=False,
        is_predictable=False,
    )
    assert "🔒" in label
