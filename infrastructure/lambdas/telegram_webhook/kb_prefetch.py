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

_DIRECT_KB_MAX_LEN = 3800


def _trim_kb_display(text: str, max_len: int = _DIRECT_KB_MAX_LEN) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]") and "/" in stripped:
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    return body[:max_len] if len(body) > max_len else body


def try_direct_knowledge_reply(user_prompt: str) -> str | None:
    """
    Respuesta en Telegram sin invocar el LLM cuando KB (o web) ya tiene material útil.
    Evita fallos de Mistral en ciclos tool-use; las comparativas siguen yendo al agente.
    """
    if not os.environ.get("KB_QUERY_LAMBDA_NAME", "").strip():
        return None
    try:
        from src.kb.domain import is_football_domain_query
        from src.kb.query_intent import is_analytical_query
        from src.kb.resolve import (
            _is_usable_web_result,
            kb_is_sufficient,
            resolve_kb_then_web,
        )
        from src.services.match_query_intent import is_match_fixture_query

        if not is_football_domain_query(user_prompt):
            return None
        if is_match_fixture_query(user_prompt):
            return None
        if is_analytical_query(user_prompt):
            return None

        resolved = resolve_kb_then_web(user_prompt, max_results=5, enqueue_on_web=False)

        if resolved.web_text and _is_usable_web_result(resolved.web_text):
            body = _trim_kb_display(resolved.web_text)
            if resolved.kb_text and kb_is_sufficient(
                user_prompt, resolved.kb_text, resolved.kb_max_score
            ):
                kb_part = _trim_kb_display(resolved.kb_text, max_len=1200)
                return (
                    "🌐 Información verificada (web + Knowledge Base):\n\n"
                    f"{body}\n\n---\n📚 KB:\n{kb_part}"
                )[:4096]
            return f"🌐 Información verificada (búsqueda web):\n\n{body}"[:4096]

        if resolved.kb_text and kb_is_sufficient(
            user_prompt, resolved.kb_text, resolved.kb_max_score
        ):
            body = _trim_kb_display(resolved.kb_text)
            if len(body) < 120:
                return None
            return f"📚 Según la Knowledge Base del Prode:\n\n{body}"[:4096]

        return None
    except Exception:
        logger.exception("try_direct_knowledge_reply failed")
        return None


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
