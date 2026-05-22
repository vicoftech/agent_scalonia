from src.services.prediction_score_parse import looks_like_simple_score, parse_simple_score
from src.services.team_flags import flag_emoji, format_team


def test_parse_simple_score_formats():
    assert parse_simple_score("2-1") == (2, 1)
    assert parse_simple_score("3:0") == (3, 0)
    assert parse_simple_score(" 0 1 ") == (0, 1)


def test_looks_like_simple_score():
    assert looks_like_simple_score("0:1") is True
    assert looks_like_simple_score("cuándo juega argentina") is False


def test_flag_argentina():
    assert "🇦🇷" in format_team("ARG")
