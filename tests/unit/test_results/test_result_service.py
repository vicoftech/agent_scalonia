"""SPEC-2026-031 — result collector SC-01 a SC-09."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.dao.dynamo.result_dao import ResultDAO
from src.models.match_result import MatchResult
from src.services import result_parser, result_queues, result_service
from src.services.result_parser import parse_web_result, set_llm_parse_fn
from src.services.result_service import ResultService, set_web_search_fn


def _match(
    *,
    match_id: str = "mid-1",
    home: str = "ARG",
    away: str = "ALG",
    kickoff_hours_ago: float = 3,
) -> dict:
    kickoff = datetime.now(timezone.utc) - timedelta(hours=kickoff_hours_ago)
    return {
        "match_id": match_id,
        "match_number": 97,
        "home_team": home,
        "away_team": away,
        "phase": "GROUP",
        "group_letter": "J",
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "venue": "AT&T Stadium",
        "city": "Dallas",
        "status": "SCHEDULED",
    }


def _svc(
    *,
    result_dao: MagicMock | None = None,
    match_dao: MagicMock | None = None,
    prediction_dao: MagicMock | None = None,
    group_dao: MagicMock | None = None,
    user_dao: MagicMock | None = None,
) -> ResultService:
    return ResultService(
        result_dao=result_dao or MagicMock(),
        match_dao=match_dao or MagicMock(),
        prediction_dao=prediction_dao or MagicMock(),
        group_dao=group_dao or MagicMock(),
        user_dao=user_dao or MagicMock(),
    )


@pytest.fixture(autouse=True)
def _reset_injection():
    set_web_search_fn(None)
    set_llm_parse_fn(None)
    with patch.dict("os.environ", {"RESULT_ADMIN_GATE_ENABLED": "false"}):
        yield
    set_web_search_fn(None)
    set_llm_parse_fn(None)


def test_sc03_complete_skips_web_search():
    rdao = MagicMock()
    rdao.get_result.return_value = MatchResult(
        home_goals=2,
        away_goals=0,
        mvp_name="Messi",
        result_processed=True,
    )
    svc = _svc(result_dao=rdao)
    set_web_search_fn(lambda q: pytest.fail("web search should not run"))

    out = svc.collect_result("mid-1")
    assert out.mvp_name == "Messi"
    rdao.save_result.assert_not_called()


def test_sc04_match_still_in_progress():
    mdao = MagicMock()
    mdao.get_match.return_value = _match(kickoff_hours_ago=0.5)
    rdao = MagicMock()
    rdao.get_result.return_value = None
    svc = _svc(result_dao=rdao, match_dao=mdao)
    called = []

    def _search(q):
        called.append(q)
        return "x"

    set_web_search_fn(_search)
    assert svc._fetch_via_web_search(mdao.get_match.return_value) is None
    assert called == []


def test_sc02_fetch_and_save_enqueues():
    mdao = MagicMock()
    match = _match()
    mdao.get_match.return_value = match
    rdao = MagicMock()
    rdao.get_result.side_effect = [None, MatchResult(home_goals=2, away_goals=0, mvp_name="Messi")]
    rdao.has_scores.return_value = False
    rdao.is_scoring_done.return_value = False
    rdao.save_result.return_value = True
    rdao.is_complete.return_value = False

    preds = MagicMock()
    groups = MagicMock()
    groups.list_groups_for_broadcast.return_value = [
        {"group_id": "g1", "status": "ACTIVE", "name": "Los Pibes"},
    ]
    groups.list_member_user_ids.return_value = ["u1", "u2"]
    groups.get_group.return_value = {"name": "Los Pibes"}
    users = MagicMock()
    users.get_profile.side_effect = lambda uid: {
        "notifications_enabled": True,
        "tg_chat_id": 111 if uid == "u1" else 222,
    }

    svc = _svc(
        result_dao=rdao,
        match_dao=mdao,
        prediction_dao=preds,
        group_dao=groups,
        user_dao=users,
    )

    set_web_search_fn(lambda q: "Argentina 2-0 Argelia. MVP: Lionel Messi")
    set_llm_parse_fn(
        lambda raw, m: {
            "found": True,
            "home_goals": 2,
            "away_goals": 0,
            "status": "FT",
            "scorers": {"Messi": 1},
            "red_cards": 0,
            "mvp_name": "Lionel Messi",
        }
    )

    with patch.object(result_service, "enqueue_scoring", return_value=True) as es:
        with patch.object(
            result_service, "enqueue_match_result_notification", return_value=True
        ) as en:
            out = svc.collect_result("mid-1")

    assert out is not None
    assert out.home_goals == 2
    rdao.save_result.assert_called_once()
    mdao.update_status.assert_called_with("mid-1", "FINISHED")
    es.assert_called_once()
    assert en.call_count == 2


def test_sc05_parse_not_found():
    set_llm_parse_fn(lambda raw, m: {"found": False})
    out = parse_web_result("sin datos", _match())
    assert out is None


def test_sc07_penalties_parse():
    set_llm_parse_fn(
        lambda raw, m: {
            "found": True,
            "home_goals": 1,
            "away_goals": 1,
            "status": "PEN",
            "playoff_winner": "ARG",
            "scorers": {},
            "red_cards": 0,
            "mvp_name": "Messi",
        }
    )
    r = parse_web_result("Argentina 1-1 Francia penales", _match(home="ARG", away="FRA"))
    assert r.status == "PEN"
    assert r.playoff_winner == "ARG"
    assert r.playoff_via == "PENALTIES"


def test_sc08_save_idempotent_no_double_scoring():
    rdao = MagicMock()
    rdao.get_result.return_value = MatchResult(home_goals=2, away_goals=0, mvp_name="Messi")
    rdao.has_scores.return_value = True
    rdao.is_scoring_done.return_value = True
    rdao.save_result.return_value = False

    mdao = MagicMock()
    mdao.get_match.return_value = _match()
    svc = _svc(result_dao=rdao, match_dao=mdao)

    with patch.object(result_service, "enqueue_scoring") as es:
        svc.collect_result("mid-1")
    es.assert_not_called()
    rdao.save_result.assert_not_called()


def test_sc01_enrich_mvp_only():
    rdao = MagicMock()
    existing = MatchResult(home_goals=2, away_goals=0, mvp_name=None, source="api_football")
    rdao.get_result.return_value = existing
    rdao.has_scores.return_value = True
    rdao.is_scoring_done.return_value = True

    mdao = MagicMock()
    mdao.get_match.return_value = _match()

    svc = _svc(result_dao=rdao, match_dao=mdao)
    set_web_search_fn(
        lambda q: "jugador del partido Lionel Messi MVP Copa Mundial 2026"
    )

    with patch.object(result_service, "enqueue_scoring") as es:
        out = svc.collect_result("mid-1")

    rdao.update_mvp.assert_called_once()
    es.assert_not_called()
    assert out.mvp_name and "Messi" in out.mvp_name


def test_sc09_mvp_missing_still_returns_scores():
    rdao = MagicMock()
    existing = MatchResult(home_goals=2, away_goals=0, mvp_name=None)
    rdao.get_result.return_value = existing
    rdao.has_scores.return_value = True
    rdao.is_scoring_done.return_value = False

    mdao = MagicMock()
    mdao.get_match.return_value = _match()
    svc = _svc(result_dao=rdao, match_dao=mdao)
    set_web_search_fn(lambda q: None)

    with patch.object(result_service, "enqueue_scoring", return_value=True) as es:
        out = svc.collect_result("mid-1")

    rdao.update_mvp.assert_not_called()
    es.assert_called_once()
    assert out.home_goals == 2
    assert out.mvp_name is None


def test_notify_members_without_prediction():
    """Todos los miembros del grupo, aunque no hayan predicho el partido."""
    groups = MagicMock()
    groups.list_groups_for_broadcast.return_value = [
        {"group_id": "global", "status": "ACTIVE", "name": "Global"},
    ]
    groups.list_member_user_ids.return_value = ["u_no_pred"]
    groups.get_group.return_value = {"name": "Global"}
    users = MagicMock()
    users.get_profile.return_value = {
        "notifications_enabled": True,
        "tg_chat_id": 999,
    }
    preds = MagicMock()

    svc = _svc(group_dao=groups, user_dao=users, prediction_dao=preds)
    by_user = svc._notify_recipients_by_user()
    assert by_user == {"u_no_pred": ["global"]}


def test_one_message_per_user_multiple_groups():
    """Mismo usuario en 2 grupos → una entrada en by_user, no dos envíos."""
    groups = MagicMock()
    groups.list_groups_for_broadcast.return_value = [
        {"group_id": "g1", "status": "ACTIVE"},
        {"group_id": "g2", "status": "ACTIVE"},
    ]
    groups.list_member_user_ids.side_effect = lambda gid: ["u1"]
    groups.get_group.side_effect = lambda gid: {
        "name": "Scaloneta" if gid == "g1" else "Putiskys"
    }

    svc = _svc(group_dao=groups)
    by_user = svc._notify_recipients_by_user()
    assert by_user == {"u1": ["g1", "g2"]}


def test_sc06_notify_all_groups_count():
    from src.services.result_notification import format_match_result_message

    match = _match()
    result = MatchResult(
        home_goals=2,
        away_goals=0,
        mvp_name="Messi",
        scorers={"Messi": 1},
        var_used=False,
    )
    msg = format_match_result_message(match, result)
    assert "RESULTADO FINAL" in msg
    assert "2 - 0" in msg
    assert "Messi" in msg  # en goleadores, no como MVP
    assert "Jugador del partido" not in msg
    assert "Intervención VAR: No" in msg


def test_result_dao_is_complete():
    dao = ResultDAO.__new__(ResultDAO)
    dao.get_raw = MagicMock(return_value={
        "result_90min_home": 2,
        "mvp_name": "X",
    })
    assert dao.is_complete("m1") is True
    dao.get_raw.return_value = {"result_90min_home": 2, "mvp_name": None}
    assert dao.is_complete("m1") is False


def test_heuristic_parse_score():
    raw = "Argentina 2-0 Argelia resultado final Mundial 2026"
    r = parse_web_result(raw, _match())
    assert r is not None
    assert r.home_goals == 2
    assert r.away_goals == 0


def test_find_incomplete_excludes_complete():
    mdao = MagicMock()
    mdao.list_matches_estimated_finished.return_value = [_match(match_id="a")]
    rdao = MagicMock()
    rdao.is_complete.side_effect = lambda mid: mid == "a"

    svc = _svc(result_dao=rdao, match_dao=mdao)
    assert svc.find_incomplete_match_ids() == []
