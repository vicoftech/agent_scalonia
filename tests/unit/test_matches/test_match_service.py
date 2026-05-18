"""tests/unit/test_matches — fixture y consultas."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.fixtures.match_fixture_builder import build_group_stage_matches, match_uuid
from src.services.match_service import MatchService, normalize_team_code


def _sample_matches() -> list[dict]:
    return [
        {
            "match_id": match_uuid(1),
            "match_number": 1,
            "home_team": "MEX",
            "away_team": "RSA",
            "phase": "GROUP",
            "group_letter": "A",
            "kickoff_utc": "2026-06-11T19:00:00Z",
            "city": "Mexico City",
            "venue": "Azteca",
            "country": "MEX",
            "status": "SCHEDULED",
        },
        {
            "match_id": match_uuid(2),
            "match_number": 2,
            "home_team": "ARG",
            "away_team": "ALG",
            "phase": "GROUP",
            "group_letter": "J",
            "kickoff_utc": "2026-06-12T22:00:00Z",
            "city": "Miami",
            "venue": "Hard Rock",
            "country": "USA",
            "status": "SCHEDULED",
        },
    ]


def test_build_group_stage_has_72_matches():
    rows = build_group_stage_matches()
    assert len(rows) == 72
    assert rows[0]["match_number"] == 1
    assert rows[-1]["match_number"] == 72


def test_normalize_team_alias():
    assert normalize_team_code("Argentina") == "ARG"
    assert normalize_team_code("ARG") == "ARG"


def test_search_by_team():
    dao = MagicMock()
    dao.list_matches.return_value = _sample_matches()
    svc = MatchService(dao)
    found = svc.search(team="Argentina", limit=10)
    assert len(found) == 1
    assert found[0]["home_team"] == "ARG"


def test_search_by_group():
    dao = MagicMock()
    dao.list_matches.return_value = _sample_matches()
    svc = MatchService(dao)
    found = svc.search(group_letter="A", limit=10)
    assert len(found) == 1
    assert found[0]["home_team"] == "MEX"


def test_match_tool_get():
    from unittest.mock import patch

    from agent.tools.match_tool import match_tool

    dao = MagicMock()
    dao.get_by_match_number.return_value = _sample_matches()[0]
    svc = MatchService(dao)

    with patch("src.services.match_service.MatchService", return_value=svc):
        out = match_tool(action="get", match_number=1)
    assert "MEX vs RSA" in out
