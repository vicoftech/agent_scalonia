"""Invocación de la Lambda kb_query desde el agente (sin VPC)."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def _kb_query_function_name() -> str:
    name = os.environ.get("KB_QUERY_LAMBDA_NAME", "").strip()
    if name:
        return name
    env = os.environ.get("ENV") or os.environ.get("PRODE_ENV") or "dev"
    return f"prode-mundial-kb-query-{env}"


def search_kb(query: str, limit: int = 5) -> list[dict]:
    from src.dao.dynamo.table import get_session

    fn = _kb_query_function_name()
    lam = get_session().client("lambda")
    resp = lam.invoke(
        FunctionName=fn,
        InvocationType="RequestResponse",
        Payload=json.dumps({"query": query, "limit": limit}),
    )
    if resp.get("FunctionError"):
        raise RuntimeError(resp.get("FunctionError", "lambda error"))
    body = json.loads(resp["Payload"].read())
    if isinstance(body, dict) and "errorMessage" in body:
        raise RuntimeError(body["errorMessage"])
    chunks = body.get("chunks", [])
    logger.debug("search_kb fn=%s query=%s chunks=%s", fn, query[:60], len(chunks))
    return chunks
