"""Wizard admin resultados — preview, extendidas, MVP."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.match_result import MatchResult

ROOT = Path(__file__).resolve().parents[3]
TG_DIR = ROOT / "infrastructure" / "lambdas" / "telegram_webhook"
if str(TG_DIR) not in sys.path:
    sys.path.insert(0, str(TG_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_format_admin_preview_shows_all_extended():
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
        mvp_name="Edin Džeko",
    )
    text = format_admin_preview_message(match, result)
    assert "CAN" in text or "Canadá" in text
    assert "Gol antes del 5'" in text
    assert "Intervención VAR" in text
    assert "Expulsiones (total): 2" in text
    assert "Edin Džeko" in text
    assert "Lionel Messi" not in text


def test_edit_extended_keyboard_has_red_cards_and_mvp():
    from src.services.result_admin_notify import edit_extended_keyboard

    kb = edit_extended_keyboard("mid-can-bih")
    flat = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert "🟥 0" in flat
    assert "⭐ Sin MVP" in flat
    assert "✏️ Escribir MVP" in flat


def test_resolve_edit_result_draft_overrides_candidate_mvp():
    from result_admin_commands import _resolve_edit_result

    match = {
        "match_id": "mid-can",
        "home_team": "CAN",
        "away_team": "BIH",
        "phase": "GROUP",
    }
    candidate = MatchResult(
        home_goals=1,
        away_goals=0,
        mvp_name="Lionel Messi",
        var_used=None,
    )
    svc = MagicMock()
    svc.get_candidate_result.return_value = candidate

    profile = {
        "result_admin_draft": {
            "match_id": "mid-can",
            "home_goals": 1,
            "away_goals": 0,
            "mvp_name": None,
            "red_cards": 1,
            "var_used": True,
        }
    }
    with patch("src.dao.dynamo.user_dao.UserDAO") as U:
        U.return_value.get_profile.return_value = profile
        with patch("result_admin_commands.ResultDAO") as R:
            R.return_value.get_result.return_value = None
            out = _resolve_edit_result("admin-1", "mid-can", match, svc)
    assert out is not None
    assert out.mvp_name is None
    assert out.red_cards == 1
    assert out.var_used is True


def test_handle_result_admin_pending_saves_mvp():
    from result_admin_commands import handle_result_admin_pending

    profile = {
        "result_admin_pending": {"match_id": "mid-can", "field": "mvp"},
        "result_admin_draft": {
            "match_id": "mid-can",
            "home_goals": 1,
            "away_goals": 0,
        },
    }
    with patch("result_admin_commands._admin_only", return_value=True):
        with patch("result_admin_commands.MatchDAO") as M:
            M.return_value.get_match.return_value = {
                "match_id": "mid-can",
                "home_team": "CAN",
                "away_team": "BIH",
                "phase": "GROUP",
            }
            with patch("result_admin_commands._save_draft") as save:
                with patch("result_admin_commands._clear_pending") as clear:
                    reply, markup = handle_result_admin_pending(
                        "admin-1", profile, "Edin Džeko"
                    )
    assert reply and "Edin" in reply
    assert markup is not None
    save.assert_called_once()
    clear.assert_called_once()
