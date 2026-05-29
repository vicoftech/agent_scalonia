"""Tests curación noticias — SPEC-2026-046."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.news_curation_service import NewsCurationService


def test_curate_fresh_tries_next_slot_when_first_empty():
    svc = NewsCurationService(news=MagicMock())
    svc._news.is_url_published.return_value = False
    mock_curate = MagicMock(
        side_effect=[None, {"headline": "Hit", "article_url": "https://fifa.com/x"}]
    )
    with (
        patch("src.services.news_curation_service.is_tavily_configured", return_value=True),
        patch.object(svc, "curate_for_slot", mock_curate),
    ):
        out = svc.curate_fresh()
    assert out is not None
    assert out["headline"] == "Hit"
    assert mock_curate.call_count == 2


def test_curate_fresh_returns_none_without_tavily():
    with patch("src.services.news_curation_service.is_tavily_configured", return_value=False):
        assert NewsCurationService().curate_fresh() is None
