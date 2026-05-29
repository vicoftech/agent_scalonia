"""SPEC-2026-045 — DAO, JSON, match brief service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fixtures.mundial2026_groups import all_world_cup_team_codes
from src.services.brief_json import extract_json_object, normalize_team_brief, truncate_markdown
from src.services.match_brief_service import (
    append_match_brief_context,
    should_regenerate_match_brief,
)


def test_all_world_cup_teams_count():
    codes = all_world_cup_team_codes()
    assert len(codes) == 48
    assert "MEX" in codes
    assert "ARG" in codes


def test_extract_json_from_fence():
    raw = '```json\n{"team_code":"ARG","brief_markdown":"x"}\n```'
    data = extract_json_object(raw)
    assert data["team_code"] == "ARG"


def test_truncate_markdown():
    assert len(truncate_markdown("a" * 3000, limit=100)) == 100


def test_should_regenerate_skips_finished():
    assert not should_regenerate_match_brief({"status": "FINISHED"})
    assert should_regenerate_match_brief({"status": "SCHEDULED"})


def test_append_match_brief_context_inserts_block():
    lines: list[str] = ["header"]
    brief = {
        "ia_prediction_line": "Dado el análisis previo me inclino por México como ganador del partido.",
        "home_team": "MEX",
        "away_team": "RSA",
        "home_strengths": ["Ataque"],
        "home_weaknesses": [],
        "away_strengths": [],
        "away_weaknesses": [],
    }
    with patch("src.services.match_brief_service.MatchBriefService") as svc:
        svc.return_value.get_match_brief.return_value = brief
        svc.return_value.format_ia_prediction_for_ui.return_value = (
            "── Contexto IA ──\n🤖 IA Prediction: test"
        )
        append_match_brief_context(lines, "match-1")
    assert any("Contexto IA" in ln for ln in lines)


def test_orchestrator_team_phase_mock():
    from src.services.brief_orchestrator import BriefOrchestrator

    team_dao = MagicMock()
    match_dao = MagicMock()
    job_ctrl = MagicMock()
    job_ctrl.is_processed.return_value = False

    def fake_invoke(prompt: str, session_id: str) -> str:
        return (
            '{"team_code":"MEX","brief_markdown":"## México","roster":[],"recent_record":"10G"}'
        )

    orch = BriefOrchestrator(
        invoke_agent=fake_invoke,
        team_briefs=team_dao,
        match_briefs=MagicMock(),
        matches=match_dao,
        job_ctrl=job_ctrl,
    )
    result = orch.run(team_filter="MEX", force=True)
    assert result["status"] == "OK"
    team_dao.put_current.assert_called()
