"""
S3 → chunk → Titan embed → prode.kb_chunks (pgvector).
Trigger: PutObject en bucket KB (*.md, *.pdf con pdfplumber).
"""
from __future__ import annotations

import logging
import os
import urllib.parse

import boto3

from src.kb.chunking import chunk_text
from src.kb.pdf_extract import extract_pdf_text
from src.kb.pg import replace_chunks

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

_s3 = boto3.client("s3")

_SUPPORTED = (".md", ".pdf")


def _load_document_text(bucket: str, key: str) -> str:
    lower = key.lower()
    if lower.endswith(".md"):
        logger.info("s3 get_object s3://%s/%s", bucket, key)
        obj = _s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read().decode("utf-8", errors="replace")
    if lower.endswith(".pdf"):
        logger.info("pdf extract s3://%s/%s", bucket, key)
        return extract_pdf_text(s3=_s3, bucket=bucket, key=key)
    raise ValueError(f"tipo no soportado: {key}")


def _ingest_key(bucket: str, key: str) -> dict:
    if not key.lower().endswith(_SUPPORTED):
        return {"key": key, "skipped": True, "reason": "unsupported suffix"}

    text = _load_document_text(bucket, key)
    if not text.strip():
        return {"key": key, "skipped": True, "reason": "empty document"}

    chunks = chunk_text(text)
    logger.info("chunked %s -> %s pieces", key, len(chunks))
    n = replace_chunks(key, chunks)
    logger.info("ingested %s chunks=%s", key, n)
    return {"key": key, "chunks": n, "chars": len(text)}


def handler(event, context):
    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        try:
            results.append(_ingest_key(bucket, key))
        except Exception:
            logger.exception("failed key=%s", key)
            raise
    return {"processed": len(results), "results": results}
