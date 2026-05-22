"""Reglas de predicción y puntuación — SPEC-021 v3 (sin jugadores)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Marcador 90' (fases de grupos y eliminatorias sobre result_90min)
PTS_EXACT = 5
PTS_WINNER_DIFF = 3
PTS_WINNER_ONLY = 1
PTS_KO_PLAYOFF_PATH = 2  # acierta ET/penales + ganador si predijiste empate en KO

# Cada variable extendida Sí/No acertada
PTS_EXTENDED_BOOL = 1

EXTENDED_FIELD_KEYS = (
    "has_red_card",
    "pred_goal_before_5min",
    "pred_var_used",
    "pred_free_kick_goal",
    "pred_penalty_saved",
    "pred_penalty_scored",
)


@dataclass(frozen=True)
class ExtendedStep:
    step_id: str
    db_key: str
    question: str
    short_label: str


EXTENDED_STEPS: tuple[ExtendedStep, ...] = (
    ExtendedStep("red", "has_red_card", "¿Habrá tarjeta roja?", "Tarjeta roja"),
    ExtendedStep(
        "goal_early",
        "pred_goal_before_5min",
        "¿Habrá gol antes del minuto 5?",
        "Gol antes del 5'",
    ),
    ExtendedStep(
        "var",
        "pred_var_used",
        "¿Habrá intervención del VAR (revisión que cambie la jugada)?",
        "Intervención VAR",
    ),
    ExtendedStep(
        "free_kick",
        "pred_free_kick_goal",
        "¿Habrá gol de tiro libre (sin rebote de córner)?",
        "Gol de tiro libre",
    ),
    ExtendedStep(
        "pen_saved",
        "pred_penalty_saved",
        "¿Habrá penal atajado?",
        "Penal atajado",
    ),
    ExtendedStep(
        "pen_scored",
        "pred_penalty_scored",
        "¿Habrá penal convertido?",
        "Penal convertido",
    ),
)

STEP_BY_ID = {s.step_id: s for s in EXTENDED_STEPS}
TOTAL_WIZARD_STEPS = 1 + len(EXTENDED_STEPS)  # marcador + 6 opcionales


def first_extended_step_id() -> str:
    return EXTENDED_STEPS[0].step_id


def next_extended_step_id(current: str) -> str | None:
    ids = [s.step_id for s in EXTENDED_STEPS]
    try:
        i = ids.index(current)
    except ValueError:
        return first_extended_step_id()
    if i + 1 < len(ids):
        return ids[i + 1]
    return None


def step_number(step_id: str) -> int:
    if step_id in ("score", "score_custom", "ko"):
        return 1
    for i, s in enumerate(EXTENDED_STEPS, start=2):
        if s.step_id == step_id:
            return i
    return 1


def bool_label(value: bool | None) -> str:
    if value is True:
        return "Sí"
    if value is False:
        return "No"
    return "—"


def extended_lines_from_prediction(pred: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for s in EXTENDED_STEPS:
        v = pred.get(s.db_key)
        if v is None:
            continue
        lines.append(f"· {s.short_label}: {bool_label(v)} (+{PTS_EXTENDED_BOOL} si acertás)")
    return lines


def max_possible_points(pred: dict[str, Any] | None) -> int:
    """Máximo teórico según lo que el usuario completó."""
    base = PTS_EXACT
    if not pred:
        return base
    extra = sum(
        PTS_EXTENDED_BOOL
        for s in EXTENDED_STEPS
        if pred.get(s.db_key) is not None
    )
    ko_bonus = 0
    if pred.get("playoff_via") and pred.get("playoff_winner"):
        ko_bonus = PTS_KO_PLAYOFF_PATH
    return base + extra + ko_bonus


def count_extended_answered(pred: dict[str, Any]) -> int:
    return sum(1 for s in EXTENDED_STEPS if pred.get(s.db_key) is not None)


def resume_step_id(pred: dict[str, Any]) -> str:
    for s in EXTENDED_STEPS:
        if pred.get(s.db_key) is None:
            return s.step_id
    return EXTENDED_STEPS[-1].step_id


def help_scoring_text() -> str:
    return """
🎯 CÓMO PREDECIR Y PUNTUAR

━━ Básica (obligatoria) ━━
Solo el marcador a los 90 minutos (ej. 2-1, 0:0).
· Exacto → 5 pts
· Ganador + diferencia de goles → 3 pts
· Solo ganador (o empate acertado sin marcador exacto) → 1 pt
· Incorrecto → 0 pts

Ejemplo básica: predicción 2-1, resultado 2-1 → 5 pts.
Ejemplo básica: predicción 2-1, resultado 3-1 → 3 pts (mismo ganador y dif. 1).

━━ Extendida (opcional, Sí/No) ━━
Después del marcador podés responder (o saltar) cada ítem.
Cada uno acertado suma +1 pt (solo si definiste Sí o No):

🟥 Tarjeta roja
⚡ Gol antes del minuto 5
📺 Intervención del VAR
🎯 Gol de tiro libre
🧤 Penal atajado
⚽ Penal convertido

Ejemplo parcial: marcador 1-0 (3 pts) + roja Sí acertada (+1) + VAR No acertado (+1)
= 5 pts si el resultado fue 1-0, hubo roja y no hubo VAR.

Ejemplo completa: marcador 2-2 (1 pt empate) + las 6 extendidas todas acertadas (+6)
= hasta 7 pts de marcador+extras (máx. teórico extendido: 5+6=11 si marcador exacto).

━━ Playoff (eliminatorias) ━━
Si predís empate en 90 min, elegís:
· Ganador en tiempo extra, o
· Ganador en penales
Si acertás vía y ganador → +2 pts extra (además del marcador de 90).

━━ Resumen tipos ━━
· Básica: solo escribís el marcador → hasta 5 pts
· Parcial: marcador + algunas extendidas → 5/3/1 + 1 por cada extra acertada
· Completa: marcador + las 6 extendidas → máximo teórico 11 pts (+2 KO si aplica)

/completo — retomá extendidas si ya guardaste el marcador.
/cancel — cancela el asistente de predicción en curso.
""".strip()
