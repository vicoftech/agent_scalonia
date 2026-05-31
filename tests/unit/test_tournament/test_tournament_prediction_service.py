"""SPEC-2026-048 — tournament prediction service."""
from unittest.mock import MagicMock

from src.services.tournament_prediction_service import (
    TournamentPredictionService,
    WIZARD_FIELDS,
)


def test_validate_complete_rejects_same_champion_finalist():
    svc = TournamentPredictionService(
        prediction_dao=MagicMock(),
        user_dao=MagicMock(),
        match_dao=MagicMock(),
    )
    payload = {field: "VAL" for field in WIZARD_FIELDS}
    payload["champion_team"] = "ARG"
    payload["finalist_team"] = "ARG"
    payload["revelation_team"] = "ECU"
    ok, err = svc.validate_complete(payload)
    assert ok is False
    assert "campeón" in err.lower()


def test_is_editable_before_match_72_finished():
    match_dao = MagicMock()
    match_dao.get_by_match_number.return_value = {"status": "SCHEDULED"}
    svc = TournamentPredictionService(match_dao=match_dao)
    assert svc.is_editable() is True


def test_is_editable_false_after_match_72_finished():
    match_dao = MagicMock()
    match_dao.get_by_match_number.return_value = {"status": "FINISHED"}
    svc = TournamentPredictionService(match_dao=match_dao)
    assert svc.is_editable() is False


def test_confirm_predictions_persists():
    user_dao = MagicMock()
    pred_dao = MagicMock()
    match_dao = MagicMock()
    match_dao.get_by_match_number.return_value = {"status": "SCHEDULED"}
    svc = TournamentPredictionService(
        prediction_dao=pred_dao,
        user_dao=user_dao,
        match_dao=match_dao,
    )
    draft = {
        "champion_team": "ARG",
        "finalist_team": "FRA",
        "best_player_name": "Messi",
        "top_scorer_name": "Haaland",
        "best_goalkeeper_name": "Martinez",
        "best_young_player_name": "Yamal",
        "revelation_team": "ECU",
    }
    user_dao.get_profile.return_value = {"tournament_wizard_draft": draft}
    ok, msg = svc.confirm_predictions("u1")
    assert ok is True
    pred_dao.put.assert_called_once()
    user_dao.update_profile.assert_called()
