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
    preds = kwargs.get("prediction_dao") or MagicMock()
    preds.get_active.return_value = None
    preds.save_prediction.return_value = {"home_goals": 2, "away_goals": 0}
    matches = kwargs.get("match_dao")
    if matches is None:
        matches = MagicMock()
        matches.list_matches.return_value = [_match()]
    matches.get_match.return_value = _match()
    matches.get_by_match_number.return_value = _match()
    groups = kwargs.get("group_dao") or MagicMock()
    groups.list_group_ids_for_user.return_value = ["GLOBAL", "grp-private"]
    def _get_group(gid: str):
        return {
            "group_id": gid,
            "name": "GLOBAL" if gid == "GLOBAL" else "Los Pibes",
            "is_global": gid == "GLOBAL",
            "status": "ACTIVE",
        }

    groups.get_group.side_effect = _get_group
    users = kwargs.get("user_dao") or MagicMock()
    profile_store = {
        "user_id": "u1",
        "status": "ACTIVE",
        "prediction_group_id": "grp-private",
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


def test_save_score_persists_and_continues_wizard():
    svc = _svc()
    text, markup = svc.save_score("u1", "m1", "grp-private", 2, 0)
    assert "Marcador guardado" in text
    assert "Los Pibes" in text
    assert "paso 2" in text.lower() or "tarjeta roja" in text.lower()
    svc._preds.save_prediction.assert_called_once()
    assert markup is not None


def test_prediction_sk_format():
    from src.dao.dynamo.prediction_dao import prediction_sk

    assert prediction_sk("mid", "gid") == "PRED#mid#GROUP#gid"


def test_parse_predecir_command():
    parsed = _svc().parse_predecir_command("/predecir ARG 2-0 ALG")
    assert parsed == ("ARG", 2, 0, "ALG")


def _first_match_button_text(markup: dict) -> str:
    return markup["inline_keyboard"][0][0]["text"]


def test_list_partidos_includes_far_future_group_match():
    far = (_NOW + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    matches = MagicMock()
    matches.list_matches.return_value = [_match(kickoff_utc=far, match_number=1)]
    svc = _svc(match_dao=matches)
    text, markup = svc.list_partidos_view("u1")
    assert "Fase de grupos" in text
    assert "Elegí un partido" in text
    assert markup is not None
    btn = _first_match_button_text(markup)
    assert "Match #1" in btn
    assert "ARG" in btn and "ALG" in btn
    assert "⏳" in btn


def test_list_partidos_excludes_knockout():
    ko = (_NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    matches = MagicMock()
    matches.list_matches.return_value = [
        _match(kickoff_utc=ko, phase="QF", match_number=90),
    ]
    svc = _svc(match_dao=matches)
    text, markup = svc.list_partidos_view("u1")
    assert "ingest" in text.lower() or "grupos" in text.lower()
    assert markup is None


def test_list_partidos_pagination():
    base = _NOW + timedelta(days=1)
    group_matches = [
        _match(
            match_id=f"m{i}",
            match_number=i,
            kickoff_utc=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            home_team=f"T{i}",
            away_team=f"U{i}",
        )
        for i in range(1, 11)
    ]
    matches = MagicMock()
    matches.list_matches.return_value = group_matches
    svc = _svc(match_dao=matches)
    text0, kb0 = svc.list_partidos_view("u1", page=0)
    text1, kb1 = svc.list_partidos_view("u1", page=1)
    assert "Página 1/2" in text0
    assert "T1" not in text0
    assert "Página 2/2" in text1
    page0_btns = [b["text"] for row in kb0["inline_keyboard"] for b in row if "prd:o:" in b.get("callback_data", "")]
    page1_btns = [b["text"] for row in kb1["inline_keyboard"] for b in row if "prd:o:" in b.get("callback_data", "")]
    assert any("T1" in t for t in page0_btns)
    assert not any("T9" in t for t in page0_btns)
    assert any("T9" in t for t in page1_btns)
    def _nav_row(kb: dict) -> list[dict]:
        for row in kb["inline_keyboard"]:
            if any("prd:pg:" in b.get("callback_data", "") for b in row):
                return row
        return []

    assert any("Siguiente" in b["text"] for b in _nav_row(kb0))
    assert any("Anterior" in b["text"] for b in _nav_row(kb1))


def test_list_partidos_empty_when_no_matches_in_db():
    matches = MagicMock()
    matches.list_matches.return_value = []
    svc = _svc(match_dao=matches)
    text, _ = svc.list_partidos_view("u1")
    assert "ingest" in text.lower()
