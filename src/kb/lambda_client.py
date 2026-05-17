"""Invocación de la Lambda kb_query desde el agente (sin VPC)."""
from __future__ import annotations

import json
import os

import boto3


def search_kb(query: str, limit: int = 5) -> list[dict]:
    name = os.environ.get("KB_QUERY_LAMBDA_NAME", "").strip()
    if not name:
        raise RuntimeError("KB_QUERY_LAMBDA_NAME no configurado")
    resp = boto3.client("lambda").invoke(
        FunctionName=name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"query": query, "limit": limit}),
    )
    if resp.get("FunctionError"):
        raise RuntimeError(resp.get("FunctionError", "lambda error"))
    body = json.loads(resp["Payload"].read())
    if isinstance(body, dict) and "errorMessage" in body:
        raise RuntimeError(body["errorMessage"])
    return body.get("chunks", [])
