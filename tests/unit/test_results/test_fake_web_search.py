"""Fake web_search y mock API poller."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.clients.api_football_mock import MockApiFootballClient
from src.models.match_result import MatchResult
from src.services.result_poller_service import ResultPollerService
from src.services.result_service import ResultService, set_web_search_fn
from src.testing.fake_web_search import build_fake_web_search_fn, load_web_search_fixture


@pytest.fixture(autouse=True)
def _reset_web_search():
    set_web_search_fn(None)
    yield
    set_web_search_fn(None)


def test_load_web_search_fixture_has_mex_rsa():
    data = load_web_search_fixture()
    assert "MEX_RSA" in data
    assert "2-0" in data["MEX_RSA"] or "2-0" in data["MEX_RSA"].replace(" ", "")


def test_fake_web_search_matches_teams_in_query():
    fn = build_fake_web_search_fn(
        fixture={"MEX_RSA": "MEX 2-0 RSA final"},
        default_response=None,
    )
    assert fn("MEX vs RSA resultado final") == "MEX 2-0 RSA final"
    assert fn("otro partido") is None


def test_mock_api_fixture_mex_rsa():
    client = MockApiFootballClient()
    fx = client.get_fixture(2)
    assert fx is not None
    assert fx.home_team == "MEX"
    assert fx.status == "FT"
    assert fx.home_goals == 2


def test_poller_dry_run_finds_match_by_teams():
    mdao = MagicMock()
    mdao.find_by_teams.return_value = {
        "match_id": "mid-mex",
        "home_team": "MEX",
        "away_team": "RSA",
        "phase": "GROUP",
    }
    rdao = MagicMock()
    rdao.is_scoring_done.return_value = False
    rdao.has_scores.return_value = False

    svc = ResultPollerService(
        api_client=MockApiFootballClient(),
        match_dao=mdao,
        result_dao=rdao,
        result_service=MagicMock(),
    )
    out = svc.poll_once(api_match_ids=[2], dry_run=True)
    assert out["processed"] == ["MEX_RSA"]
    mdao.find_by_teams.assert_not_called()
    rdao.save_result.assert_not_called()


def test_poller_saves_and_calls_collector():
    mdao = MagicMock()
    mdao.find_by_teams.return_value = {
        "match_id": "mid-mex",
        "home_team": "MEX",
        "away_team": "RSA",
        "phase": "GROUP",
    }
    rdao = MagicMock()
    rdao.is_scoring_done.return_value = False
    rdao.has_scores.return_value = False
    rdao.save_result.return_value = True

    collector = MagicMock()
    collector.collect_result.return_value = MatchResult(
        home_goals=2, away_goals=0, mvp_name="X"
    )

    svc = ResultPollerService(
        api_client=MockApiFootballClient(),
        match_dao=mdao,
        result_dao=rdao,
        result_service=collector,
    )
    out = svc.poll_once(api_match_ids=[2], dry_run=False)
    assert "mid-mex" in out["processed"]
    rdao.save_result.assert_called_once()
    collector.collect_result.assert_called_once_with(
        "mid-mex", telegram_direct=False, force_notify=False
    )


def test_poller_handler_mock_event():
    from infrastructure.lambdas.result_poller import handler

    with patch("src.services.result_poller_service.ResultPollerService") as poller_cls:
        poller_cls.return_value.poll_once.return_value = {
            "fixtures": 1,
            "processed": [],
            "skipped": [],
        }
        resp = handler.handler(
            {"trigger": "fixture", "api_match_id": 2, "dry_run": True},
            None,
        )
    assert resp["status"] == "OK"
    poller_cls.return_value.poll_once.assert_called_once()


def test_collect_with_fake_web_search_parses_score():
    mdao = MagicMock()
    mdao.get_match.return_value = {
        "match_id": "mid-1",
        "home_team": "MEX",
        "away_team": "RSA",
        "phase": "GROUP",
        "kickoff_utc": "2020-01-01T12:00:00Z",
    }
    rdao = MagicMock()
    rdao.get_result.return_value = None

    set_web_search_fn(
        build_fake_web_search_fn(fixture={"MEX_RSA": "México 2-0 Sudáfrica resultado final"})
    )

    with patch.object(ResultService, "_save_and_notify", return_value=MatchResult(home_goals=2, away_goals=0)):
        svc = ResultService(result_dao=rdao, match_dao=mdao)
        got = svc._fetch_via_web_search(mdao.get_match.return_value)

    assert got is not None
    assert got.home_goals == 2
    assert got.away_goals == 0
