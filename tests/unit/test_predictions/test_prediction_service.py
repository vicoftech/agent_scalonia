"""SPEC-2026-021 — prediction_service unit tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.services.prediction_service import PredictionService

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
    preds = MagicMock()
    preds.get_active.return_value = None
    preds.save_prediction.return_value = {"home_goals": 2, "away_goals": 0}
    matches = MagicMock()
    matches.get_match.return_value = _match()
    matches.get_by_match_number.return_value = _match()
    matches.list_matches.return_value = [_match()]
    groups = MagicMock()
    groups.list_group_ids_for_user.return_value = ["GLOBAL", "grp-private"]
    def _get_group(gid: str):
        return {
            "group_id": gid,
            "name": "GLOBAL" if gid == "GLOBAL" else "Los Pibes",
            "is_global": gid == "GLOBAL",
            "status": "ACTIVE",
        }

    groups.get_group.side_effect = _get_group
    users = MagicMock()
    users.get_profile.return_value = {
        "user_id": "u1",
        "status": "ACTIVE",
        "prediction_group_id": "grp-private",
    }
    return PredictionService(
        prediction_dao=preds,
        match_dao=matches,
        group_dao=groups,
        user_dao=users,
        **kwargs,
    )


def test_check_can_predict_requires_non_global_group():
    groups = MagicMock()
    groups.list_group_ids_for_user.return_value = ["GLOBAL"]
    groups.get_group.return_value = {
        "group_id": "GLOBAL",
        "is_global": True,
        "status": "ACTIVE",
    }
    users = MagicMock()
    users.get_profile.return_value = {"user_id": "u1", "status": "ACTIVE"}
    svc = PredictionService(group_dao=groups, user_dao=users)
    ok, code = svc.check_can_predict("u1")
    assert ok is False
    assert code == "NO_GROUP_MEMBERSHIP"


def test_check_can_predict_ok_with_private_group():
    ok, code = _svc().check_can_predict("u1")
    assert ok is True
    assert code == "ok"


def test_validate_blocks_veda_active():
    svc = _svc()
    vr = svc.validate_save("u1", _match(veda_active=True), 2, 0)
    assert not vr.ok
    assert vr.code == "VEDA_ACTIVE"


def test_save_score_persists():
    svc = _svc()
    text, markup = svc.save_score("u1", "m1", "grp-private", 2, 0)
    assert "guardada" in text
    assert "Los Pibes" in text
    svc._preds.save_prediction.assert_called_once()


def test_prediction_sk_format():
    from src.dao.dynamo.prediction_dao import prediction_sk

    assert prediction_sk("mid", "gid") == "PRED#mid#GROUP#gid"


def test_parse_predecir_command():
    parsed = _svc().parse_predecir_command("/predecir ARG 2-0 ALG")
    assert parsed == ("ARG", 2, 0, "ALG")
