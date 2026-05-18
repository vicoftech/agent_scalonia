"""agent/tools/web_search_tool.py — SPEC-2026-017 búsqueda web + cache DynamoDB."""
from __future__ import annotations

import json
import logging
import os
from typing import Callable, Optional

import boto3
import httpx
from strands import tool

from src.kb.cache import (
    get_from_cache,
    make_cache_key,
    save_to_cache,
    ttl_for_search_type,
)
from src.kb.domain import is_football_domain_query

logger = logging.getLogger(__name__)

_OUT_OF_SCOPE_MSG = (
    "Solo puedo buscar información sobre fútbol y mundiales FIFA. "
    "Reformulá la consulta en ese ámbito."
)

# Inyectable en tests
_search_fn: Optional[Callable[[str], Optional[str]]] = None


def _get_tavily_api_key() -> str:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key
    secret_id = os.environ.get("TAVILY_SECRET_ARN", "").strip()
    if not secret_id:
        return ""
    resp = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)
    raw = resp.get("SecretString", "")
    if raw.startswith("{"):
        return json.loads(raw).get("api_key", raw)
    return raw


def is_tavily_configured() -> bool:
    """True si hay API key o secreto Tavily en el entorno."""
    return bool(_get_tavily_api_key())


def perform_web_search(query: str) -> Optional[str]:
    """Búsqueda Tavily; sin API key devuelve None (tests pueden mockear)."""
    api_key = _get_tavily_api_key()
    if not api_key:
        logger.warning("TAVILY_API_KEY / TAVILY_SECRET_ARN no configurado")
        return None
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5,
            "include_domains": [],
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    parts = [f"{r.get('title', '')}\n{r.get('content', '')}" for r in results]
    return "\n\n".join(parts).strip()


def _resolve_search(query: str) -> Optional[str]:
    if _search_fn is not None:
        return _search_fn(query)
    return perform_web_search(query)


@tool
def web_search_tool(query: str, search_type: str = "general") -> str:
    """
    Busca en la web (Tavily) sobre fútbol y mundiales cuando la KB no alcanza.

    Usar para: comparativas entre jugadores/selecciones, estadísticas, tendencias,
    noticias recientes, resultados en vivo, datos no indexados en la Knowledge Base.

    Usa cache DynamoDB; TTL según search_type (live_match 10m, result 24h, fixture 6h,
    stats 6h, news 2h, general 6h).

    search_type: live_match | result | fixture | stats | news | general

    NO usar para calendario/fixture del Mundial 2026 — match_tool.
    kb_retrieval_tool ya intenta web en automático; llamá esta tool si hace falta ampliar.
    """
    from src.services.match_query_intent import is_match_fixture_query

    if is_match_fixture_query(query):
        return (
            "Para partidos, fixture, horarios y calendario del Mundial 2026 usá match_tool, "
            "no web_search_tool."
        )

    if not is_football_domain_query(query):
        return _OUT_OF_SCOPE_MSG

    cache_key = make_cache_key(query)
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Cache hit: %s", cache_key[:24])
        return cached

    ttl_seconds = ttl_for_search_type(search_type)
    try:
        result = _resolve_search(query)
    except Exception as exc:
        logger.warning("Web search error: %s", type(exc).__name__)
        return "No pude completar la búsqueda en este momento. Intentá de nuevo en unos minutos."

    if result:
        save_to_cache(cache_key, query, result, ttl_seconds)
        return result
    return "No encontré información relevante para esa consulta."
