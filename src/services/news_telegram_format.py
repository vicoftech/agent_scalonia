"""Formato caption HTML y teclado inline — SPEC-2026-046."""
from __future__ import annotations

import html
import re
from typing import Any

from src.services.news_read_token import build_read_url

MAX_CAPTION = 1024
CATEGORY_EMOJI = {
    "Mundial 2026": "🏆",
    "Selecciones": "⚽",
    "Fixture": "📅",
    "Lesiones": "🩹",
    "default": "📰",
}


def _emoji_for(category: str, subcategory: str) -> str:
    for key, em in CATEGORY_EMOJI.items():
        if key.lower() in (category or "").lower() or key.lower() in (subcategory or "").lower():
            return em
    return CATEGORY_EMOJI["default"]


def escape_html(text: str) -> str:
    return html.escape(text or "", quote=False)


def format_news_caption(item: dict[str, Any], *, include_footer: bool = True) -> str:
    emoji = _emoji_for(str(item.get("category") or ""), str(item.get("subcategory") or ""))
    headline = escape_html(str(item.get("headline") or ""))
    summary = escape_html(str(item.get("summary") or ""))
    category = escape_html(str(item.get("category") or "Mundial 2026"))
    subcategory = escape_html(str(item.get("subcategory") or "#Noticias"))
    source_label = escape_html(str(item.get("source_label") or "Web"))
    score = int(item.get("relevance_score") or 0)
    hashtags = "#Mundial2026 #ProdeBot #Noticias"
    if item.get("source_type") == "ADMIN":
        headline = f"📌 {headline}"
    body = (
        f"<b>{emoji} {headline}</b>\n\n"
        f"{summary}\n\n"
        f"<b>Categoría:</b> {category}\n"
        f"<b>Subcategoría:</b> {subcategory}\n"
        f"<b>Fuente de datos:</b> {source_label}\n"
        f"<b>Relevancia:</b> {score}/100\n\n"
        f"{hashtags}"
    )
    if include_footer:
        body += "\n\n🌐 Mundial 2026 — General"
    if len(body) > MAX_CAPTION:
        excess = len(body) - MAX_CAPTION + 3
        summary_trim = summary[: max(0, len(summary) - excess)]
        body = body.replace(summary, summary_trim.rstrip() + "...")
        if len(body) > MAX_CAPTION:
            body = body[: MAX_CAPTION - 3] + "..."
    return body


def build_news_keyboard(
    news_id: str,
    *,
    user_id: str,
    like_count: int,
    article_url: str | None = None,
) -> dict[str, Any]:
    read_url = build_read_url(news_id, user_id, article_url=article_url)
    return {
        "inline_keyboard": [
            [
                {"text": "🔗 Leer más", "url": read_url},
                {"text": f"👍 {like_count}", "callback_data": f"news:like:{news_id}"},
            ]
        ]
    }


def domain_from_url(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url or "")
    return (m.group(1) if m else "web").lower().removeprefix("www.")
