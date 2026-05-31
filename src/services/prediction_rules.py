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

# Veda de predicciones por partido (SPEC-032 / ADR-005)
VEDA_MINUTES_BEFORE_KICKOFF = 5

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
    icon: str


EXTENDED_STEPS: tuple[ExtendedStep, ...] = (
    ExtendedStep(
        "red",
        "has_red_card",
        "¿Habrá tarjeta roja?",
        "Tarjeta roja",
        "🟥",
    ),
    ExtendedStep(
        "goal_early",
        "pred_goal_before_5min",
        "¿Habrá gol antes del minuto 5?",
        "Gol antes del 5'",
        "⚡",
    ),
    ExtendedStep(
        "var",
        "pred_var_used",
        "¿Habrá intervención del VAR (revisión que cambie la jugada)?",
        "Intervención VAR",
        "📺",
    ),
    ExtendedStep(
        "free_kick",
        "pred_free_kick_goal",
        "¿Habrá gol de tiro libre (sin rebote de córner)?",
        "Gol de tiro libre",
        "🎯",
    ),
    ExtendedStep(
        "pen_saved",
        "pred_penalty_saved",
        "¿Habrá penal atajado?",
        "Penal atajado",
        "🧤",
    ),
    ExtendedStep(
        "pen_scored",
        "pred_penalty_scored",
        "¿Habrá penal convertido?",
        "Penal convertido",
        "⚽",
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


def extended_value_display(pred: dict[str, Any], step: ExtendedStep) -> str:
    """Sí / No si respondió; — si aún no completó el ítem."""
    v = pred.get(step.db_key)
    if v is None:
        return "—"
    return bool_label(v)


def extended_item_line(
    pred: dict[str, Any],
    step: ExtendedStep,
    *,
    show_points_hint: bool = False,
) -> str:
    """Una línea con ícono + etiqueta + valor (o —)."""
    val = extended_value_display(pred, step)
    line = f"{step.icon} {step.short_label}: {val}"
    if show_points_hint and pred.get(step.db_key) is not None:
        line += f" (+{PTS_EXTENDED_BOOL} si acertás)"
    return line


def extended_brief_lines(pred: dict[str, Any]) -> list[str]:
    """Brief / resumen: siempre los 6 ítems extendidos con ícono."""
    return [extended_item_line(pred, s) for s in EXTENDED_STEPS]


def format_prediction_brief(
    pred: dict[str, Any],
    *,
    match_title: str,
    group_name: str,
    minutes_to_veda: str,
    change_prompt: bool = True,
    veda_locked: bool = False,
) -> str:
    """Vista al abrir un partido con predicción ya guardada."""
    if veda_locked:
        status_line = "🔒 Veda activa — la predicción ya no se puede modificar."
    else:
        status_line = f"⏱️ Veda cierra en {minutes_to_veda}"
    lines = [
        f"📋 {match_title}",
        f"👥 {group_name}",
        status_line,
        "",
        "── Tu predicción ──",
        (
            f"⚽ Marcador (90 min): {pred['home_goals']}-"
            f"{pred['away_goals']}{extended_icons_compact(pred)}"
        ),
    ]
    if pred.get("playoff_via"):
        lines.append(
            f"🏆 Playoff: {pred['playoff_via']} → "
            f"{pred.get('playoff_winner', '?')}"
        )
    lines.append("")
    lines.append("── Extendida ──")
    lines.extend(extended_brief_lines(pred))
    match_id = pred.get("match_id")
    if match_id:
        from src.services.match_brief_service import append_match_brief_context

        append_match_brief_context(lines, str(match_id))
    if change_prompt:
        lines.append("")
        lines.append("¿Querés cambiarla?")
    return "\n".join(lines)


def extended_icons_compact(pred: dict[str, Any] | None) -> str:
    """Íconos en fila (listas / marcador compacto), sin valores."""
    if not pred:
        return ""
    return " " + "".join(s.icon for s in EXTENDED_STEPS)


def extended_lines_from_prediction(pred: dict[str, Any]) -> list[str]:
    """Solo ítems respondidos (p. ej. reporte post-partido)."""
    lines: list[str] = []
    for s in EXTENDED_STEPS:
        v = pred.get(s.db_key)
        if v is None:
            continue
        lines.append(
            extended_item_line(pred, s, show_points_hint=True)
        )
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
    extended_items = "\n".join(f"{s.icon} {s.short_label}" for s in EXTENDED_STEPS)
    return f"""
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

{extended_items}

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
