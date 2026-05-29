"""Tests formato caption — SPEC-2026-046."""
from __future__ import annotations

import os

from src.services.news_telegram_format import build_news_keyboard, format_news_caption


def test_caption_escapes_html():
    item = {
        "headline": "Messi <gol> & festejo",
        "summary": "Resumen breve.",
        "category": "Mundial 2026",
        "subcategory": "#Selecciones",
        "source_label": "Web · ole.com.ar",
        "relevance_score": 88,
    }
    cap = format_news_caption(item)
    assert "&lt;gol&gt;" in cap
    assert "<b>" in cap


def test_keyboard_direct_article_when_tracking_off():
    os.environ["NEWS_REDIRECT_ENABLED"] = "false"
    kb = build_news_keyboard(
        "nid-1",
        user_id="u1",
        like_count=3,
        article_url="https://www.ole.com.ar/nota-ejemplo",
    )
    row = kb["inline_keyboard"][0]
    assert row[0]["url"] == "https://www.ole.com.ar/nota-ejemplo"
    assert row[1]["callback_data"] == "news:like:nid-1"


def test_keyboard_tracking_when_enabled():
    os.environ["NEWS_REDIRECT_ENABLED"] = "true"
    os.environ["NEWS_REDIRECT_BASE_URL"] = "https://api.example.com"
    os.environ["NEWS_REDIRECT_SECRET"] = "test-secret-046"
    kb = build_news_keyboard(
        "nid-1",
        user_id="u1",
        like_count=3,
        article_url="https://www.ole.com.ar/nota-ejemplo",
    )
    row = kb["inline_keyboard"][0]
    assert row[0]["url"].startswith("https://api.example.com/news/r/nid-1")
