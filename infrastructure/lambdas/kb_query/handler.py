"""
Búsqueda semántica en pgvector (mismo embed Titan v2 que ingest).
Invocación: {"query": "...", "limit": 5}
"""
from __future__ import annotations

import json
import logging
import os

from src.kb.pg import kb_stats, search_chunks

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def handler(event, context):
    if isinstance(event, str):
        event = json.loads(event)
    if event.get("action") == "stats":
        return kb_stats()
    query = (event.get("query") or "").strip()
    if not query:
        return {"chunks": []}
    limit = max(1, min(int(event.get("limit", 5)), 10))
    rows = search_chunks(query, limit=limit)
    return {"chunks": rows}
