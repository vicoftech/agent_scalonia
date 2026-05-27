"""KB + web para Ask IA — prefetch antes del agente (evita tool-use roto en Mistral)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DIRECT_KB_MAX_LEN = 3800

_KB_CTX_HEADER = (
    "[Contexto Knowledge Base — basá la respuesta en esto; "
    "no inventes datos fuera del contexto]"
)
_WEB_CTX_HEADER = (
    "[Contexto web — basá la respuesta en esto; "
    "podés mencionar que es información de fuentes públicas]"
)
_NO_TOOLS = (
    "[Instrucción: NO invoques herramientas (kb_retrieval_tool, web_search_tool, etc.). "
    "El contexto KB/web ya está en este mensaje. Respondé en español rioplatense, breve.]"
)
_FIXTURE_HINT = (
    "[Instrucción: consulta de PARTIDOS/FIXTURE. "
    "Indicá al usuario que use /partidos para calendario y rivales; "
    "no uses KB ni web para horarios.]"
)


@dataclass
class AskIaTurnPrep:
    """Resultado de preparar un turno Ask IA."""

    direct_reply: str | None = None
    agent_prompt: str | None = None


def _trim_display(text: str, max_len: int = _DIRECT_KB_MAX_LEN) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]") and "/" in stripped:
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    return body[:max_len] if len(body) > max_len else body


def _scoped_prompt(user_prompt: str) -> str:
    try:
        from src.kb.domain import is_football_domain_query

        if is_football_domain_query(user_prompt):
            return f"[Alcance: fútbol y Mundial FIFA]\n{user_prompt}"
    except Exception:
        pass
    return user_prompt


def try_direct_knowledge_reply(user_prompt: str) -> str | None:
    """
    Respuesta sin LLM cuando KB o web ya tienen material suficiente.
  """
    if not os.environ.get("KB_QUERY_LAMBDA_NAME", "").strip():
        return None
    question = (user_prompt or "").strip()
    if not question:
        return None
    try:
        from src.services.prediction_score_parse import looks_like_simple_score

        if looks_like_simple_score(question):
            return None
        from src.kb.domain import is_football_domain_query
        from src.kb.query_intent import is_analytical_query
        from src.kb.resolve import (
            _is_usable_web_result,
            kb_is_sufficient,
            resolve_kb_then_web,
        )
        from src.services.match_query_intent import is_match_fixture_query

        if not is_football_domain_query(question):
            return None
        if is_match_fixture_query(question):
            return None
        if is_analytical_query(question):
            return None

        resolved = resolve_kb_then_web(question, max_results=5, enqueue_on_web=True)

        if resolved.web_text and _is_usable_web_result(resolved.web_text):
            body = _trim_display(resolved.web_text)
            if resolved.kb_text and kb_is_sufficient(
                question, resolved.kb_text, resolved.kb_max_score
            ):
                kb_part = _trim_display(resolved.kb_text, max_len=1200)
                return (
                    "🌐 Información verificada (web + Knowledge Base):\n\n"
                    f"{body}\n\n---\n📚 KB:\n{kb_part}"
                )[:4096]
            return f"🌐 Información verificada (búsqueda web):\n\n{body}"[:4096]

        if resolved.kb_text and kb_is_sufficient(
            question, resolved.kb_text, resolved.kb_max_score
        ):
            body = _trim_display(resolved.kb_text)
            if len(body) < 120:
                return None
            return f"📚 Según la Knowledge Base del Prode:\n\n{body}"[:4096]

        return None
    except Exception:
        logger.exception("ask_ia try_direct_knowledge_reply failed")
        return None


def prepare_ask_ia_turn(user_prompt: str) -> AskIaTurnPrep:
    """
    1) Respuesta directa KB/web si alcanza.
    2) Si no, prompt enriquecido para el agente (sin depender de tools).
    3) Si no hay datos, mensaje de miss.
    """
    question = (user_prompt or "").strip()
    if not question:
        return AskIaTurnPrep(direct_reply="Escribí una pregunta sobre el Mundial 2026.")

    direct = try_direct_knowledge_reply(question)
    if direct:
        return AskIaTurnPrep(direct_reply=direct)

    scoped = _scoped_prompt(question)
    try:
        from src.services.prediction_score_parse import looks_like_simple_score

        if looks_like_simple_score(scoped):
            return AskIaTurnPrep(
                agent_prompt=(
                    f"{_NO_TOOLS}\n\n{scoped}\n\n"
                    "Para predecir un resultado usá /partidos."
                )
            )
    except Exception:
        pass

    try:
        from src.services.match_query_intent import is_match_fixture_query

        if is_match_fixture_query(scoped):
            return AskIaTurnPrep(
                agent_prompt=f"{scoped}\n\n{_FIXTURE_HINT}\n\n{_NO_TOOLS}"
            )
    except Exception:
        pass

    if not os.environ.get("KB_QUERY_LAMBDA_NAME", "").strip():
        return AskIaTurnPrep(
            agent_prompt=(
                f"{_NO_TOOLS}\n\n{scoped}\n\n"
                "[Nota: Knowledge Base no configurada en este entorno.]"
            )
        )

    try:
        from src.kb.resolve import format_kb_web_miss_message, resolve_kb_then_web

        resolved = resolve_kb_then_web(scoped, max_results=5, enqueue_on_web=True)

        if resolved.web_text:
            parts = [scoped, _WEB_CTX_HEADER, resolved.web_text]
            if resolved.kb_text:
                parts.insert(1, f"{_KB_CTX_HEADER}:\n{resolved.kb_text}")
            return AskIaTurnPrep(agent_prompt=f"{_NO_TOOLS}\n\n" + "\n\n".join(parts))

        if resolved.kb_text and resolved.kb_chunk_count > 0:
            return AskIaTurnPrep(
                agent_prompt=(
                    f"{_NO_TOOLS}\n\n{scoped}\n\n"
                    f"{_KB_CTX_HEADER}:\n{resolved.kb_text}"
                )
            )

        miss = format_kb_web_miss_message(
            tavily_configured=resolved.tavily_configured,
            had_kb_snippet=bool(resolved.kb_chunk_count),
        )
        return AskIaTurnPrep(direct_reply=miss)

    except Exception:
        logger.exception("ask_ia prepare_ask_ia_turn failed")
        return AskIaTurnPrep(
            agent_prompt=(
                f"{_NO_TOOLS}\n\n{scoped}\n\n"
                "[Error técnico al consultar KB/web. Respondé con disculpas breves.]"
            )
        )
