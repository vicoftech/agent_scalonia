"""Tests curación noticias — SPEC-2026-046."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.news_curation_service import (
    NewsCurationService,
    headline_fingerprint,
)
from src.services.news_translation import (
    looks_english,
    set_translate_fn,
    should_translate,
    translate_if_english,
)


def test_headline_fingerprint_stable():
    a = headline_fingerprint("Argentina squad announced for World Cup 2026")
    b = headline_fingerprint("Argentina squad announced for World Cup 2026!")
    assert a == b


def test_curate_fresh_merges_queries_and_picks_tier1():
    news = MagicMock()
    news.is_url_published.return_value = False
    news.list_published_on_date.return_value = []
    svc = NewsCurationService(news=news)

    rows = [
        {
            "url": "https://www.ole.com.ar/mundial/argentina-plantel",
            "title": "Argentina confirmó el plantel para el Mundial 2026",
            "content": "La selección argentina presentó la lista final.",
        },
        {
            "url": "https://www.fifa.com/en/articles/world-cup-2026-draw",
            "title": "World Cup 2026 draw sets groups for tournament",
            "content": "FIFA announced the final group stage matchups for 2026.",
        },
    ]

    with (
        patch("src.services.news_curation_service.is_tavily_configured", return_value=True),
        patch("src.services.news_curation_service._search_tavily", return_value=rows),
        patch(
            "src.services.news_curation_service.translate_if_english",
            side_effect=lambda h, s, **_: (h, s),
        ),
    ):
        out = svc.curate_fresh()

    assert out is not None
    assert "fifa.com" in out["article_url"]
    assert out["relevance_score"] >= out.get("relevance_score", 0)


def test_curate_fresh_skips_duplicate_headline_fp():
    news = MagicMock()
    news.is_url_published.return_value = False
    fp = headline_fingerprint("World Cup 2026 draw sets groups for tournament")
    news.list_published_on_date.return_value = [
        {"headline": "World Cup 2026 draw sets groups for tournament", "url_hash": "x"}
    ]

    svc = NewsCurationService(news=news)
    rows = [
        {
            "url": "https://www.fifa.com/en/articles/world-cup-2026-draw-v2",
            "title": "World Cup 2026 draw sets groups for tournament",
            "content": "Same story different url.",
        },
    ]

    with (
        patch("src.services.news_curation_service.is_tavily_configured", return_value=True),
        patch("src.services.news_curation_service._search_tavily", return_value=rows),
    ):
        out = svc.curate_fresh(exclude_headline_fps={fp})

    assert out is None


def test_curate_fresh_returns_none_without_tavily():
    with patch("src.services.news_curation_service.is_tavily_configured", return_value=False):
        assert NewsCurationService().curate_fresh() is None


def test_should_translate_fifa_url_even_with_mixed_summary():
    assert should_translate(
        "World Cup 2026 draw sets groups",
        "https://www.fifa.com/en/articles/world-cup-draw",
    )
    # Resumen con palabras sueltas en español no debe bloquear (solo mira titular)
    assert should_translate(
        "FIFA World Cup 2026 groups confirmed",
        "https://www.fifa.com/en/news",
    )


def test_looks_english_and_translate():
    assert looks_english("World Cup 2026 draw sets groups for tournament")
    assert not looks_english("Argentina confirmó el plantel para el Mundial 2026")

    set_translate_fn(lambda h, s: ("Sorteo del Mundial 2026", "FIFA anunció los grupos."))
    h, s = translate_if_english(
        "World Cup 2026 draw sets groups",
        "FIFA announced the groups.",
    )
    assert h == "Sorteo del Mundial 2026"
    assert "FIFA" in s
    set_translate_fn(None)


def test_looks_english_fifa_headline():
    assert looks_english("FIFA World Cup 2026: Everything you need to know")
