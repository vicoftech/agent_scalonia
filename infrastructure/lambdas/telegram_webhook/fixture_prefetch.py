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


def _format_by_dates(svc, dates: list) -> str:
    from datetime import date

    lines: list[str] = []
    for d in sorted(dates):
        assert isinstance(d, date)
        day_rows = svc.search_by_local_dates([d])
        label = d.strftime("%d/%m/%Y")
        lines.append(f"\n{label} — {len(day_rows)} partido(s):")
        if day_rows:
            for m in day_rows:
                lines.append(f"- {svc.format_match(m)}")
        else:
            lines.append("- Sin partidos programados.")
    return "\n".join(lines).strip()


def _bracket_direct_reply(user_prompt: str) -> str | None:
    from src.services.bracket_service import BracketService, extract_group_letter_from_query
    from src.services.match_query_intent import is_fixture_bracket_query

    if not is_fixture_bracket_query(user_prompt):
        return None
    team = _guess_team(user_prompt)
    if not team:
        return None
    group = extract_group_letter_from_query(user_prompt)
    body = BracketService().format_bracket_scenarios(
        team,
        group_letter=group,
        for_agent=False,
    )
    return body[:4096] if body else None


def try_direct_fixture_reply(user_prompt: str) -> str | None:
    """
    Respuesta lista para Telegram sin invocar el LLM (fixture en DynamoDB).
    Usar cuando hay fechas/equipo/grupo parseables y datos en tabla.
    """
    try:
        from src.services.prediction_score_parse import looks_like_simple_score

        if looks_like_simple_score(user_prompt):
            return None
        from src.services.match_date_parse import parse_dates_from_query, parse_month_range
        from src.services.match_query_intent import (
            is_fixture_bracket_query,
            is_match_fixture_query,
        )
        from src.services.match_service import MatchService

        if not is_match_fixture_query(user_prompt):
            return None

        if is_fixture_bracket_query(user_prompt):
            return _bracket_direct_reply(user_prompt)

        svc = MatchService()
        dates = parse_dates_from_query(user_prompt)
        if dates:
            body = _format_by_dates(svc, dates)
            return (
                "📅 Fixture oficial Mundial 2026 (horarios GMT-3):\n"
                f"{body}\n\n"
                "Instancia = fase del torneo (ej. Cuartos de final = QUARTER_FINAL)."
            )

        month_range = parse_month_range(user_prompt)
        if month_range:
            from_d, to_d = month_range
            rows = svc.search(from_date=from_d, to_date=to_d, limit=50)
            if rows:
                return svc.format_list(rows, header="📅 Fixture oficial:")

        team = _guess_team(user_prompt)
        if team and not is_fixture_bracket_query(user_prompt):
            rows = svc.search(team=team, limit=20)
            if rows:
                return svc.format_list(rows, header=f"📅 Partidos — {team}:")

        gl_match = re.search(r"\bgrupo\s+([a-l])\b", user_prompt, re.IGNORECASE)
        if gl_match:
            rows = svc.group_fixture(gl_match.group(1))
            if rows:
                return svc.format_list(
                    rows,
                    header=f"📅 Fixture grupo {gl_match.group(1).upper()}:",
                )
        return None
    except Exception:
        logger.exception("try_direct_fixture_reply failed")
        return None


def enrich_prompt_with_fixture(user_prompt: str) -> tuple[str, bool]:
    """
    Si es consulta de fixture, adjunta partidos desde DynamoDB al prompt.
    Retorna (prompt, True) si se inyectó fixture.
    """
    try:
        from src.services.match_date_parse import parse_dates_from_query, parse_month_range
        from src.services.match_query_intent import (
            is_fixture_bracket_query,
            is_match_fixture_query,
        )
        from src.services.match_service import MatchService

        if not is_match_fixture_query(user_prompt):
            return user_prompt, False

        if is_fixture_bracket_query(user_prompt):
            bracket = _bracket_direct_reply(user_prompt)
            if bracket:
                return (
                    f"{user_prompt}\n\n"
                    f"[Cuadro eliminatorio oficial — razoná con estos escenarios]\n"
                    f"{bracket}\n\n"
                    "[Instrucción: respondé en prosa los cruces posibles según 1° o 2° del grupo; "
                    "usá match_tool action=bracket si necesitás ampliar. No uses KB ni web para la llave.]",
                    True,
                )

        svc = MatchService()
        team = _guess_team(user_prompt)
        gl_match = re.search(r"\bgrupo\s+([a-l])\b", user_prompt, re.IGNORECASE)
        dates = parse_dates_from_query(user_prompt)
        month_range = parse_month_range(user_prompt)

        if dates:
            header = (
                "[Fixture oficial — fechas consultadas (GMT-3); "
                "respondé día por día, incluyendo instancia/fase]"
            )
            block = f"{header}\n{_format_by_dates(svc, dates)}"
            logger.info("fixture_prefetch by_dates=%s", [d.isoformat() for d in dates])
        elif month_range:
            from_d, to_d = month_range
            rows = svc.search(from_date=from_d, to_date=to_d, limit=50)
            header = f"[Fixture oficial — {from_d} a {to_d}]"
            block = svc.format_list(rows, header=header) if rows else f"{header}\nSin partidos."
        elif gl_match:
            rows = svc.group_fixture(gl_match.group(1))
            header = f"[Fixture oficial — grupo {gl_match.group(1).upper()}]"
            block = svc.format_list(rows, header=header) if rows else f"{header}\nSin partidos."
        elif team and not is_fixture_bracket_query(user_prompt):
            rows = svc.search(team=team, limit=20)
            header = f"[Fixture oficial — {team}]"
            block = svc.format_list(rows, header=header) if rows else f"{header}\nSin partidos."
        else:
            rows = svc.next_matches(limit=15)
            header = "[Fixture oficial — próximos partidos]"
            block = svc.format_list(rows, header=header) if rows else f"{header}\nSin partidos."

        if block:
            return (
                f"{user_prompt}\n\n{block}\n\n"
                "[Instrucción: respondé SOLO con el fixture de arriba. "
                "Si un día dice 0 partidos, decilo explícitamente. "
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
