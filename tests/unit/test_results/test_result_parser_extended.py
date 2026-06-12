"""Parser heurístico — eventos extendidos (ISSUE-2026-050)."""
from __future__ import annotations

from src.services.result_parser import parse_web_result

_MATCH = {"home_team": "MEX", "away_team": "RSA", "phase": "GROUP"}


def test_mex_rsa_extended_from_fixture():
    from src.testing.fake_web_search import load_web_search_fixture

    raw = load_web_search_fixture()["MEX_RSA"]
    r = parse_web_result(raw, _MATCH)
    assert r is not None
    assert r.home_goals == 2
    assert r.away_goals == 0
    assert r.red_cards == 3
    assert r.var_used is True
    assert r.goal_before_5min is False
    assert r.penalty_scored is False
    assert r.penalty_saved is False


def test_mex_rsa_extended_from_espn_style_snippet():
    raw = """
    Mexico beats South Africa 2-0 in World Cup opener after 3 red cards.
    Julián Quiñones scored the first goal of the tournament in the ninth minute.
    Themba Zwane was sent off following a VAR review.
    Sphephelo Sithole straight red card. César Montes third red card in stoppage time.
    Raúl Jiménez doubled the lead. What was almost a penalty turned into a goal kick.
    """
    r = parse_web_result(raw, _MATCH)
    assert r is not None
    assert r.home_goals == 2
    assert r.red_cards == 3
    assert r.var_used is True
    assert r.goal_before_5min is False
    assert r.penalty_scored is False
