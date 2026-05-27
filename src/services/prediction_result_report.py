"""Desglose predicción vs resultado — partidos finalizados (SPEC-021 flujo 11)."""
from __future__ import annotations

from typing import Any

from src.scoring.scoring_engine import PointsResult, ScoringReason, calculate_points
from src.services.prediction_rules import (
    PTS_EXTENDED_BOOL,
    extended_lines_from_prediction,
)
from src.services.team_flags import format_match_heading

_SCORING_REASON_ES: dict[ScoringReason, str] = {
    "EXACT_SCORE": "Resultado exacto: +5 pts",
    "CORRECT_WINNER_AND_DIFF": "Ganador y diferencia de goles: +3 pts",
    "CORRECT_WINNER_ONLY": "Solo ganador correcto: +1 pt",
    "INCORRECT": "No acertaste ganador ni marcador: 0 pts",
}


def actual_score_from_result(match: dict, result: dict) -> tuple[int, int]:
    """Marcador para scoring (90' en eliminatorias)."""
    home = result.get("result_90min_home")
    away = result.get("result_90min_away")
    if home is None:
        home = result.get("result_final_home", 0)
    if away is None:
        away = result.get("result_final_away", 0)
    return int(home), int(away)


def explain_incorrect(
    pred_home: int,
    pred_away: int,
    actual_home: int,
    actual_away: int,
) -> str:
    return (
        f"Predijiste {pred_home}-{pred_away} y el partido terminó "
        f"{actual_home}-{actual_away}."
    )


def scoring_reason_label(reason: ScoringReason) -> str:
    return _SCORING_REASON_ES.get(reason, reason)


def compute_match_points(
    pred_home: int,
    pred_away: int,
    actual_home: int,
    actual_away: int,
    phase: str,
) -> PointsResult:
    phase_key = (phase or "GROUP").upper()
    if phase_key not in (
        "GROUP",
        "R16",
        "QF",
        "SF",
        "FINAL",
        "THIRD_PLACE",
        "ROUND_OF_32",
        "ROUND_OF_16",
        "QUARTER_FINAL",
        "SEMI_FINAL",
    ):
        phase_key = "GROUP"
    ko_map = {
        "ROUND_OF_32": "R16",
        "ROUND_OF_16": "R16",
        "QUARTER_FINAL": "QF",
        "SEMI_FINAL": "SF",
    }
    phase_key = ko_map.get(phase_key, phase_key)
    return calculate_points(
        pred_home,
        pred_away,
        actual_home,
        actual_away,
        phase_key,  # type: ignore[arg-type]
    )


def format_finished_match_report(
    match: dict,
    *,
    group_name: str,
    result: dict | None,
    prediction: dict | None,
) -> str:
    title = format_match_heading(match)
    num = match.get("match_number", "?")
    gl = match.get("group_letter") or "—"
    lines = [
        f"🏁 Partido finalizado — #{num}",
        title,
        f"Grupo {gl} · 👥 {group_name}",
        "",
    ]

    if not result:
        lines.append("El marcador oficial aún no está cargado en el sistema.")
        if prediction:
            ph, pa = int(prediction["home_goals"]), int(prediction["away_goals"])
            lines.append(f"\nTu predicción: {ph}-{pa}")
            lines.append("Te avisamos cuando esté el resultado y los puntos.")
        else:
            lines.append("\n😔 No tenías predicción para este partido.")
        return "\n".join(lines)

    ah, aa = actual_score_from_result(match, result)
    lines.append(f"📋 Resultado final: {ah}-{aa}")

    if not prediction:
        lines.extend(
            [
                "",
                "😔 No tenías predicción para este partido en este grupo.",
                "No sumaste puntos.",
            ]
        )
        return "\n".join(lines)

    ph, pa = int(prediction["home_goals"]), int(prediction["away_goals"])
    phase = (match.get("phase") or "GROUP").upper()
    pts_result = compute_match_points(ph, pa, ah, aa, phase)

    stored_pts = prediction.get("points_earned")
    if stored_pts is not None:
        points_line = int(stored_pts)
    else:
        points_line = pts_result.points

    lines.extend(
        [
            "",
            "── Tu predicción ──",
            f"Marcador: {ph}-{pa}",
        ]
    )
    if prediction.get("playoff_via"):
        pw = prediction.get("playoff_winner", "?")
        lines.append(
            f"Definición: {prediction['playoff_via']} → {pw} "
            "(no suma al marcador de 90')"
        )

    lines.extend(
        [
            "",
            "── Puntos por marcador ──",
            scoring_reason_label(pts_result.reason),
        ]
    )
    if pts_result.reason == "INCORRECT":
        lines.append(explain_incorrect(ph, pa, ah, aa))
    elif pts_result.reason == "CORRECT_WINNER_ONLY":
        lines.append(
            f"Diferencia real: {abs(ah - aa)} goles · "
            f"tu diferencia: {abs(ph - pa)}."
        )

    if points_line > 0:
        lines.append(f"\n🎉 Sumaste {points_line} pts en este partido.")
    else:
        lines.append("\nSin puntos en este partido.")

    extras = extended_lines_from_prediction(prediction)
    if extras:
        lines.append("")
        lines.append("── Extendida (predicción) ──")
        lines.extend(extras)
        lines.append(
            f"\nCada variable Sí/No acertada suma +{PTS_EXTENDED_BOOL} pt "
            "(cuando el resultado oficial incluya esos datos)."
        )

    return "\n".join(lines)
