"""Precarga KB + fallback web antes del agente — ISSUE-2026-024."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_KB_CTX_HEADER = (
    "[Contexto Knowledge Base — usá esto solo si responde la pregunta; "
    "si no alcanza o es tangencial, llamá web_search_tool con la misma consulta; "
    "no digas solo que no está en la KB sin intentar web]"
)

_WEB_CTX_HEADER = (
    "[Contexto web (búsqueda externa) — basá la respuesta en esto; "
    "podés citar que es información de fuentes públicas recientes]"
)

_WEB_INSTRUCTION = (
    "[Instrucción: la Knowledge Base no tuvo datos suficientes. "
    "Debés llamar web_search_tool con la consulta del usuario "
    "(search_type=stats para comparativas/tendencias, news para noticias). "
    "No respondas únicamente que no está en la KB.]"
)


def _prompt_with_football_scope(user_prompt: str) -> str:
    """Ayuda al modelo/guardrail a no confundir finales del Mundial con entretenimiento."""
    try:
        from src.kb.domain import is_football_domain_query

        if is_football_domain_query(user_prompt):
            return f"[Alcance: fútbol y Mundial FIFA]\n{user_prompt}"
    except Exception:
        pass
    return user_prompt


def enrich_prompt_with_kb(user_prompt: str) -> tuple[str, int]:
    """
    Consulta KB (+ web si miss/baja relevancia) y adjunta contexto al prompt.
    Retorna (prompt_enriquecido, cantidad_chunks_kb).
    """
    user_prompt = _prompt_with_football_scope(user_prompt)
    try:
        from src.services.match_query_intent import is_match_fixture_query

        if is_match_fixture_query(user_prompt):
            logger.info("kb prefetch skipped: fixture query → match_tool")
            return (
                f"{user_prompt}\n\n"
                "[Instrucción: consulta de PARTIDOS/FIXTURE. "
                "Usá match_tool únicamente; no uses KB ni web_search para horarios o rivales.]",
                0,
            )
    except Exception:
        pass

    if not os.environ.get("KB_QUERY_LAMBDA_NAME", "").strip():
        from src.kb.query_intent import is_analytical_query

        if is_analytical_query(user_prompt):
            return f"{user_prompt}\n\n{_WEB_INSTRUCTION}", 0
        return user_prompt, 0

    try:
        from src.kb.resolve import resolve_kb_then_web

        resolved = resolve_kb_then_web(user_prompt, max_results=5, enqueue_on_web=True)

        if resolved.web_text:
            logger.info(
                "kb_prefetch web_fallback_used=true kb_chunks=%s kb_max_score=%.3f tavily=%s",
                resolved.kb_chunk_count,
                resolved.kb_max_score,
                resolved.tavily_configured,
            )
            parts = [user_prompt, _WEB_CTX_HEADER, resolved.web_text]
            if resolved.kb_text:
                parts.insert(1, f"{_KB_CTX_HEADER}:\n{resolved.kb_text}")
            return "\n\n".join(parts), resolved.kb_chunk_count

        if resolved.kb_text and resolved.kb_chunk_count > 0:
            logger.info(
                "kb_prefetch kb_only chunks=%s kb_max_score=%.3f",
                resolved.kb_chunk_count,
                resolved.kb_max_score,
            )
            return (
                f"{user_prompt}\n\n{_KB_CTX_HEADER}:\n{resolved.kb_text}",
                resolved.kb_chunk_count,
            )

        logger.info(
            "kb_prefetch miss kb_chunks=%s kb_max_score=%.3f tavily=%s",
            resolved.kb_chunk_count,
            resolved.kb_max_score,
            resolved.tavily_configured,
        )
        return f"{user_prompt}\n\n{_WEB_INSTRUCTION}", 0

    except Exception:
        logger.exception("kb prefetch failed")
        return f"{user_prompt}\n\n{_WEB_INSTRUCTION}", 0
