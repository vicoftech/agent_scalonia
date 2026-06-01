"""Footer Telegram — countdown y comandos básicos."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from src.services.telegram_interaction_footer import (
    append_interaction_footer,
    clear_opener_cache,
    countdown_parts,
    countdown_text,
    interaction_footer_lines,
)

_OPENER = {
    "match_number": 1,
    "home_team": "MEX",
    "away_team": "CAN",
    "kickoff_utc": "2026-06-11T16:00:00Z",
    "status": "SCHEDULED",
}


def setup_function():
    clear_opener_cache()


def test_countdown_parts_before_kickoff():
    now = datetime(2026, 6, 10, 16, 0, tzinfo=timezone.utc)
    with patch(
        "src.services.telegram_interaction_footer.first_tournament_match",
        return_value=_OPENER,
    ):
        info = countdown_parts(now=now)
    assert info["started"] is False
    assert info["days"] == 1
    assert info["hours"] == 0
    assert info["minutes"] == 0


def test_countdown_text_includes_teams():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    with patch(
        "src.services.telegram_interaction_footer.first_tournament_match",
        return_value=_OPENER,
    ):
        text = countdown_text(now=now)
    assert "⏳ Faltan" in text
    assert "MEX" in text or "México" in text
    assert "CAN" in text or "Canad" in text


def test_countdown_after_kickoff():
    now = datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc)
    with patch(
        "src.services.telegram_interaction_footer.first_tournament_match",
        return_value=_OPENER,
    ):
        text = countdown_text(now=now)
    assert "ya arrancó" in text


def test_interaction_footer_has_basic_commands():
    with patch(
        "src.services.telegram_interaction_footer.first_tournament_match",
        return_value=_OPENER,
    ):
        footer = interaction_footer_lines()
    assert "/partidos" in footer
    assert "/ask_ia" in footer
    assert "⏳ Faltan" in footer


def test_append_footer_once():
    with patch(
        "src.services.telegram_interaction_footer.first_tournament_match",
        return_value=_OPENER,
    ):
        base = "Hola jugador"
        once = append_interaction_footer(base)
        twice = append_interaction_footer(once)
    assert once == twice
    assert once.count("⏳ Faltan") == 1


def test_append_footer_html():
    with patch(
        "src.services.telegram_interaction_footer.first_tournament_match",
        return_value=_OPENER,
    ):
        out = append_interaction_footer("Respuesta IA", parse_mode="HTML")
    assert "<i>" in out
    assert "/partidos" in out
