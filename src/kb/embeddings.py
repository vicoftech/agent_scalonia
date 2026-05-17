"""Embeddings Bedrock Titan v2 para la KB pgvector."""
from __future__ import annotations

import json
import os

import boto3

_EMBED_MODEL = os.environ.get(
    "BEDROCK_EMBED_MODEL_ID",
    "amazon.titan-embed-text-v2:0",
)
_REGION = os.environ.get("AWS_REGION", "us-east-1")
_DIM = 1024


def embed_text(text: str) -> list[float]:
    """Genera embedding 1024-dim para un texto."""
    import logging
    logging.getLogger(__name__).debug("bedrock embed len=%s", len(text))
    client = boto3.client("bedrock-runtime", region_name=_REGION)
    body = json.dumps({"inputText": text[:8000]})
    resp = client.invoke_model(
        modelId=_EMBED_MODEL,
        body=body,
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(resp["body"].read())
    vector = payload.get("embedding") or payload.get("embeddings", [{}])[0]
    if len(vector) != _DIM:
        raise ValueError(f"embedding dim={len(vector)}, expected {_DIM}")
    return vector


def vector_literal(values: list[float]) -> str:
    """Formato literal para cast ::vector en PostgreSQL."""
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"
