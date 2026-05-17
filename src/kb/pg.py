"""Acceso a prode.kb_chunks (pgvector) — usado por Lambdas en VPC."""
from __future__ import annotations

import json
import os
import socket

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

from src.kb.embeddings import embed_text, vector_literal

_SCHEMA_READY = False

_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS prode;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS prode.kb_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_path  TEXT NOT NULL,
    chunk_index  INT  NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector(1024) NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_path, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_source_path
    ON prode.kb_chunks (source_path);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding_hnsw
    ON prode.kb_chunks
    USING hnsw (embedding vector_cosine_ops);
"""

_SECRET_ARN = lambda: os.environ["AURORA_SYNC_SECRET_ARN"]
_PROXY = lambda: os.environ["RDS_PROXY_ENDPOINT"]
_DB = lambda: os.environ.get("DB_NAME", "prode")


def _resolve_ipv4(host: str) -> str:
    """Resuelve el endpoint RDS a IPv4 (evita fallos AAAA en Lambda VPC)."""
    try:
        infos = socket.getaddrinfo(host, 5432, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise psycopg2.OperationalError(
            f"DNS falló para {host}: {exc}. "
            "Verificá que el cluster Aurora tenga al menos una instancia en estado available."
        ) from exc
    return infos[0][4][0]


def _connect():
    import logging

    log = logging.getLogger(__name__)
    log.info("secretsmanager get %s", _SECRET_ARN())
    raw = boto3.client("secretsmanager").get_secret_value(SecretId=_SECRET_ARN())[
        "SecretString"
    ]
    cfg = json.loads(raw)
    host = _PROXY()
    hostaddr = _resolve_ipv4(host)
    log.info("postgres connect host=%s hostaddr=%s db=%s", host, hostaddr, _DB())
    return psycopg2.connect(
        host=host,
        hostaddr=hostaddr,
        port=int(cfg.get("port", 5432)),
        user=cfg.get("username") or cfg.get("user"),
        password=cfg["password"],
        dbname=cfg.get("dbname") or cfg.get("database") or _DB(),
        connect_timeout=30,
    )


def _ensure_kb_schema(conn) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with conn.cursor() as cur:
        cur.execute(_SCHEMA_SQL)
    conn.commit()
    _SCHEMA_READY = True


def replace_chunks(source_path: str, chunks: list[str]) -> int:
    """Reemplaza todos los chunks de un documento (embed + upsert)."""
    count = 0
    with _connect() as conn:
        _ensure_kb_schema(conn)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prode.kb_chunks WHERE source_path = %s", (source_path,))
            for idx, content in enumerate(chunks):
                vec = vector_literal(embed_text(content))
                cur.execute(
                    """
                    INSERT INTO prode.kb_chunks
                        (source_path, chunk_index, content, embedding, metadata)
                    VALUES (%s, %s, %s, %s::vector, %s::jsonb)
                    ON CONFLICT (source_path, chunk_index) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                    """,
                    (source_path, idx, content, vec, json.dumps({"source": source_path})),
                )
                count += 1
        conn.commit()
    return count


def kb_stats() -> dict:
    """Conteo y metadatos de conexión (para verificar cluster/DB correctos)."""
    with _connect() as conn:
        _ensure_kb_schema(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS database, inet_server_addr()::text AS server_ip")
            meta = dict(cur.fetchone())
            cur.execute(
                """
                SELECT source_path, COUNT(*)::int AS chunks
                FROM prode.kb_chunks
                GROUP BY source_path
                ORDER BY source_path
                """
            )
            by_source = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT COUNT(*)::int AS total FROM prode.kb_chunks")
            meta["total_chunks"] = cur.fetchone()["total"]
            meta["host"] = _PROXY()
            meta["documents"] = by_source
            return meta


def search_chunks(query: str, limit: int = 5) -> list[dict]:
    query_vec = vector_literal(embed_text(query))
    sql = """
        SELECT source_path, content,
               1 - (embedding <=> %s::vector) AS score
        FROM prode.kb_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with _connect() as conn:
        _ensure_kb_schema(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (query_vec, query_vec, limit))
            return [dict(row) for row in cur.fetchall()]
