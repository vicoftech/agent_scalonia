"""Mensajes de resultado final."""
from src.models.match_result import MatchResult
from src.services.result_notification import (
    format_match_events_lines,
    format_match_result_message,
)


def test_result_message_score_and_events_no_prediction_no_mvp():
    text = format_match_result_message(
        {
            "home_team": "MEX",
            "away_team": "RSA",
            "group_letter": "A",
            "phase": "GROUP",
            "venue": "Azteca",
            "city": "CDMX",
        },
        MatchResult(
            home_goals=2,
            away_goals=0,
            mvp_name="Lozano",
            var_used=True,
            goal_before_5min=False,
            free_kick_goal=False,
            penalty_saved=False,
            penalty_scored=None,
        ),
    )
    assert "Calculando" not in text
    assert "Tu predicción" not in text
    assert "Jugador del partido" not in text
    assert "Lozano" not in text
    assert "2 - 0" in text
    assert "🟥 Expulsados: ninguno" in text
    assert "Gol antes del 5': No" in text
    assert "Intervención VAR: Sí" in text
    assert "Penal convertido: —" in text


def test_match_events_lines():
    lines = format_match_events_lines(
        MatchResult(home_goals=1, away_goals=0, red_cards=2, penalty_scored=True)
    )
    assert lines[0] == "🟥 Expulsados: Sí"
    assert "Penal convertido: Sí" in lines
