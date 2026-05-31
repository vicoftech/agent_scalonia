"""SPEC-2026-048 — tournament scoring."""
from unittest.mock import MagicMock

from src.services.tournament_scoring_service import TournamentScoringService


def test_score_user_champion_and_finalist():
    pred_dao = MagicMock()
    user_dao = MagicMock()
    match_dao = MagicMock()
    match_dao.get_by_match_number.return_value = {"status": "FINISHED", "match_id": "m104"}
    match_dao.get_result.return_value = {
        "result_90min_home": 2,
        "result_90min_away": 1,
    }
    svc = TournamentScoringService(
        prediction_dao=pred_dao,
        user_dao=user_dao,
        match_dao=match_dao,
    )
    awards = {
        "champion_team": "ARG",
        "finalist_team": "FRA",
        "best_player_name": "Messi",
        "top_scorer_name": "Haaland",
        "best_goalkeeper_name": "Martinez",
        "best_young_player_name": "Yamal",
        "revelation_team": "ECU",
    }
    item = {
        "status": "LOCKED",
        "champion_team": "ARG",
        "finalist_team": "FRA",
        "best_player_name": "Messi",
        "top_scorer_name": "Mbappe",
        "best_goalkeeper_name": "Martinez",
        "best_young_player_name": "Yamal",
        "revelation_team": "ECU",
    }
    result = svc.score_user("u1", item, awards)
    assert result["points"] == 160
    user_dao.add_tournament_points.assert_called_once_with("u1", 160)
    pred_dao.mark_scored.assert_called_once()


def test_process_idempotent_when_awards_processed():
    pred_dao = MagicMock()
    pred_dao.get_awards.return_value = {"awards_processed": True}
    match_dao = MagicMock()
    match_dao.get_by_match_number.return_value = {"status": "FINISHED"}
    svc = TournamentScoringService(prediction_dao=pred_dao, match_dao=match_dao)
    out = svc.process_tournament_awards()
    assert out["ok"] is False
