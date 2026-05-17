"""agent/tools/kb_retrieval_tool.py — RAG vía Lambda kb_query → pgvector."""
from __future__ import annotations

import logging

from strands import tool

logger = logging.getLogger(__name__)


@tool
def kb_retrieval_tool(query: str, max_results: int = 5) -> str:
    """
    Busca en la Knowledge Base (pgvector / Aurora): historia de mundiales,
    reglas, tácticas, grupos/sedes/calendario Mundial 2026 y PDF FWC26 Match Schedule.
    Usar antes que web_search para preguntas sobre grupos, fixture estático o reglas.
    Para resultados en vivo o noticias del día usá web_search_tool.
    """
    try:
        from src.kb.lambda_client import search_kb

        rows = search_kb(query, limit=max(1, min(max_results, 10)))
    except RuntimeError as exc:
        logger.warning("KB retrieval config: %s", exc)
        return (
            "La Knowledge Base no está configurada (falta KB_QUERY_LAMBDA_NAME). "
            "Usá web_search_tool para consultas actuales."
        )
    except Exception:
        logger.warning("KB retrieval error", exc_info=True)
        return "No pude consultar la Knowledge Base en este momento."

    if not rows:
        return "No encontré pasajes relevantes en la Knowledge Base para esa consulta."

    parts = []
    for row in rows:
        src = row.get("source_path", "")
        prefix = f"[{src}]\n" if src else ""
        parts.append(f"{prefix}{row['content']}")
    return "\n\n---\n\n".join(parts)
