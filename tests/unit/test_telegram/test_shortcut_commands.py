"""Atajos mi_puntuacion y resultados."""
from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.shortcut_commands import (
    format_mi_puntuacion,
    handle_shortcut_command,
)


@patch("infrastructure.lambdas.telegram_webhook.shortcut_commands.UserDAO")
@patch("infrastructure.lambdas.telegram_webhook.shortcut_commands.PredictionDAO")
def test_format_mi_puntuacion(mock_pred, mock_user):
    mock_user.return_value.get_profile.return_value = {
        "total_points": 12,
        "match_points": 10,
        "trivia_points": 2,
    }
    mock_pred.return_value.list_user_predictions.return_value = [
        {
            "match_id": "m1",
            "status": "SCORED",
            "home_goals": 2,
            "away_goals": 0,
            "points_earned": 5,
            "updated_at": "2026-01-01",
        },
    ]
    with patch(
        "infrastructure.lambdas.telegram_webhook.shortcut_commands.MatchDAO"
    ) as mock_match:
        mock_match.return_value.get_match.return_value = {
            "home_team": "ARG",
            "away_team": "ALG",
        }
        text = format_mi_puntuacion("u1")
    assert "12" in text
    assert "ARG" in text
    assert "5 pts" in text


def test_handle_menu_command():
    text, markup = handle_shortcut_command("u1", "/menu")
    assert "Menú actualizado" in text
    assert markup is None
