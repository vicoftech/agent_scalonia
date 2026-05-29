"""Curación automática de noticias — SPEC-2026-046."""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from src.dao.dynamo.news_dao import NewsDAO, url_hash
from src.services.news_telegram_format import domain_from_url
from src.web.tavily_search import get_tavily_api_key, is_tavily_configured

logger = logging.getLogger(__name__)

NEWS_WHITELIST_DOMAINS = [
    "fifa.com",
    "es.fifa.com",
    "ole.com.ar",
    "espn.com.ar",
    "espndeportes.espn.com",
    "deportes.lanacion.com.ar",
    "clarin.com",
    "infobae.com",
    "conmebol.com",
    "uefa.com",
]

SLOT_QUERIES = {
    "MORNING": "site:fifa.com Mundial 2026 noticias selecciones",
    "EVENING": "site:ole.com.ar Mundial 2026 selección argentina noticias",
    "PRE_MATCHDAY": "Mundial 2026 partidos hoy noticias site:espn.com.ar",
    "POST_MATCHDAY": "Mundial 2026 resultados análisis site:ole.com.ar",
    "ADMIN": (
        "Mundial Copa del Mundo 2026 noticias hoy selecciones argentina "
        "convocatoria lesiones última hora"
    ),
}

# Orden al buscar bajo demanda (/noticia sin URL)
ADMIN_CURATE_SLOTS: tuple[str, ...] = (
    "ADMIN",
    "EVENING",
    "MORNING",
    "PRE_MATCHDAY",
    "POST_MATCHDAY",
)


def _domain_allowed(url: str) -> bool:
    host = domain_from_url(url)
    return any(host == d or host.endswith("." + d) or d in host for d in NEWS_WHITELIST_DOMAINS)


def _score_candidate(title: str, content: str, url: str, *, slot: str) -> int:
    text = f"{title} {content}".lower()
    score = 50
    if "2026" in text or "mundial" in text:
        score += 20
    if "selección" in text or "seleccion" in text:
        score += 10
    if slot in ("PRE_MATCHDAY", "POST_MATCHDAY") and ("partido" in text or "grupo" in text):
        score += 15
    if "fifa.com" in url:
        score += 10
    return min(100, score)


def _search_tavily(query: str, *, max_results: int = 8) -> list[dict[str, Any]]:
    api_key = get_tavily_api_key()
    if not api_key:
        return []
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_domains": NEWS_WHITELIST_DOMAINS,
                "topic": "news",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return list(resp.json().get("results") or [])
    except Exception:
        logger.exception("tavily news search failed")
        return []


def _normalize_summary(content: str, *, max_sentences: int = 4) -> str:
    text = re.sub(r"\s+", " ", (content or "").strip())
    if not text:
        return "Sin resumen disponible."
    parts = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(parts[:max_sentences]).strip()
    return summary[:600] if summary else text[:600]


def _pick_subcategory(title: str, content: str) -> str:
    blob = f"{title} {content}".lower()
    if "lesión" in blob or "lesion" in blob:
        return "#Lesiones"
    if "fixture" in blob or "grupo" in blob or "calendario" in blob:
        return "#Fixture"
    if "selección" in blob or "seleccion" in blob or "plantel" in blob:
        return "#Selecciones"
    return "#Noticias"


class NewsCurationService:
    def __init__(self, *, news: NewsDAO | None = None):
        self._news = news or NewsDAO()

    def curate_for_slot(
        self,
        slot: str,
        *,
        exclude_url_hashes: set[str] | None = None,
        run_date: str | None = None,
    ) -> dict[str, Any] | None:
        if not is_tavily_configured():
            logger.warning("Tavily not configured — cannot curate news")
            return None
        query = SLOT_QUERIES.get(slot, SLOT_QUERIES["MORNING"])
        results = _search_tavily(query)
        exclude = exclude_url_hashes or set()
        candidates: list[dict[str, Any]] = []
        for row in results:
            url = (row.get("url") or "").strip()
            if not url or not _domain_allowed(url):
                continue
            h = url_hash(url)
            if h in exclude or self._news.is_url_published(url):
                continue
            title = (row.get("title") or "").strip()
            content = (row.get("content") or "").strip()
            if len(title) < 12:
                continue
            domain = domain_from_url(url)
            source_label = f"Web · {domain}"
            if "fifa.com" in domain:
                source_label = "RSS · fifa.com"
            candidates.append(
                {
                    "headline": title,
                    "summary": _normalize_summary(content),
                    "article_url": url,
                    "url_hash": h,
                    "image_url": row.get("image") or row.get("og_image") or "",
                    "category": "Mundial 2026",
                    "subcategory": _pick_subcategory(title, content),
                    "source_label": source_label,
                    "relevance_score": _score_candidate(title, content, url, slot=slot),
                }
            )
        if not candidates:
            return None
        candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
        best = candidates[0]
        if run_date:
            best["run_date"] = run_date
        return best

    def curate_fresh(
        self,
        *,
        exclude_url_hashes: set[str] | None = None,
        slots: tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        """Busca una noticia nueva (admin /noticia sin URL). Prueba varios queries."""
        if not is_tavily_configured():
            logger.warning("Tavily not configured — cannot curate_fresh")
            return None
        order = slots or ADMIN_CURATE_SLOTS
        exclude = exclude_url_hashes or set()
        for slot in order:
            hit = self.curate_for_slot(slot, exclude_url_hashes=exclude)
            if hit:
                return hit
        return None

    def fetch_og_article(self, url: str) -> dict[str, Any] | None:
        """Extracción simple para /noticia admin (título + descripción)."""
        try:
            resp = httpx.get(
                url,
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "ProdeBot/1.0"},
            )
            resp.raise_for_status()
            html_text = resp.text
        except Exception:
            logger.exception("fetch_og_article failed url=%s", url[:60])
            return None
        title_m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html_text, re.I)
        if not title_m:
            title_m = re.search(r"<title>([^<]+)</title>", html_text, re.I)
        desc_m = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
            html_text,
            re.I,
        )
        img_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html_text, re.I)
        title = (title_m.group(1) if title_m else "").strip()
        if not title:
            return None
        summary = (desc_m.group(1) if desc_m else "").strip() or title
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        return {
            "headline": title,
            "summary": _normalize_summary(summary),
            "article_url": url,
            "url_hash": url_hash(url),
            "image_url": (img_m.group(1) if img_m else "") or "",
            "category": "Mundial 2026",
            "subcategory": _pick_subcategory(title, summary),
            "source_label": f"Web · {domain}",
            "relevance_score": 85,
        }
