"""Wizard de predicción — flujo onboarding."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.services.prediction_service import PredictionService
from src.services import prediction_wizard as pw

_NOW = datetime.now(timezone.utc)
_KICKOFF = (_NOW + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _match(**overrides):
    base = {
        "match_id": "m1",
        "match_number": 10,
        "home_team": "ARG",
        "away_team": "ALG",
        "phase": "GROUP",
        "group_letter": "J",
        "kickoff_utc": _KICKOFF,
        "veda_active": False,
        "status": "SCHEDULED",
        "venue": "Stadium",
        "city": "Dallas",
    }
    base.update(overrides)
    return base


def _svc(**kwargs) -> PredictionService:
    preds = kwargs.get("prediction_dao") or MagicMock()
    preds.get_active.return_value = None
    preds.save_prediction.return_value = {"home_goals": 2, "away_goals": 0}
    preds.update_optional_fields.return_value = {"home_goals": 2, "away_goals": 0}
    matches = kwargs.get("match_dao")
    if matches is None:
        matches = MagicMock()
        matches.get_match.return_value = _match()
        matches.get_by_match_number.return_value = _match()
    groups = kwargs.get("group_dao") or MagicMock()
    groups.list_group_ids_for_user.return_value = ["grp-private"]
    groups.get_group.return_value = {
        "group_id": "grp-private",
        "name": "Los Pibes",
        "is_global": False,
        "status": "ACTIVE",
    }
    users = kwargs.get("user_dao") or MagicMock()
    profile_store: dict = {
        "user_id": "u1",
        "status": "ACTIVE",
        "prediction_group_id": "grp-private",
        "prediction_wizard": None,
    }

    def _get_profile(_uid: str):
        return dict(profile_store)

    def _update_profile(_uid: str, **fields):
        profile_store.update(fields)

    users.get_profile.side_effect = _get_profile
    users.update_profile.side_effect = _update_profile
    return PredictionService(
        prediction_dao=preds,
        match_dao=matches,
        group_dao=groups,
        user_dao=users,
    )


def test_start_wizard_shows_step1():
    svc = _svc()
    text, kb = pw.start_wizard(svc, "u1", 10, "grp-private")
    assert "paso 1" in text.lower()
    assert "Marcador" in text
    assert kb is not None
    assert any("prd:s:" in b.get("callback_data", "") for row in kb["inline_keyboard"] for b in row)


def test_custom_score_keeps_wizard_session():
    svc = _svc()
    pw.start_wizard(svc, "u1", 10, "grp-private")
    text, _ = pw.wizard_begin_custom_score(svc, "u1", 10, "grp-private")
    assert "Escribí el marcador" in text
    result = pw.wizard_handle_text(svc, "u1", "3-2")
    assert result is not None
    rtext, rkb = result
    assert "Marcador guardado" in rtext
    assert "tarjeta roja" in rtext.lower() or "paso 2" in rtext.lower()


def test_ko_draw_requires_playoff_step():
    ko = _match(phase="QF")
    matches = MagicMock()
    matches.get_match.return_value = ko
    matches.get_by_match_number.return_value = ko
    svc = _svc(match_dao=matches)
    pw.start_wizard(svc, "u1", 10, "grp-private")
    text, kb = pw.wizard_submit_score(svc, "u1", 10, "grp-private", 1, 1)
    assert kb is not None
    assert any("prd:w:ko:" in b.get("callback_data", "") for row in kb["inline_keyboard"] for b in row)
    svc._preds.save_prediction.assert_not_called()


def test_skip_red_advances_to_scorer():
    svc = _svc()
    pw.start_wizard(svc, "u1", 10, "grp-private")
    pw.wizard_submit_score(svc, "u1", 10, "grp-private", 2, 0)
    text, kb = pw.wizard_advance_skip(svc, "u1")
    assert "goleador" in text.lower()
    assert kb is not None
