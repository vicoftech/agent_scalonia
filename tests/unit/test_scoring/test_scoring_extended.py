"""Puntos extendidos y KO."""
from src.models.match_result import MatchResult
from src.scoring.scoring_extended import extended_points, ko_playoff_points


def test_extended_all_correct():
    pred = {
        "has_red_card": False,
        "pred_goal_before_5min": False,
        "pred_var_used": True,
    }
    result = MatchResult(
        home_goals=2,
        away_goals=0,
        red_cards=0,
        goal_before_5min=False,
        var_used=True,
    )
    pts, hits = extended_points(pred, result)
    assert pts == 3
    assert len(hits) == 3


def test_extended_unknown_actual_not_scored():
    pred = {"pred_var_used": True}
    result = MatchResult(home_goals=1, away_goals=0, var_used=None)
    pts, hits = extended_points(pred, result)
    assert pts == 0


def test_ko_playoff_bonus():
    pred = {
        "home_goals": 0,
        "away_goals": 0,
        "playoff_via": "PENALTIES",
        "playoff_winner": "ARG",
    }
    result = MatchResult(
        home_goals=0,
        away_goals=0,
        playoff_via="PENALTIES",
        playoff_winner="ARG",
        phase="QF",
    )
    pts, _ = ko_playoff_points(pred, result, "QF")
    assert pts == 2
