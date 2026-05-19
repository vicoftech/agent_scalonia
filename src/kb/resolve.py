"""Resolución KB → web compartida (tools + prefetch) — ISSUE-2026-024."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from src.kb.chunks_format import format_kb_chunks
from src.kb.domain import is_football_domain_query
from src.kb.enrichment_queue import enqueue_enrichment
from src.kb.kb_enrichment_service import KB_RESULT_MIN_CHARS, classify_query
from src.kb.query_intent import is_analytical_query, is_historical_football_query

logger = logging.getLogger(__name__)

KB_MIN_RELEVANCE_SCORE = 0.75
KB_HIGH_RELEVANCE_SCORE = 0.85

_WEB_FAILURE_PREFIXES = (
    "No encontré información relevante",
    "No pude completar la búsqueda",
    "Solo puedo buscar información sobre fútbol",
    "La Knowledge Base no está configurada",
)


@dataclass
class KbWebResolveResult:
    kb_text: str
    web_text: str | None
    kb_chunk_count: int
    kb_max_score: float
    web_fallback_used: bool
    tavily_configured: bool


def max_kb_score(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    scores = [float(r.get("score") or 0.0) for r in rows]
    return max(scores) if scores else 0.0


def kb_is_sufficient(query: str, kb_text: str, kb_max: float) -> bool:
    if not kb_text or len(kb_text.strip()) <= KB_RESULT_MIN_CHARS:
        return False
    if is_analytical_query(query):
        return kb_max >= KB_HIGH_RELEVANCE_SCORE
    return kb_max >= KB_MIN_RELEVANCE_SCORE


def _is_usable_web_result(text: str) -> bool:
    if not text or len(text.strip()) < 80:
        return False
    return not any(text.startswith(p) for p in _WEB_FAILURE_PREFIXES)


def is_tavily_configured() -> bool:
    if os.environ.get("TAVILY_API_KEY", "").strip():
        return True
    return bool(os.environ.get("TAVILY_SECRET_ARN", "").strip())


def perform_web_search(query: str) -> Optional[str]:
    """Wrapper testeable; delega en agent.tools.web_search_tool."""
    from agent.tools.web_search_tool import perform_web_search as _tavily_search

    return _tavily_search(query)


def format_kb_web_miss_message(*, tavily_configured: bool, had_kb_snippet: bool) -> str:
    if not tavily_configured:
        return (
            "No encontré datos suficientes en la Knowledge Base y la búsqueda web "
            "no está habilitada en este entorno (falta configurar Tavily). "
            "Probá reformular la pregunta o consultá más tarde."
        )
    if had_kb_snippet:
        return (
            "La Knowledge Base no alcanza para responder con precisión y la búsqueda web "
            "no devolvió resultados útiles. Reformulá la consulta con más detalle."
        )
    return (
        "No encontré información suficiente en la Knowledge Base ni en la web para esa consulta. "
        "Reformulá con nombres de jugadores, selecciones o el período que te interesa."
    )


def resolve_kb_then_web(
    query: str,
    *,
    max_results: int = 5,
    enqueue_on_web: bool = True,
) -> KbWebResolveResult:
    """
    1) search_kb  2) si insuficiente → perform_web_search  3) opcional enqueue enrichment.
    """
    rows: list[dict] = []
    kb_text = ""
    try:
        from src.kb.lambda_client import search_kb

        rows = search_kb(query, limit=max(1, min(max_results, 10)))
        if rows:
            kb_text = format_kb_chunks(rows)
    except RuntimeError as exc:
        logger.warning("resolve_kb_then_web config: %s", exc)
    except Exception:
        logger.exception("resolve_kb_then_web search_kb failed")

    kb_max = max_kb_score(rows)
    tavily_ok = is_tavily_configured()

    # Web solo si la KB no alcanza (comparativas, historia subjetiva, etc.).
    # Antes se forzaba Tavily en toda consulta "histórica" aunque la KB ya tenía el dato
    # (ej. Pelé 1962), duplicando latencia y fallos del LLM con tools.
    force_web = is_football_domain_query(query) and not kb_is_sufficient(
        query, kb_text, kb_max
    ) and (is_analytical_query(query) or is_historical_football_query(query))

    if kb_is_sufficient(query, kb_text, kb_max) and not force_web:
        logger.info(
            "kb_resolve sufficient | chunks=%s max_score=%.3f analytical=%s",
            len(rows),
            kb_max,
            is_analytical_query(query),
        )
        return KbWebResolveResult(
            kb_text=kb_text,
            web_text=None,
            kb_chunk_count=len(rows),
            kb_max_score=kb_max,
            web_fallback_used=False,
            tavily_configured=tavily_ok,
        )

    web_text: str | None = None
    web_used = False

    if is_football_domain_query(query):
        try:
            web_text = perform_web_search(query)
            web_used = bool(web_text and _is_usable_web_result(web_text))
        except Exception:
            logger.exception("resolve_kb_then_web web failed")

        if web_used and enqueue_on_web:
            try:
                enqueue_enrichment(query, web_text, classify_query(query))
            except Exception:
                logger.exception("enqueue enrichment failed")

    logger.info(
        "kb_resolve fallback | chunks=%s max_score=%.3f web_used=%s tavily=%s analytical=%s force_web=%s",
        len(rows),
        kb_max,
        web_used,
        tavily_ok,
        is_analytical_query(query),
        force_web,
    )

    return KbWebResolveResult(
        kb_text=kb_text,
        web_text=web_text if web_used else None,
        kb_chunk_count=len(rows),
        kb_max_score=kb_max,
        web_fallback_used=web_used,
        tavily_configured=tavily_ok,
    )
