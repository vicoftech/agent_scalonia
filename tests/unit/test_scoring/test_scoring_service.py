"""ScoringService — FINISH_MATCH."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.models.match_result import MatchResult
from src.services.scoring_service import ScoringService


def _match():
    return {
        "match_id": "mid-1",
        "match_number": 1,
        "home_team": "MEX",
        "away_team": "RSA",
        "phase": "GROUP",
    }


def _result():
    return MatchResult(
        home_goals=2,
        away_goals=0,
        red_cards=0,
        var_used=True,
        goal_before_5min=False,
    )


def test_process_skips_when_already_processed():
    rdao = MagicMock()
    rdao.is_scoring_done.return_value = True
    svc = ScoringService(results=rdao)
    out = svc.process_finish_match("mid-1")
    assert out.already_processed
    rdao.mark_result_processed.assert_not_called()


def test_process_scores_active_predictions():
    rdao = MagicMock()
    rdao.is_scoring_done.return_value = False
    rdao.get_result.return_value = _result()
    rdao.get_raw.return_value = {
        "result_90min_home": 2,
        "result_90min_away": 0,
    }

    mdao = MagicMock()
    mdao.get_match.return_value = _match()

    pdao = MagicMock()
    pdao.get_predictions_for_match.return_value = [
        {
            "user_id": "u1",
            "group_id": "g1",
            "home_goals": 2,
            "away_goals": 0,
            "pred_var_used": True,
            "status": "ACTIVE",
        },
    ]
    pdao.mark_scored.return_value = True

    udao = MagicMock()
    svc = ScoringService(
        results=rdao, predictions=pdao, matches=mdao, users=udao
    )
    out = svc.process_finish_match("mid-1")
    assert out.scored == 1
    assert out.rows[0].base_points == 5
    assert out.rows[0].extended_points == 1
    assert out.rows[0].points == 6
    udao.add_match_points.assert_called_once_with("u1", 6)
    rdao.mark_result_processed.assert_called_once_with("mid-1")


def test_notify_scoring_breakdowns_idempotent():
    rdao = MagicMock()
    rdao.is_breakdown_notified.return_value = True
    svc = ScoringService(results=rdao)
    assert svc.notify_scoring_breakdowns("mid-1") == 0
    rdao.mark_breakdown_notified.assert_not_called()
