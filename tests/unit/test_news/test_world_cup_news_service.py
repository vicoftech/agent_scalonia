"""Tests servicio noticias — SPEC-2026-046."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.world_cup_news_service import WorldCupNewsService


def test_pre_slot_skipped_when_already_processed():
    news = MagicMock()
    job = MagicMock()
    job.is_processed.return_value = True
    matches = MagicMock()
    matches.list_matches.return_value = [
        {"kickoff_utc": "2026-08-01T19:00:00+00:00", "status": "SCHEDULED", "home_team": "A", "away_team": "B"}
    ]
    svc = WorldCupNewsService(news=news, job_ctrl=job, matches=matches)
    with patch("src.services.world_cup_news_service.sched.pre_slot_window_ok", return_value=True):
        out = svc.run_pre_slot("MORNING", force=False)
    assert out["status"] == "SKIPPED"
    assert out["reason"] == "already_processed"
