from src.fixtures.wc2026_api import api_row_to_match, build_fixture_document


def test_api_row_group_match():
    row = {
        "id": 1,
        "match_number": 1,
        "home_team": "Mexico",
        "home_team_code": "MEX",
        "away_team": "South Africa",
        "away_team_code": "RSA",
        "stadium": "Estadio Azteca",
        "stadium_city": "Mexico City",
        "stadium_country": "Mexico",
        "kickoff_utc": "2026-06-11T19:00:00.000Z",
        "round": "group",
        "group_name": "A",
        "status": "scheduled",
    }
    m = api_row_to_match(row)
    assert m["match_number"] == 1
    assert m["home_team"] == "MEX"
    assert m["away_team"] == "RSA"
    assert m["phase"] == "GROUP"
    assert m["group_letter"] == "A"
    assert m["country"] == "MEX"
    assert m["status"] == "SCHEDULED"
    assert m["kickoff_utc"] == "2026-06-11T19:00:00Z"


def test_api_row_knockout():
    row = {
        "id": 73,
        "match_number": 73,
        "home_team_code": "TBD",
        "away_team_code": "TBD",
        "round": "R32",
        "kickoff_utc": "2026-07-01T20:00:00Z",
        "status": "scheduled",
    }
    m = api_row_to_match(row)
    assert m["phase"] == "ROUND_OF_32"
    assert m["group_letter"] is None


def test_build_fixture_document_sorts():
    doc = build_fixture_document(
        [
            {"id": 2, "match_number": 2, "round": "group", "group_name": "A", "status": "scheduled"},
            {"id": 1, "match_number": 1, "round": "group", "group_name": "A", "status": "scheduled"},
        ]
    )
    assert doc["match_count"] == 2
    assert doc["matches"][0]["match_number"] == 1
