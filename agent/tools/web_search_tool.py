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
    Busca información actualizada sobre fútbol y el Mundial 2026.
    Usa cache DynamoDB; TTL según search_type (live_match 10m, result 24h, fixture 6h, news 2h).

    search_type: live_match | result | fixture | stats | news | general
  """
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
