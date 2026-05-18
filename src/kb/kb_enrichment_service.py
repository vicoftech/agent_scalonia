"""SPEC-2026-023 — enriquecimiento KB / cache tras web search."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum

import boto3

from src.kb.cache import make_cache_key, save_to_cache, ttl_for_search_type

logger = logging.getLogger(__name__)

_table = None

KB_RESULT_MIN_CHARS = 200
ENRICHED_TTL_DAYS = 30

HISTORICAL_SIGNALS = [
    r"\b(19[3-9]\d|20[0-2][0-9])\b",
    r"\bmundial\s+(de\s+)?(19|20)\d{2}",
    r"\b(primer|último|histórico|record|all.time)\b",
    r"\bjugador\s+retirado\b",
    r"\b(pelé|maradona|cruyff|beckenbauer|zidane|ronaldo nazario)\b",
    r"\b(regla|ley del juego|táctica|formación|historia de|anécdota|curiosidad)\b",
    r"\b(estadística de carrera|goles en mundiales|partidos jugados)\b",
    r"\b(sede|estadio del mundial [12]\d{3})\b",
    r"\b(canción|cancion|himno|soundtrack)\b",
]

VOLATILE_SIGNALS = [
    r"\b(hoy|ayer|anoche|esta semana|reciente|último partido|ahora)\b",
    r"\b202[6-9]\b",
    r"\b(en vivo|live|minuto a minuto)\b",
    r"\b(resultado|marcador|score)\b",
    r"\b(convocatoria|alineación|once titular|titular)\b",
    r"\b(lesión|baja|suspendido|sancionado)\b",
    r"\b(fixture|horario|cuándo juega|próximo partido)\b",
    r"\b(tabla de posiciones|clasificación actual|ranking actual)\b",
    r"\b(noticias?|novedades?|rumores?)\b",
]


class DataType(Enum):
    HISTORICAL = "historical"
    VOLATILE = "volatile"
    AMBIGUOUS = "ambiguous"


def classify_query(query: str) -> DataType:
    q = query.lower().strip()
    if len(q.split()) < 3:
        return DataType.AMBIGUOUS
    historical_score = sum(
        1 for pattern in HISTORICAL_SIGNALS if re.search(pattern, q, re.IGNORECASE)
    )
    volatile_score = sum(
        1 for pattern in VOLATILE_SIGNALS if re.search(pattern, q, re.IGNORECASE)
    )
    if volatile_score > 0:
        return DataType.VOLATILE
    if historical_score >= 2:
        return DataType.HISTORICAL
    return DataType.AMBIGUOUS


def make_slug(query: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", query.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    base = slug[:80] or "consulta"
    return base if base.endswith(".md") else f"{base}.md"


def _dynamo_table(table_name: str | None = None):
    global _table
    if _table is None:
        name = table_name or os.environ.get("DYNAMODB_TABLE", "")
        if not name:
            raise RuntimeError("DYNAMODB_TABLE no configurado")
        _table = boto3.resource("dynamodb").Table(name)
    return _table


class KBEnrichmentService:
    def __init__(
        self,
        *,
        kb_bucket: str | None = None,
        table_name: str | None = None,
        s3_client=None,
        dynamodb_table=None,
    ):
        self._kb_bucket = (
            kb_bucket or os.environ.get("KB_S3_BUCKET", "").strip()
        )
        self._table = dynamodb_table or _dynamo_table(table_name)
        self._s3 = s3_client or boto3.client("s3")

    def should_enrich(self, query: str, kb_result: str | None, web_result: str) -> bool:
        if kb_result and len(kb_result) > KB_RESULT_MIN_CHARS:
            return False
        if len(query.split()) < 3:
            return False
        if len(web_result.strip()) < 80:
            return False
        return True

    def enrich_from_web(self, query: str, web_result: str, data_type: DataType) -> None:
        if not self.should_enrich(query, None, web_result):
            logger.info("enrichment skipped query=%r", query[:60])
            return
        if data_type == DataType.HISTORICAL:
            self._enrich_kb(query, web_result)
        else:
            self._enrich_cache(query, web_result)

    def _enrich_kb(self, query: str, content: str) -> None:
        if not self._kb_bucket:
            logger.warning("KB_S3_BUCKET no configurado; fallback a cache")
            self._enrich_cache(query, content)
            return
        slug = make_slug(query)
        if self._check_already_enriched(slug):
            logger.info("already enriched slug=%s", slug)
            self._enrich_cache(query, content)
            return

        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        s3_key = f"enriched/{date_str}/{slug}"
        markdown = self._build_markdown(query, content)
        self._s3.put_object(
            Bucket=self._kb_bucket,
            Key=s3_key,
            Body=markdown.encode("utf-8"),
            ContentType="text/markdown",
            Metadata={
                "source": "web_search_enrichment",
                "query": query[:200],
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
            },
        )
        self._mark_as_enriched(query, slug, s3_key)
        logger.info("KB enrichment uploaded s3://%s/%s", self._kb_bucket, s3_key)

    def _enrich_cache(self, query: str, content: str, ttl_seconds: int | None = None) -> None:
        cache_key = make_cache_key(query)
        ttl = ttl_seconds or ttl_for_search_type("general")
        save_to_cache(cache_key, query, content, ttl)

    def _build_markdown(self, query: str, content: str) -> str:
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        title = query.strip().title() or "Consulta"
        return f"""# {title}

## Fuente
Obtenido via web search — enriquecimiento dinámico de KB.
Fecha de incorporación: {today}

## Contenido

{content}

## Metadata
- query_original: {query}
- tipo: enrichment
- verificar_actualidad: true
"""

    def _check_already_enriched(self, slug: str) -> bool:
        resp = self._table.get_item(
            Key={"partition_key": f"KB_ENRICHED#{slug}", "sort_key": "DETAILS"},
        )
        return bool(resp.get("Item"))

    def _mark_as_enriched(self, query: str, slug: str, s3_key: str) -> None:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        self._table.put_item(
            Item={
                "partition_key": f"KB_ENRICHED#{slug}",
                "sort_key": "DETAILS",
                "query": query[:200],
                "s3_key": s3_key,
                "enriched_at": datetime.now(tz=timezone.utc).isoformat(),
                "ttl_expiry": now + (ENRICHED_TTL_DAYS * 24 * 3600),
            },
        )
