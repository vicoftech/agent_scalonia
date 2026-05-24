"""Búsqueda Tavily — compartido por agent tools y result_collector."""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import boto3
import httpx

logger = logging.getLogger(__name__)


def get_tavily_api_key() -> str:
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
    return bool(get_tavily_api_key())


def perform_web_search(query: str) -> Optional[str]:
    api_key = get_tavily_api_key()
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
