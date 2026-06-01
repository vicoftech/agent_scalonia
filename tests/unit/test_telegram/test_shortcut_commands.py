"""Atajos mi_puntuacion y resultados."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_LAMBDA_DIR = Path(__file__).resolve().parents[3] / "infrastructure" / "lambdas" / "telegram_webhook"
if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))

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
    with patch("bot_commands.admin_menu_hint", return_value="admin hint"), patch(
        "src.services.auth_service.AuthService.is_admin_global", return_value=False
    ):
        text, markup = handle_shortcut_command("u1", "/menu")
    assert "Menú actualizado" in text
    assert markup is None


@patch("ask_ia_commands.handle_ask_ia_command")
@patch("trivia_commands.handle_trivia_command")
@patch("profile_commands.handle_perfil_command", return_value=None)
@patch("ranking_commands.matches_mi_ranking_command", return_value=False)
def test_ask_ia_not_blocked_by_trivia_none_tuple(
    mock_ranking, mock_perfil, mock_trivia, mock_ask_ia
):
    """handle_trivia_command returns (None, None) for non-trivia commands — must not swallow /ask_ia."""
    mock_trivia.return_value = (None, None)
    mock_ask_ia.return_value = ("🤖 Ask IA — Mundial 2026", None)

    text, markup = handle_shortcut_command("u1", "/ask_ia")

    mock_ask_ia.assert_called_once_with("u1", "/ask_ia")
    assert "Ask IA" in text
    assert markup is None
