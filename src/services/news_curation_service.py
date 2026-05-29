"""Curación automática de noticias — SPEC-2026-046."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from src.dao.dynamo.news_dao import NewsDAO, url_hash
from src.services.news_telegram_format import domain_from_url
from src.services.news_translation import translate_if_english
from src.web.tavily_search import get_tavily_api_key, is_tavily_configured

logger = logging.getLogger(__name__)

# Tier 1 internacional (prioridad)
TIER1_DOMAINS = frozenset(
    {
        "fifa.com",
        "es.fifa.com",
        "uefa.com",
        "conmebol.com",
        "bbc.com",
        "bbc.co.uk",
        "reuters.com",
        "theguardian.com",
        "skysports.com",
        "goal.com",
        "espn.com",
    }
)

NEWS_WHITELIST_DOMAINS = sorted(
    TIER1_DOMAINS
    | {
        "ole.com.ar",
        "espn.com.ar",
        "espndeportes.espn.com",
        "deportes.lanacion.com.ar",
        "clarin.com",
        "infobae.com",
    }
)

SLOT_QUERIES = {
    "MORNING": "site:fifa.com World Cup 2026 latest news teams groups",
    "EVENING": "World Cup 2026 news site:uefa.com OR site:goal.com OR site:bbc.com",
    "PRE_MATCHDAY": "World Cup 2026 matchday preview today site:fifa.com",
    "POST_MATCHDAY": "World Cup 2026 match results analysis site:fifa.com OR site:uefa.com",
    "ADMIN": "site:fifa.com World Cup 2026 news teams fixtures",
}

# Búsquedas diversas para /noticia sin URL (evita loop en medios AR)
ADMIN_SEARCH_QUERIES: tuple[str, ...] = (
    "site:fifa.com World Cup 2026 latest news",
    "site:uefa.com World Cup 2026 national teams",
    "World Cup 2026 squad news site:goal.com",
    "World Cup 2026 groups fixtures site:fifa.com",
    "World Cup 2026 preview site:bbc.com OR site:skysports.com",
    "World Cup 2026 injuries transfers site:reuters.com OR site:theguardian.com",
    "Copa del Mundo 2026 noticias site:conmebol.com",
    "World Cup 2026 team news site:espn.com",
)

# Legacy alias — curate_fresh ya no itera slots AR primero
ADMIN_CURATE_SLOTS: tuple[str, ...] = ("ADMIN",)


def headline_fingerprint(headline: str) -> str:
    """Dedup aproximado por titular (misma historia, distinta URL)."""
    t = re.sub(r"[^\w\s]", " ", (headline or "").lower())
    words = [w for w in t.split() if len(w) > 2][:10]
    if not words:
        return hashlib.sha256((headline or "").encode()).hexdigest()[:16]
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:16]


def _domain_allowed(url: str) -> bool:
    host = domain_from_url(url)
    return any(host == d or host.endswith("." + d) or d in host for d in NEWS_WHITELIST_DOMAINS)


def _domain_tier(host: str) -> int:
    if any(host == d or host.endswith("." + d) for d in TIER1_DOMAINS):
        return 1
    return 2


def _score_candidate(
    title: str,
    content: str,
    url: str,
    *,
    slot: str,
    domains_used_today: set[str] | None = None,
) -> int:
    text = f"{title} {content}".lower()
    host = domain_from_url(url)
    score = 40
    if "2026" in text or "world cup" in text or "mundial" in text:
        score += 25
    if _domain_tier(host) == 1:
        score += 20
    if "fifa.com" in host:
        score += 8
    if slot in ("PRE_MATCHDAY", "POST_MATCHDAY") and (
        "match" in text or "partido" in text or "grupo" in text or "group" in text
    ):
        score += 10
    # Penalizar foco exclusivo selección argentina (salvo slot legacy)
    if slot != "EVENING" and re.search(
        r"\b(argentina|albiceleste|scaloni)\b", text, re.I
    ) and not re.search(r"\b(brazil|france|spain|germany|mexico|usa|england)\b", text, re.I):
        score -= 12
    used = domains_used_today or set()
    if host in used:
        score -= 25
    return max(0, min(100, score))


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
        logger.exception("tavily news search failed query=%s", query[:80])
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
    if "lesión" in blob or "lesion" in blob or "injury" in blob or "injured" in blob:
        return "#Lesiones"
    if "fixture" in blob or "grupo" in blob or "calendario" in blob or "group" in blob:
        return "#Fixture"
    if (
        "selección" in blob
        or "seleccion" in blob
        or "plantel" in blob
        or "squad" in blob
        or "roster" in blob
    ):
        return "#Selecciones"
    return "#Noticias"


def _source_label(domain: str) -> str:
    if "fifa.com" in domain:
        return "RSS · fifa.com"
    if domain in TIER1_DOMAINS or any(domain.endswith("." + d) for d in TIER1_DOMAINS):
        return f"Web · {domain}"
    return f"Web · {domain}"


def _is_excluded(
    *,
    url: str,
    title: str,
    exclude_url_hashes: set[str],
    exclude_headline_fps: set[str],
    news: NewsDAO,
) -> bool:
    h = url_hash(url)
    if h in exclude_url_hashes or news.is_url_published(url):
        return True
    fp = headline_fingerprint(title)
    return fp in exclude_headline_fps


def _finalize_text_fields(
    headline: str, summary: str, *, article_url: str = ""
) -> tuple[str, str]:
    return translate_if_english(headline, summary, article_url=article_url)


class NewsCurationService:
    def __init__(self, *, news: NewsDAO | None = None):
        self._news = news or NewsDAO()

    def _domains_used_on_date(self, run_date: str) -> set[str]:
        domains: set[str] = set()
        for item in self._news.list_published_on_date(run_date):
            url = item.get("article_url") or ""
            if url:
                domains.add(domain_from_url(url))
        return domains

    def _row_to_candidate(
        self,
        row: dict[str, Any],
        *,
        slot: str,
        domains_used_today: set[str],
    ) -> dict[str, Any] | None:
        url = (row.get("url") or "").strip()
        if not url or not _domain_allowed(url):
            return None
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        if len(title) < 12:
            return None
        summary = _normalize_summary(content)
        domain = domain_from_url(url)
        return {
            "headline": title,
            "summary": summary,
            "article_url": url,
            "url_hash": url_hash(url),
            "headline_fp": headline_fingerprint(title),
            "image_url": row.get("image") or row.get("og_image") or "",
            "category": "Mundial 2026",
            "subcategory": _pick_subcategory(title, summary),
            "source_label": _source_label(domain),
            "relevance_score": _score_candidate(
                title,
                summary,
                url,
                slot=slot,
                domains_used_today=domains_used_today,
            ),
        }

    def curate_for_slot(
        self,
        slot: str,
        *,
        exclude_url_hashes: set[str] | None = None,
        exclude_headline_fps: set[str] | None = None,
        run_date: str | None = None,
    ) -> dict[str, Any] | None:
        if not is_tavily_configured():
            logger.warning("Tavily not configured — cannot curate news")
            return None
        query = SLOT_QUERIES.get(slot, SLOT_QUERIES["MORNING"])
        return self._curate_from_queries(
            (query,),
            slot=slot,
            exclude_url_hashes=exclude_url_hashes,
            exclude_headline_fps=exclude_headline_fps,
            run_date=run_date,
        )

    def _curate_from_queries(
        self,
        queries: tuple[str, ...],
        *,
        slot: str,
        exclude_url_hashes: set[str] | None = None,
        exclude_headline_fps: set[str] | None = None,
        run_date: str | None = None,
    ) -> dict[str, Any] | None:
        exclude_urls = exclude_url_hashes or set()
        exclude_fps = exclude_headline_fps or set()
        domains_used: set[str] = set()
        if run_date:
            domains_used = self._domains_used_on_date(run_date)

        candidates: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for query in queries:
            for row in _search_tavily(query, max_results=6):
                url = (row.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                title = (row.get("title") or "").strip()
                if _is_excluded(
                    url=url,
                    title=title,
                    exclude_url_hashes=exclude_urls,
                    exclude_headline_fps=exclude_fps,
                    news=self._news,
                ):
                    continue
                cand = self._row_to_candidate(
                    row, slot=slot, domains_used_today=domains_used
                )
                if not cand:
                    continue
                seen_urls.add(url)
                exclude_fps.add(cand["headline_fp"])
                candidates.append(cand)

        if not candidates:
            return None
        candidates.sort(
            key=lambda c: (
                c["relevance_score"],
                -_domain_tier(domain_from_url(c["article_url"])),
            ),
            reverse=True,
        )
        best = candidates[0]
        best["headline"], best["summary"] = _finalize_text_fields(
            best["headline"],
            best["summary"],
            article_url=best.get("article_url") or "",
        )
        best["subcategory"] = _pick_subcategory(best["headline"], best["summary"])
        best.pop("headline_fp", None)
        if run_date:
            best["run_date"] = run_date
        return best

    def curate_fresh(
        self,
        *,
        exclude_url_hashes: set[str] | None = None,
        exclude_headline_fps: set[str] | None = None,
        slots: tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        """Busca noticia única (admin /noticia sin URL) con fuentes internacionales."""
        if not is_tavily_configured():
            logger.warning("Tavily not configured — cannot curate_fresh")
            return None
        queries = ADMIN_SEARCH_QUERIES if slots is None else tuple(
            SLOT_QUERIES.get(s, SLOT_QUERIES["ADMIN"]) for s in slots
        )
        from src.services.match_service import DISPLAY_TZ
        from datetime import datetime

        run_date = datetime.now(DISPLAY_TZ).date().isoformat()
        return self._curate_from_queries(
            queries,
            slot="ADMIN",
            exclude_url_hashes=exclude_url_hashes,
            exclude_headline_fps=exclude_headline_fps,
            run_date=run_date,
        )

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
        title_m = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            html_text,
            re.I,
        )
        if not title_m:
            title_m = re.search(r"<title>([^<]+)</title>", html_text, re.I)
        desc_m = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
            html_text,
            re.I,
        )
        img_m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            html_text,
            re.I,
        )
        title = (title_m.group(1) if title_m else "").strip()
        if not title:
            return None
        raw_summary = (desc_m.group(1) if desc_m else "").strip() or title
        headline, summary = _finalize_text_fields(
            title, _normalize_summary(raw_summary), article_url=url
        )
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        return {
            "headline": headline,
            "summary": summary,
            "article_url": url,
            "url_hash": url_hash(url),
            "image_url": (img_m.group(1) if img_m else "") or "",
            "category": "Mundial 2026",
            "subcategory": _pick_subcategory(headline, summary),
            "source_label": _source_label(domain),
            "relevance_score": 85,
        }
