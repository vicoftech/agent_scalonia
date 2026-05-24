"""Mensajes de resultado final — SPEC-2026-031."""
from __future__ import annotations

from typing import Any

from src.models.match_result import MatchResult
from src.services.match_service import PHASE_LABELS
from src.services.prediction_rules import bool_label
from src.services.team_flags import format_team

# Eventos reales del partido (mismas etiquetas que el wizard de predicción)
MATCH_EVENT_LINES: tuple[tuple[str, str], ...] = (
    ("goal_before_5min", "Gol antes del 5'"),
    ("var_used", "Intervención VAR"),
    ("free_kick_goal", "Gol de tiro libre"),
    ("penalty_saved", "Penal atajado"),
    ("penalty_scored", "Penal convertido"),
)


def _format_scorers(scorers: dict[str, int]) -> list[str]:
    lines: list[str] = []
    for name, goals in scorers.items():
        if goals > 1:
            lines.append(f"   {name} · {goals} goles")
        else:
            lines.append(f"   {name}")
    return lines


def _format_red_cards(red_cards: int) -> str:
    if red_cards <= 0:
        return "ninguno"
    return "Sí"


def format_match_events_lines(result: MatchResult) -> list[str]:
    """Hechos del partido: expulsiones y variables extendidas (Sí/No/—)."""
    lines = [f"🟥 Expulsados: {_format_red_cards(result.red_cards)}"]
    for attr, label in MATCH_EVENT_LINES:
        lines.append(f"{label}: {bool_label(getattr(result, attr, None))}")
    return lines


def format_match_result_message(match: dict[str, Any], result: MatchResult) -> str:
    """Mensaje 🏁 RESULTADO FINAL — marcador, goles y eventos reales del partido."""
    home = format_team(match["home_team"])
    away = format_team(match["away_team"])
    h, a = result.home_goals, result.away_goals
    lines = [
        "🏁 RESULTADO FINAL",
        "",
        f"{home}  {h} - {a}  {away}",
    ]

    phase = (match.get("phase") or "GROUP").upper()
    phase_label = PHASE_LABELS.get(phase, phase.replace("_", " ").title())
    venue = match.get("venue") or ""
    city = match.get("city") or ""
    loc = " · ".join(x for x in (venue, city) if x)
    gl = match.get("group_letter")
    meta = []
    if gl:
        meta.append(f"Grupo {gl}")
    if phase != "GROUP":
        meta.append(phase_label)
    if loc:
        meta.append(loc)
    if meta:
        lines.append("  ".join(meta))

    if result.playoff_via == "PENALTIES" and result.playoff_winner:
        lines.append(
            f"\n({format_team(result.playoff_winner)} gana en penales)"
        )
    elif result.playoff_via == "ET":
        lines.append("\n(Decisión en tiempo extra)")

    if result.scorers:
        lines.append("")
        lines.append("⚽ Goles:")
        lines.extend(_format_scorers(result.scorers))

    lines.append("")
    lines.extend(format_match_events_lines(result))

    return "\n".join(lines)
