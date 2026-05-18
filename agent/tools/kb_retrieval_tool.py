"""agent/tools/kb_retrieval_tool.py — RAG + web search con enriquecimiento (SPEC-023)."""
from __future__ import annotations

import logging

from strands import tool

from src.kb.domain import is_football_domain_query
from src.kb.enrichment_queue import enqueue_enrichment
from src.kb.kb_enrichment_service import KB_RESULT_MIN_CHARS, classify_query

logger = logging.getLogger(__name__)

_WEB_FAILURE_PREFIXES = (
    "No encontré información relevante",
    "No pude completar la búsqueda",
    "Solo puedo buscar información sobre fútbol",
    "La Knowledge Base no está configurada",
)


def _is_usable_web_result(text: str) -> bool:
    if not text or len(text.strip()) < 80:
        return False
    return not any(text.startswith(p) for p in _WEB_FAILURE_PREFIXES)


@tool
def kb_retrieval_tool(query: str, max_results: int = 5) -> str:
    """
    Busca en la Knowledge Base (pgvector). Si no hay suficiente contexto,
    consulta la web, responde al usuario y enriquece KB (histórico) o cache
    (volátil) en background sin bloquear.

    Para resultados en vivo del día, el agente puede usar web_search_tool directo.
    """
    kb_result = ""
    try:
        from src.kb.lambda_client import search_kb

        rows = search_kb(query, limit=max(1, min(max_results, 10)))
        if rows:
            from src.kb.chunks_format import format_kb_chunks

            kb_result = format_kb_chunks(rows)
    except RuntimeError as exc:
        logger.warning("KB retrieval config: %s", exc)
        kb_result = ""
    except Exception as exc:
        logger.warning("KB retrieval error: %s", exc, exc_info=True)
        return (
            "Error técnico al consultar la Knowledge Base (no es que falte el dato). "
            f"Detalle: {exc}"
        )

    if kb_result and len(kb_result) > KB_RESULT_MIN_CHARS:
        return kb_result

    if not is_football_domain_query(query):
        return kb_result or (
            "Solo puedo buscar información sobre fútbol y mundiales FIFA. "
            "Reformulá la consulta en ese ámbito."
        )

    from agent.tools.web_search_tool import perform_web_search

    try:
        web_result = perform_web_search(query)
    except Exception as exc:
        logger.warning("web search fallback failed: %s", exc)
        web_result = None

    if not web_result or not _is_usable_web_result(web_result):
        if kb_result:
            return kb_result
        return "No encontré información sobre eso en la Knowledge Base ni en la web."

    data_type = classify_query(query)
    try:
        enqueue_enrichment(query, web_result, data_type)
    except Exception:
        logger.exception("enqueue enrichment failed")

    return web_result
