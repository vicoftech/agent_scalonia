"""Mensajes de resultado final — SPEC-2026-031."""
from __future__ import annotations

from typing import Any

from src.models.match_result import MatchResult
from src.services.match_service import PHASE_LABELS
from src.services.team_flags import format_team


def _format_scorers(scorers: dict[str, int]) -> list[str]:
    lines: list[str] = []
    for name, goals in scorers.items():
        if goals > 1:
            lines.append(f"   {name} · {goals} goles")
        else:
            lines.append(f"   {name}")
    return lines


def format_match_result_message(match: dict[str, Any], result: MatchResult) -> str:
    """Mensaje 🏁 RESULTADO FINAL para Telegram."""
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

    if result.red_cards:
        lines.append(f"\n🟥 Expulsados: {result.red_cards}")
    else:
        lines.append("\n🟥 Expulsados: ninguno")

    if result.mvp_name:
        lines.append(f"\n⭐ Jugador del partido: {result.mvp_name}")

    lines.extend(
        [
            "",
            "📊 Calculando tus puntos...",
            "[Ver mi desglose →]",
        ]
    )
    return "\n".join(lines)
