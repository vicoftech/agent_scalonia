"""SPEC-2026-051 — agregador y gate admin de resultados."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.match_result import MatchResult
from src.services.result_parser import detect_in_play_signals
from src.services.result_source_aggregator import (
    AggregatedCandidate,
    ResultSourceAggregator,
    set_web_search_fn,
)
from src.services.result_gate import is_admin_gate_enabled


@pytest.fixture(autouse=True)
def _reset_web_search():
    set_web_search_fn(None)
    yield
    set_web_search_fn(None)


def _match(**kwargs) -> dict:
    kickoff = datetime.now(timezone.utc) - timedelta(hours=3)
    base = {
        "match_id": "mid-051",
        "home_team": "MEX",
        "away_team": "RSA",
        "phase": "GROUP",
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
    }
    base.update(kwargs)
    return base


def test_detect_in_play_signals():
    assert detect_in_play_signals("México 1-0 en vivo minuto 67")
    assert not detect_in_play_signals("Resultado final: México 2-0 Sudáfrica")


def test_aggregator_consensus_two_of_three():
    texts = {
        "tavily:score": "MEX 2-0 RSA resultado final Copa Mundial 2026",
        "tavily:events": "MEX vs RSA 2-0 tarjetas rojas VAR usado",
        "tavily:mvp": "jugador del partido MEX vs RSA MVP Julián Quiñones",
    }

    def fake_search(q: str) -> str:
        for key, text in texts.items():
            if key.split(":")[1] in q.lower() or key in q:
                return text
        if "marcador" in q:
            return texts["tavily:score"]
        if "var" in q.lower():
            return texts["tavily:events"]
        return texts["tavily:mvp"]

    set_web_search_fn(fake_search)
    agg = ResultSourceAggregator()
    out = agg.aggregate(_match())
    assert out is not None
    assert out.proposed.home_goals == 2
    assert out.proposed.away_goals == 0
    assert out.consensus_score >= 0.5
    assert len(out.snapshots) >= 3


def test_aggregator_rejects_in_play_without_api():
    set_web_search_fn(lambda q: "MEX 1-0 RSA en vivo minuto 80")
    agg = ResultSourceAggregator()
    assert agg.aggregate(_match()) is None


def test_aggregator_prefers_api_on_disagreement():
    api = MatchResult(home_goals=2, away_goals=0, source="api_football")
    set_web_search_fn(lambda q: "MEX 1-1 RSA resultado final")
    agg = ResultSourceAggregator()
    out = agg.aggregate(_match(), api_result=api)
    assert out is not None
    assert out.proposed.home_goals == 2
    assert any("API-Football discrepa" in w for w in out.warnings)


def test_collect_result_does_not_publish_with_gate_on():
    from src.services.result_service import ResultService

    rdao = MagicMock()
    rdao.get_result.return_value = None
    mdao = MagicMock()
    mdao.get_match.return_value = _match()

    with patch.dict("os.environ", {"RESULT_ADMIN_GATE_ENABLED": "true"}):
        with patch(
            "src.services.result_admin_service.ResultAdminService.propose_result"
        ) as propose:
            propose.return_value = AggregatedCandidate(
                match_id="mid-051",
                proposed=MatchResult(home_goals=2, away_goals=0),
                consensus_score=0.9,
            )
            svc = ResultService(result_dao=rdao, match_dao=mdao)
            out = svc.collect_result("mid-051")
            assert out.home_goals == 2
            propose.assert_called_once()
            rdao.save_result.assert_not_called()


def test_admin_confirm_publishes_and_enqueues_scoring():
    from src.services.result_admin_service import ResultAdminService

    rdao = MagicMock()
    rdao.get_candidate_raw.return_value = {
        "match_id": "mid-051",
        "approval_status": "PENDING_REVIEW",
        "proposed_result": MatchResult(home_goals=2, away_goals=0).to_dict(),
        "source_snapshots": [],
    }
    rdao.has_scores.return_value = False
    rdao.get_publish_version.return_value = 0
    mdao = MagicMock()
    mdao.get_match.return_value = _match()
    svc_mock = MagicMock()
    svc_mock.notify_match_result.return_value = 3

    auth = MagicMock()
    auth.is_admin_global.return_value = True

    with patch("src.services.result_admin_service.enqueue_scoring") as eq:
        admin = ResultAdminService(
            results=rdao,
            matches=mdao,
            auth=auth,
            result_service=svc_mock,
        )
        out = admin.confirm_and_publish("mid-051", "admin-1")
        assert out.published
        assert out.notified_users == 3
        eq.assert_called_once()


def test_non_admin_confirm_rejected():
    from src.services.result_admin_service import ResultAdminService

    auth = MagicMock()
    auth.is_admin_global.return_value = False
    admin = ResultAdminService(auth=auth)
    with pytest.raises(PermissionError):
        admin.confirm_and_publish("mid-051", "user-1")


def test_gate_default_on():
    with patch.dict("os.environ", {}, clear=True):
        # default true when unset
        assert is_admin_gate_enabled()

    with patch.dict("os.environ", {"RESULT_ADMIN_GATE_ENABLED": "false"}):
        assert not is_admin_gate_enabled()
