"""agent/tools/kb_retrieval_tool.py — RAG + web search con enriquecimiento (SPEC-023, ISSUE-024)."""
from __future__ import annotations

import logging

from strands import tool

logger = logging.getLogger(__name__)


@tool
def kb_retrieval_tool(query: str, max_results: int = 5) -> str:
    """
    Busca primero en la Knowledge Base (pgvector): historia, reglas, tácticas, cultura y
    fichas de las 48 selecciones del Mundial 2026 (DT, récord reciente, figuras, táctica, ligas).

    Usar para preguntas sobre un país/selección concreta antes que web. Incluí el nombre del
    equipo y «Mundial 2026» en query si ayuda. max_results=8 si la pregunta es amplia (varios equipos).

    Si no hay pasajes relevantes o la pregunta es comparativa en vivo / noticias recientes,
    hace fallback automático a búsqueda web (Tavily) y puede encolar enriquecimiento de KB.

    NO usar para fixture, horarios, rivales ni calendario — eso es match_tool.
    Para ampliar tras un prefetch débil, el agente puede llamar web_search_tool.
    """
    from src.services.match_query_intent import is_match_fixture_query

    if is_match_fixture_query(query):
        return (
            "Esta consulta es sobre partidos o fixture del Mundial 2026. "
            "Debés usar match_tool (action=search|get|next|group|teams). "
            "No uses kb_retrieval_tool ni web_search_tool para horarios ni rivales."
        )

    try:
        from src.kb.resolve import format_kb_web_miss_message, resolve_kb_then_web

        resolved = resolve_kb_then_web(query, max_results=max_results, enqueue_on_web=True)

        if resolved.web_text:
            if resolved.kb_text:
                return (
                    f"{resolved.kb_text}\n\n"
                    f"--- Información complementaria (web) ---\n\n{resolved.web_text}"
                )
            return resolved.web_text

        if resolved.kb_text:
            return resolved.kb_text

        return format_kb_web_miss_message(
            tavily_configured=resolved.tavily_configured,
            had_kb_snippet=bool(resolved.kb_chunk_count),
        )

    except RuntimeError as exc:
        logger.warning("KB retrieval config: %s", exc)
        return (
            "Error técnico al consultar la Knowledge Base (no es que falte el dato). "
            f"Detalle: {exc}"
        )
    except Exception as exc:
        logger.warning("KB retrieval error: %s", exc, exc_info=True)
        return (
            "Error técnico al consultar la Knowledge Base (no es que falte el dato). "
            f"Detalle: {exc}"
        )
