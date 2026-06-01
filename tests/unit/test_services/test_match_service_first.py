"""first_tournament_match en MatchService."""
from unittest.mock import MagicMock

from src.services.match_service import MatchService


def test_first_tournament_match_by_kickoff():
    dao = MagicMock()
    dao.list_matches.return_value = [
        {"match_number": 2, "kickoff_utc": "2026-06-11T19:00:00Z"},
        {"match_number": 1, "kickoff_utc": "2026-06-11T16:00:00Z"},
    ]
    first = MatchService(dao=dao).first_tournament_match()
    assert first["match_number"] == 1
