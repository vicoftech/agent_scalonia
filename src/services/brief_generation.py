"""Generación de briefs con prefetch KB/web (sin tool-use en runtime)."""
from __future__ import annotations

import logging
import os

from src.services.brief_prompts import match_brief_prompt, team_brief_prompt
from src.services.team_flags import resolve_team_display_name

logger = logging.getLogger(__name__)

_NO_TOOLS = (
    "[Instrucción: NO invoques herramientas. El contexto ya está abajo. "
    "Respondé ÚNICAMENTE con un objeto JSON válido, sin markdown fuera del JSON.]"
)


def _team_context_limit() -> int:
    return int(os.environ.get("BRIEF_TEAM_CONTEXT_CHARS", "8000"))


def _trim(text: str, limit: int | None = None) -> str:
    cap = limit if limit is not None else _team_context_limit()
    t = (text or "").strip()
    return t[:cap] if len(t) > cap else t


def fetch_team_context(team_code: str) -> str:
    """KB + web para una selección (mismo stack que kb_retrieval_tool)."""
    code = team_code.strip().upper()
    name = resolve_team_display_name(code)
    query = f"{name} selección Mundial 2026 DT táctica plantel {code}"
    parts: list[str] = []
    try:
        from src.kb.resolve import resolve_kb_then_web

        resolved = resolve_kb_then_web(query, max_results=8, enqueue_on_web=True)
        if resolved.kb_text:
            parts.append(f"--- Knowledge Base ---\n{resolved.kb_text}")
        if resolved.web_text:
            parts.append(f"--- Web ---\n{resolved.web_text}")
    except Exception:
        logger.exception("fetch_team_context failed team=%s", code)
    if not parts and os.environ.get("KB_QUERY_LAMBDA_NAME"):
        try:
            from src.kb.retrieval import retrieve_chunks

            chunks = retrieve_chunks(query, max_results=8)
            if chunks:
                parts.append("--- Knowledge Base ---\n" + "\n\n".join(chunks))
        except Exception:
            logger.exception("retrieve_chunks fallback failed team=%s", code)
    return _trim("\n\n".join(parts))


def team_brief_agent_prompt(team_code: str, *, context: str) -> str:
    base = team_brief_prompt(team_code)
    ctx = context or "(Sin contexto KB/web — usá datos generales con «sin confirmar».)"
    return f"{base}\n\n--- CONTEXTO (única fuente) ---\n{ctx}\n\n{_NO_TOOLS}"


def match_brief_agent_prompt(
    match: dict,
    home_brief: dict,
    away_brief: dict,
    *,
    context_chars: int = 1800,
) -> str:
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    trimmed_home = {**home_brief, "brief_markdown": (home_brief.get("brief_markdown") or "")[:context_chars]}
    trimmed_away = {**away_brief, "brief_markdown": (away_brief.get("brief_markdown") or "")[:context_chars]}
    base = match_brief_prompt(match, trimmed_home, trimmed_away)
    return f"{base}\n\n{_NO_TOOLS}"
