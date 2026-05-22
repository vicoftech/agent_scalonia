"""Partido finalizado — predicción vs resultado."""
from unittest.mock import MagicMock

from src.services.prediction_result_report import (
    compute_match_points,
    format_finished_match_report,
)
from src.services.prediction_service import PredictionService


def test_format_finished_exact_score():
    match = {
        "match_number": 1,
        "home_team": "ARG",
        "away_team": "ALG",
        "group_letter": "J",
        "phase": "GROUP",
    }
    text = format_finished_match_report(
        match,
        group_name="Los Pibes",
        result={"result_90min_home": 2, "result_90min_away": 0},
        prediction={"home_goals": 2, "away_goals": 0, "points_earned": 5},
    )
    assert "2-0" in text
    assert "+5 pts" in text or "5 pts" in text
    assert "exacto" in text.lower() or "Exacto" in text or "+5" in text
    assert "Sumaste 5 pts" in text


def test_format_finished_incorrect_explains():
    text = format_finished_match_report(
        {
            "match_number": 2,
            "home_team": "MEX",
            "away_team": "RSA",
            "group_letter": "A",
            "phase": "GROUP",
        },
        group_name="G",
        result={"result_90min_home": 0, "result_90min_away": 1},
        prediction={"home_goals": 2, "away_goals": 0},
    )
    assert "Sin puntos" in text
    assert "Predijiste 2-0" in text
    assert "0-1" in text


def test_format_finished_no_prediction():
    text = format_finished_match_report(
        {"match_number": 3, "home_team": "BRA", "away_team": "MAR", "phase": "GROUP"},
        group_name="G",
        result={"result_final_home": 0, "result_final_away": 0},
        prediction=None,
    )
    assert "No tenías predicción" in text


def test_open_match_picker_finished_shows_report():
    matches = MagicMock()
    matches.get_by_match_number.return_value = {
        "match_id": "m1",
        "match_number": 1,
        "home_team": "ARG",
        "away_team": "ALG",
        "status": "FINISHED",
        "phase": "GROUP",
        "group_letter": "J",
    }
    matches.get_result.return_value = {
        "result_90min_home": 2,
        "result_90min_away": 0,
    }
    preds = MagicMock()
    preds.get_for_group.return_value = {
        "home_goals": 2,
        "away_goals": 0,
        "status": "ACTIVE",
    }
    groups = MagicMock()
    groups.get_group.return_value = {"name": "Los Pibes", "is_global": False}
    groups.list_group_ids_for_user.return_value = ["g1"]

    users = MagicMock()
    users.get_profile.return_value = {
        "status": "ACTIVE",
        "prediction_group_id": "g1",
    }

    svc = PredictionService(
        prediction_dao=preds,
        match_dao=matches,
        group_dao=groups,
        user_dao=users,
    )
    text, kb = svc.open_match_picker("u1", 1, "g1")
    assert "Partido finalizado" in text
    assert "Tu predicción" in text
    assert kb is None
    preds.get_active.assert_not_called()
