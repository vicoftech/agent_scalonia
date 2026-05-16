"""
src/scoring/scoring_engine.py
Funciones PURAS — sin boto3, sin I/O. Testeable con pytest sin mocks.
SPEC: SPEC-2026-013 | TASK: TASK-010 | Modo: Humano
"""
from dataclasses import dataclass
from typing import Literal

MatchPhase    = Literal["GROUP", "R16", "QF", "SF", "FINAL", "THIRD_PLACE"]
ScoringReason = Literal["EXACT_SCORE", "CORRECT_WINNER_AND_DIFF", "CORRECT_WINNER_ONLY", "INCORRECT"]
TrivaDifficulty = Literal["easy", "medium", "hard"]

TRIVIA_POINTS: dict[str, int] = {"easy": 1, "medium": 2, "hard": 3}


@dataclass(frozen=True)
class PointsResult:
    points: int
    reason: ScoringReason
    predicted_home: int
    predicted_away: int
    actual_home:    int
    actual_away:    int
    phase:          MatchPhase


def _winner(home: int, away: int) -> str:
    if home > away: return "HOME"
    if away > home: return "AWAY"
    return "DRAW"


def calculate_points(
    pred_home: int, pred_away: int,
    actual_home: int, actual_away: int,
    phase: MatchPhase,
) -> PointsResult:
    """
    Calcula puntos de una predicción.

    IMPORTANTE para fases eliminatorias (R16/QF/SF/FINAL/THIRD_PLACE):
    El caller DEBE pasar result_90min como actual_home/actual_away.
    Ignorar ET y penales es responsabilidad del caller, no de esta función.

    Prioridad: EXACT(5) > WINNER+DIFF(3) > WINNER(1) > INCORRECT(0)

    Ejemplos:
        calculate_points(2, 0, 2, 0, "GROUP") → (5, "EXACT_SCORE")
        calculate_points(2, 0, 3, 1, "GROUP") → (3, "CORRECT_WINNER_AND_DIFF")
        calculate_points(2, 0, 1, 0, "GROUP") → (1, "CORRECT_WINNER_ONLY")
        calculate_points(2, 0, 0, 1, "GROUP") → (0, "INCORRECT")
        calculate_points(0, 0, 0, 0, "QF")   → (5, "EXACT_SCORE")  # 90' empate
    """
    # TODO: implementar — TASK-010
    raise NotImplementedError("Implementar en TASK-010 — Sprint 2")


def calculate_trivia_points(difficulty: TrivaDifficulty) -> int:
    """Puntos por respuesta correcta de trivia. Sin penalización por error."""
    return TRIVIA_POINTS[difficulty]
