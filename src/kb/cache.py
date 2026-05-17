"""Cache DynamoDB CACHE#<hash>/RESULT — SPEC-2026-017."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

TTL_LIVE_MATCH = 60 * 10
TTL_RECENT_RESULT = 60 * 60 * 24
TTL_FIXTURE = 60 * 60 * 6
TTL_STATS = 60 * 60 * 6
TTL_NEWS = 60 * 60 * 2

TTL_BY_SEARCH_TYPE = {
    "live_match": TTL_LIVE_MATCH,
    "result": TTL_RECENT_RESULT,
    "fixture": TTL_FIXTURE,
    "stats": TTL_STATS,
    "news": TTL_NEWS,
    "general": TTL_STATS,
}

_MAX_RESULT_BYTES = 10_000
_table = None


def ttl_for_search_type(search_type: str) -> int:
    return TTL_BY_SEARCH_TYPE.get(search_type, TTL_STATS)


def make_cache_key(query: str) -> str:
    digest = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:32]
    return f"CACHE#{digest}"


def _table_resource():
    global _table
    if _table is None:
        name = os.environ.get("DYNAMODB_TABLE", "")
        if not name:
            raise RuntimeError("DYNAMODB_TABLE no configurado")
        _table = boto3.resource("dynamodb").Table(name)
    return _table


def get_from_cache(cache_key: str) -> Optional[str]:
    try:
        resp = _table_resource().get_item(
            Key={"partition_key": cache_key, "sort_key": "RESULT"},
        )
        item = resp.get("Item")
        if not item:
            return None
        ttl = int(item.get("ttl_expiry") or 0)
        now = int(datetime.now(tz=timezone.utc).timestamp())
        if ttl > 0 and now > ttl:
            return None
        return item.get("result_text")
    except Exception as exc:
        logger.warning("Cache read error: %s", type(exc).__name__)
        return None


def save_to_cache(cache_key: str, query: str, result: str, ttl_seconds: int) -> None:
    try:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        _table_resource().put_item(
            Item={
                "partition_key": cache_key,
                "sort_key": "RESULT",
                "query": query,
                "result_text": result[:_MAX_RESULT_BYTES],
                "cached_at": datetime.now(tz=timezone.utc).isoformat(),
                "ttl_expiry": now + ttl_seconds,
            },
        )
    except Exception as exc:
        logger.warning("Cache write error: %s", type(exc).__name__)
