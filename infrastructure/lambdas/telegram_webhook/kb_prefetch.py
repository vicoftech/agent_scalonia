"""Precarga KB antes del agente — Nova a veces no invoca kb_retrieval_tool."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def enrich_prompt_with_kb(user_prompt: str) -> tuple[str, int]:
    """
    Consulta kb_query y adjunta pasajes al prompt del agente.
    Retorna (prompt_enriquecido, cantidad_chunks).
    """
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
        return user_prompt, 0
    try:
        from src.kb.chunks_format import format_kb_chunks
        from src.kb.lambda_client import search_kb

        rows = search_kb(user_prompt, limit=5)
        if not rows:
            return user_prompt, 0
        ctx = format_kb_chunks(rows)
        return (
            f"{user_prompt}\n\n"
            "[Contexto Knowledge Base — basá la respuesta en esto; "
            "el usuario ya está autenticado y activo]:\n"
            f"{ctx}",
            len(rows),
        )
    except Exception:
        logger.exception("kb prefetch failed")
        return user_prompt, 0
