"""agent/tools/match_tool.py — consultas de fixture / partidos Mundial 2026."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from strands import tool

logger = logging.getLogger(__name__)


@tool
def match_tool(
    action: str,
    team: str | None = None,
    city: str | None = None,
    group_letter: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    match_number: int | None = None,
    match_id: str | None = None,
    on_date: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 15,
) -> str:
    """
    Fuente oficial de fixture del Mundial 2026 (tabla matches en DynamoDB).
    Usar SIEMPRE para partidos, horarios, grupos y rivales — no usar KB ni web para esto.

    action:
      search   — filtros: team, city, group_letter, phase, status, on_date / from_date / to_date (YYYY-MM-DD)
      get      — un partido por match_number o match_id
      next     — próximos partidos programados (limit)
      group    — todos los partidos de un grupo (group_letter A-L)
      teams    — equipos de un grupo (group_letter)
      bracket  — cruces eliminatorios posibles según 1°/2° (o 3°) del grupo (team + group_letter)
      list     — listar partidos (mismo que search sin filtros, respeta limit)

    team acepta código FIFA (ARG) o nombre (Argentina, México).
    """
    from src.services.match_service import MatchService

    svc = MatchService()
    action = (action or "search").strip().lower()

    try:
        if action == "get":
            row = svc.get(match_id=match_id, match_number=match_number)
            if not row:
                return "No encontré ese partido. Probá con match_number o pedí list/next."
            return svc.format_match(row, include_id=True)

        if action == "next":
            rows = svc.next_matches(limit=limit)
            return svc.format_list(
                rows,
                header=f"Próximos {len(rows)} partidos (UTC):",
            )

        if action == "group":
            if not group_letter:
                return "Indicá group_letter (A-L) para el fixture del grupo."
            rows = svc.group_fixture(group_letter)
            return svc.format_list(
                rows,
                header=f"Fixture grupo {group_letter.upper()}:",
            )

        if action == "teams":
            if not group_letter:
                return "Indicá group_letter (A-L)."
            codes = svc.teams_in_group(group_letter)
            if not codes:
                return f"Grupo {group_letter} no válido (usá A-L)."
            return f"Grupo {group_letter.upper()}: " + ", ".join(codes)

        if action == "bracket":
            if not team:
                return "Indicá team (ej. Argentina / ARG) para los cruces eliminatorios."
            from src.services.bracket_service import BracketService

            return BracketService().format_bracket_scenarios(
                team,
                group_letter=group_letter,
                for_agent=True,
            )

        if action in ("search", "list"):
            rows = svc.search(
                team=team,
                city=city,
                group_letter=group_letter,
                phase=phase,
                status=status,
                on_date=on_date,
                from_date=from_date,
                to_date=to_date,
                limit=limit,
            )
            parts = [f"Partidos encontrados: {len(rows)}"]
            if team:
                parts[0] += f" (equipo: {team})"
            return svc.format_list(rows, header=parts[0])

        return (
            f"action desconocida: {action}. "
            "Usá search|get|next|group|teams|list."
        )
    except Exception as exc:
        logger.warning("match_tool error: %s", exc, exc_info=True)
        return f"Error al consultar partidos: {exc}"
