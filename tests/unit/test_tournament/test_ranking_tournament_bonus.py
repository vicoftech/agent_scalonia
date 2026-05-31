"""Ranking con bonus torneo — SPEC-048."""
from unittest.mock import MagicMock

from src.services.ranking_service import RankingService


def test_ranking_includes_tournament_points():
    groups = MagicMock()
    groups.get_group.return_value = {"name": "Test", "status": "ACTIVE"}
    groups.list_member_user_ids.return_value = ["u1"]
    users = MagicMock()
    users.get_profile.return_value = {"alias": "Ana", "tournament_points": 60}
    preds = MagicMock()
    preds.list_user_predictions.return_value = [
        {"points_earned": 45, "status": "SCORED"},
    ]
    svc = RankingService(group_dao=groups, user_dao=users, prediction_dao=preds)
    ranking = svc.build_group_ranking("g1", viewer_user_id="u1")
    assert ranking["rows"][0]["points"] == 105
