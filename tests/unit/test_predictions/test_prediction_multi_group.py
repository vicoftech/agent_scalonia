"""Predicción por grupo — selector y copia entre grupos."""
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
    }
    base.update(overrides)
    return base


def _svc_two_groups(**kwargs) -> PredictionService:
    preds = kwargs.get("prediction_dao") or MagicMock()
    if "prediction_dao" not in kwargs:
        preds.get_active.return_value = None
        preds.get_for_group.return_value = None
        preds.save_prediction.return_value = {"home_goals": 2, "away_goals": 0}

    matches = kwargs.get("match_dao") or MagicMock()
    matches.get_match.return_value = _match()
    matches.get_by_match_number.return_value = _match()

    groups = kwargs.get("group_dao") or MagicMock()
    if "group_dao" not in kwargs:
        groups.list_group_ids_for_user.return_value = ["grp-a", "grp-b"]

    def _get_group(gid: str):
        names = {"grp-a": "Grupo A", "grp-b": "Grupo B"}
        return {
            "group_id": gid,
            "name": names.get(gid, gid),
            "is_global": False,
            "status": "ACTIVE",
            "avatar": "⚽",
        }

    groups.get_group.side_effect = _get_group

    users = kwargs.get("user_dao") or MagicMock()
    profile_store = {
        "user_id": "u1",
        "status": "ACTIVE",
        "prediction_group_id": "grp-a",
        "prediction_wizard": None,
    }
    users.get_profile.side_effect = lambda _u: dict(profile_store)
    users.update_profile.side_effect = lambda _u, **kw: profile_store.update(kw)

    return PredictionService(
        prediction_dao=preds,
        match_dao=matches,
        group_dao=groups,
        user_dao=users,
    )


def test_open_match_flow_shows_group_picker_when_two_groups():
    svc = _svc_two_groups()
    text, kb = svc.open_match_flow("u1", 10)
    assert "Elegí el grupo" in text
    assert kb is not None
    callbacks = [
        b["callback_data"]
        for row in kb["inline_keyboard"]
        for b in row
    ]
    assert "prd:mg:10:" in callbacks[0]
    assert len(callbacks) == 2


def test_open_match_flow_single_group_skips_picker():
    groups = MagicMock()
    groups.list_group_ids_for_user.return_value = ["grp-a"]
    groups.get_group.return_value = {
        "group_id": "grp-a",
        "name": "Solo",
        "is_global": False,
        "status": "ACTIVE",
    }
    matches = MagicMock()
    matches.get_match.return_value = _match()
    matches.get_by_match_number.return_value = _match()
    matches.get_result.return_value = None
    svc = _svc_two_groups(group_dao=groups, match_dao=matches)
    text, _kb = svc.open_match_flow("u1", 10)
    assert "paso 1/7" in text.lower() or "marcador" in text.lower()


def test_copy_prediction_to_other_group():
    preds = MagicMock()
    src_pred = {
        "home_goals": 2,
        "away_goals": 1,
        "has_red_card": True,
        "pred_var_used": False,
    }
    preds.get_active.side_effect = lambda _u, mid, gid: (
        src_pred if gid == "grp-a" else None
    )
    preds.get_for_group.side_effect = preds.get_active
    preds.save_prediction.side_effect = lambda **kw: dict(kw)

    svc = _svc_two_groups(prediction_dao=preds)
    text, _kb = svc.copy_prediction_to_groups("u1", "m1", "grp-a", ["grp-b"])
    assert "copiada" in text.lower()
    assert preds.save_prediction.call_count == 1
    call_kw = preds.save_prediction.call_args.kwargs
    assert call_kw["group_id"] == "grp-b"
    assert call_kw["home_goals"] == 2
    assert call_kw["has_red_card"] is True


def test_finish_wizard_offers_other_groups():
    from src.services import prediction_wizard as pw

    preds = MagicMock()
    stored = {"home_goals": 1, "away_goals": 0}

    def _get_active(_u, _mid, gid):
        return stored if gid == "grp-a" else None

    preds.get_active.side_effect = _get_active
    preds.get_for_group.side_effect = _get_active

    svc = _svc_two_groups(prediction_dao=preds)
    text, kb = pw.finish_wizard(svc, "u1", 10, "grp-a")
    assert "Otros grupos" in text
    assert kb is not None
    flat = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert any(c.startswith("prd:mg:10:") for c in flat)
    assert any(c.startswith("prd:cpa:10:") for c in flat)
