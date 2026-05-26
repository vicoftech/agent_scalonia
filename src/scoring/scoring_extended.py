"""Puntos extendidos y playoff — complemento de scoring_engine (puro)."""
from __future__ import annotations

from typing import Any, Callable

from src.models.match_result import MatchResult
from src.services.prediction_rules import EXTENDED_STEPS, PTS_EXTENDED_BOOL, PTS_KO_PLAYOFF_PATH

_KO_PHASES = frozenset({"R16", "QF", "SF", "FINAL", "THIRD_PLACE", "ROUND_OF_16", "QUARTER_FINAL", "SEMI_FINAL"})

# pred db_key → valor real en MatchResult (o derivado)
_ACTUAL_EXTENDED: dict[str, Callable[[MatchResult], bool | None]] = {
    "has_red_card": lambda r: (r.red_cards or 0) > 0,
    "pred_goal_before_5min": lambda r: r.goal_before_5min,
    "pred_var_used": lambda r: r.var_used,
    "pred_free_kick_goal": lambda r: r.free_kick_goal,
    "pred_penalty_saved": lambda r: r.penalty_saved,
    "pred_penalty_scored": lambda r: r.penalty_scored,
}


def normalize_phase(phase: str | None) -> str:
    p = (phase or "GROUP").upper()
    m = {
        "ROUND_OF_32": "R16",
        "ROUND_OF_16": "R16",
        "QUARTER_FINAL": "QF",
        "SEMI_FINAL": "SF",
    }
    return m.get(p, p)


def extended_points(pred: dict[str, Any], result: MatchResult) -> tuple[int, list[dict[str, Any]]]:
    """+1 por cada extendida acertada (solo si el usuario respondió y el resultado es conocido)."""
    pts = 0
    hits: list[dict[str, Any]] = []
    for step in EXTENDED_STEPS:
        pred_val = pred.get(step.db_key)
        if pred_val is None:
            continue
        actual_fn = _ACTUAL_EXTENDED.get(step.db_key)
        if not actual_fn:
            continue
        actual_val = actual_fn(result)
        if actual_val is None:
            continue
        ok = bool(pred_val) == bool(actual_val)
        if ok:
            pts += PTS_EXTENDED_BOOL
        hits.append(
            {
                "key": step.db_key,
                "label": step.short_label,
                "predicted": bool(pred_val),
                "actual": bool(actual_val),
                "points": PTS_EXTENDED_BOOL if ok else 0,
            }
        )
    return pts, hits


def ko_playoff_points(
    pred: dict[str, Any],
    result: MatchResult,
    phase: str,
) -> tuple[int, dict[str, Any] | None]:
    """+2 si predijiste empate 90' y acertás vía + ganador en eliminatorias."""
    ph = normalize_phase(phase)
    if ph not in _KO_PHASES:
        return 0, None
    pred_home = int(pred.get("home_goals", 0))
    pred_away = int(pred.get("away_goals", 0))
    if pred_home != pred_away:
        return 0, None
    if not result.playoff_via or not result.playoff_winner:
        return 0, None
    pred_via = pred.get("playoff_via")
    pred_winner = pred.get("playoff_winner")
    if not pred_via or not pred_winner:
        return 0, None
    ok = (
        str(pred_via).upper() == str(result.playoff_via).upper()
        and str(pred_winner).upper() == str(result.playoff_winner).upper()
    )
    detail = {
        "predicted_via": pred_via,
        "predicted_winner": pred_winner,
        "actual_via": result.playoff_via,
        "actual_winner": result.playoff_winner,
        "points": PTS_KO_PLAYOFF_PATH if ok else 0,
    }
    return (PTS_KO_PLAYOFF_PATH if ok else 0), detail
