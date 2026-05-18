"""Precarga fixture desde DynamoDB — el agente no depende solo de match_tool en runtime."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_TEAM_IN_QUERY = re.compile(
    r"\b("
    r"argentina|brasil|mexico|méxico|usa|españa|francia|alemania|inglaterra|portugal|"
    r"holanda|uruguay|colombia|ecuador|chile|japon|japón|austria|argelia|jordania|"
    r"alg|aut|jor|eng|fra|ger|esp|bra|arg|mex|usa"
    r")\b",
    re.IGNORECASE,
)


def _guess_team(text: str) -> str | None:
    m = _TEAM_IN_QUERY.search(text or "")
    return m.group(1) if m else None


def enrich_prompt_with_fixture(user_prompt: str) -> tuple[str, bool]:
    """
    Si es consulta de fixture, adjunta partidos desde DynamoDB al prompt.
    Retorna (prompt, True) si se inyectó fixture.
    """
    try:
        from src.services.match_query_intent import is_match_fixture_query
        from src.services.match_service import MatchService

        if not is_match_fixture_query(user_prompt):
            return user_prompt, False

        svc = MatchService()
        team = _guess_team(user_prompt)
        gl_match = re.search(r"\bgrupo\s+([a-l])\b", user_prompt, re.IGNORECASE)

        if gl_match:
            rows = svc.group_fixture(gl_match.group(1))
            header = f"[Fixture oficial — grupo {gl_match.group(1).upper()}]"
        elif team:
            rows = svc.search(team=team, limit=20)
            header = f"[Fixture oficial — {team}]"
        else:
            rows = svc.next_matches(limit=15)
            header = "[Fixture oficial — próximos partidos]"

        if rows:
            block = svc.format_list(rows, header=header)
            logger.info("fixture_prefetch rows=%s team=%s", len(rows), team or "?")
            return (
                f"{user_prompt}\n\n{block}\n\n"
                "[Instrucción: respondé SOLO con el fixture de arriba. "
                "No uses kb_retrieval_tool ni web_search para horarios o rivales.]",
                True,
            )

        return (
            f"{user_prompt}\n\n"
            "[Instrucción: consulta de PARTIDOS/FIXTURE. "
            "Usá match_tool; si falla, decí que no hay fixture cargado.]",
            False,
        )
    except Exception:
        logger.exception("fixture_prefetch failed")
        return user_prompt, False
