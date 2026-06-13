"""Wizard admin resultados — texto: marcador + extendidas SI/NO."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
TG_DIR = ROOT / "infrastructure" / "lambdas" / "telegram_webhook"
if str(TG_DIR) not in sys.path:
    sys.path.insert(0, str(TG_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.match_result import MatchResult


def test_format_admin_preview_shows_extended_without_mvp():
    from src.services.result_admin_notify import format_admin_preview_message

    match = {"match_number": 12, "home_team": "CAN", "away_team": "BIH"}
    result = MatchResult(
        home_goals=1,
        away_goals=0,
        goal_before_5min=False,
        var_used=True,
        free_kick_goal=False,
        penalty_saved=False,
        penalty_scored=False,
        red_cards=2,
    )
    text = format_admin_preview_message(match, result)
    assert "CAN" in text or "Canadá" in text
    assert "Gol antes del 5'" in text
    assert "Intervención VAR" in text
    assert "Expulsiones (total): 2" in text
    assert "MVP" not in text
    assert "Lionel Messi" not in text


def test_pending_keyboard_starts_wizard():
    from src.services.result_admin_notify import pending_result_keyboard

    kb = pending_result_keyboard("mid-can-bih")
    flat = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert "✏️ Ingresar resultado" in flat
    assert "Confirmar y publicar" not in flat


def test_wizard_score_then_si_no_completes():
    from result_admin_commands import handle_result_admin_wizard

    match = {
        "match_id": "mid-can",
        "home_team": "CAN",
        "away_team": "BIH",
        "phase": "GROUP",
        "match_number": 12,
    }
    profile = {
        "result_admin_wizard": {
            "match_id": "mid-can",
            "step_idx": 0,
            "draft": {"_touched": []},
        }
    }
    with patch("result_admin_commands._admin_only", return_value=True):
        with patch("result_admin_commands.MatchDAO") as M:
            M.return_value.get_match.return_value = match
            with patch("result_admin_commands._save_wizard") as save:
                with patch("result_admin_commands.ResultDAO") as R:
                    R.return_value.has_scores.return_value = False
                    reply, markup = handle_result_admin_wizard(
                        "admin-1", profile, "1-0"
                    )
    assert reply and "Gol antes del 5'" in reply
    assert markup is None
    save.assert_called_once()
    saved = save.call_args[0][1]
    assert saved["step_idx"] == 1
    assert saved["draft"]["home_goals"] == 1
    assert saved["draft"]["away_goals"] == 0


def test_wizard_last_step_shows_preview():
    from result_admin_commands import handle_result_admin_wizard

    match = {
        "match_id": "mid-can",
        "home_team": "CAN",
        "away_team": "BIH",
        "phase": "GROUP",
        "match_number": 12,
    }
    profile = {
        "result_admin_wizard": {
            "match_id": "mid-can",
            "step_idx": 6,
            "draft": {
                "home_goals": 1,
                "away_goals": 0,
                "goal_before_5min": False,
                "var_used": True,
                "free_kick_goal": False,
                "penalty_saved": False,
                "penalty_scored": False,
                "_touched": [
                    "home_goals",
                    "away_goals",
                    "goal_before_5min",
                    "var_used",
                    "free_kick_goal",
                    "penalty_saved",
                    "penalty_scored",
                ],
            },
        }
    }
    with patch("result_admin_commands._admin_only", return_value=True):
        with patch("result_admin_commands.MatchDAO") as M:
            M.return_value.get_match.return_value = match
            with patch("result_admin_commands._save_wizard"):
                with patch("result_admin_commands.ResultDAO") as R:
                    R.return_value.has_scores.return_value = False
                    reply, markup = handle_result_admin_wizard(
                        "admin-1", profile, "no"
                    )
    assert reply and "VISTA PREVIA" in reply
    assert "Lionel Messi" not in reply
    assert markup is not None
    assert markup["inline_keyboard"][0][0]["text"] == "✅ Publicar"


def test_draft_to_result_never_sets_mvp():
    from result_admin_commands import _draft_to_result

    match = {"match_id": "mid-can", "phase": "GROUP"}
    draft = {
        "home_goals": 2,
        "away_goals": 1,
        "red_cards": 1,
        "var_used": True,
    }
    out = _draft_to_result(draft, match)
    assert out.mvp_name is None
    assert out.home_goals == 2
    assert out.red_cards == 1
