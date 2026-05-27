"""Nombres completos de equipos en vistas de detalle."""
from src.services.prediction_service import PredictionService
from src.services.team_flags import format_match_heading, resolve_team_display_name


def test_resolve_uses_match_name_when_present():
    match = {
        "home_team": "KOR",
        "away_team": "CZE",
        "home_team_name": "Korea Republic",
        "away_team_name": "Czechia",
    }
    assert resolve_team_display_name("KOR", match=match, side="home") == "Korea Republic"
    assert resolve_team_display_name("CZE", match=match, side="away") == "Czechia"


def test_resolve_falls_back_to_catalog():
    assert resolve_team_display_name("MEX") == "México"
    assert resolve_team_display_name("RSA") == "Sudáfrica"


def test_format_match_heading_full_names():
    text = format_match_heading(
        {"home_team": "KOR", "away_team": "CZE", "home_team_name": "", "away_team_name": ""}
    )
    assert "Corea del Sur" in text
    assert "República Checa" in text
    assert "KOR vs" not in text


def test_prediction_service_format_match_title_full():
    svc = PredictionService()
    title = svc.format_match_title(
        {"home_team": "ARG", "away_team": "ALG"},
        full_names=True,
    )
    assert "Argentina" in title
    assert "Argelia" in title
