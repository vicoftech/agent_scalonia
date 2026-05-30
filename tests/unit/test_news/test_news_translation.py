"""Tests traducción noticias — SPEC-2026-046."""
from __future__ import annotations

from src.services.news_translation import (
    _extract_json,
    _fields_from_json,
    should_translate,
    set_translate_fn,
    translate_if_english,
)


def test_should_translate_bbc_headline():
    assert should_translate(
        "Adams & Robinson in US squad for World Cup - BBC",
        "https://www.bbc.com/sport/football/articles/abc",
    )


def test_extract_json_from_markdown_fence():
    raw = '```json\n{"headline":"Sorteo","summary":"FIFA anunció grupos."}\n```'
    data = _extract_json(raw)
    assert data is not None
    assert _fields_from_json(data) == ("Sorteo", "FIFA anunció grupos.")


def test_translate_uses_injected_fn():
    set_translate_fn(lambda h, s: (f"ES:{h}", f"ES:{s}"))
    h, s = translate_if_english(
        "World Cup 2026 draw",
        "FIFA announced groups.",
        article_url="https://www.fifa.com/en/articles/x",
    )
    assert h.startswith("ES:")
    set_translate_fn(None)
