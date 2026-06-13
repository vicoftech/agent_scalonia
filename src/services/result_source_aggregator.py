"""Agregador multi-fuente de resultados — SPEC-2026-051."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from src.models.match_result import MatchResult
from src.services.result_parser import (
    detect_in_play_signals,
    extract_mvp_from_text,
    parse_web_result,
)
from src.services.result_service import ESTIMATED_MATCH_MINUTES

logger = logging.getLogger(__name__)

_web_search_fn: Optional[Callable[[str], Optional[str]]] = None

EXTENDED_FIELDS = (
    "goal_before_5min",
    "var_used",
    "free_kick_goal",
    "penalty_saved",
    "penalty_scored",
)


@dataclass
class SourceSnapshot:
    source_id: str
    fetched_at: str
    raw_excerpt: str
    parsed: MatchResult | None
    parse_confidence: float
    in_play_signals: bool


@dataclass
class AggregatedCandidate:
    match_id: str
    proposed: MatchResult
    consensus_score: float
    snapshots: list[SourceSnapshot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def set_web_search_fn(fn: Optional[Callable[[str], Optional[str]]]) -> None:
    global _web_search_fn
    _web_search_fn = fn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_web_search(query: str) -> Optional[str]:
    from src.web.tavily_search import perform_web_search

    return perform_web_search(query)


def _excerpt(raw: str, *, limit: int = 2000) -> str:
    return (raw or "")[:limit]


def _tavily_queries(match: dict[str, Any]) -> list[tuple[str, str]]:
    home = match["home_team"]
    away = match["away_team"]
    return [
        ("tavily:score", f"{home} vs {away} resultado final marcador Copa Mundial 2026"),
        (
            "tavily:events",
            f"{home} vs {away} resumen goles tarjetas VAR Copa Mundial 2026",
        ),
        ("tavily:mvp", f"jugador del partido {home} vs {away} Copa Mundial 2026"),
    ]


def _parse_snapshot(
    source_id: str,
    raw: str | None,
    match: dict[str, Any],
    *,
    base_confidence: float,
) -> SourceSnapshot | None:
    if not raw:
        return None
    in_play = detect_in_play_signals(raw)
    parsed = None if in_play else parse_web_result(raw, match)
    conf = base_confidence if parsed else 0.0
    if parsed and source_id == "tavily:mvp" and not parsed.mvp_name:
        mvp = extract_mvp_from_text(raw)
        if mvp:
            from dataclasses import replace

            parsed = replace(parsed, mvp_name=mvp)
    return SourceSnapshot(
        source_id=source_id,
        fetched_at=_now_iso(),
        raw_excerpt=_excerpt(raw),
        parsed=parsed,
        parse_confidence=conf,
        in_play_signals=in_play,
    )


def _score_key(result: MatchResult) -> tuple[int, int]:
    return (int(result.home_goals), int(result.away_goals))


def _merge_extended(
    snapshots: list[SourceSnapshot],
    warnings: list[str],
) -> dict[str, bool | None]:
    merged: dict[str, bool | None] = {f: None for f in EXTENDED_FIELDS}
    for attr in EXTENDED_FIELDS:
        votes: dict[bool, float] = {}
        for snap in snapshots:
            if not snap.parsed:
                continue
            val = getattr(snap.parsed, attr, None)
            if val is None:
                continue
            votes[bool(val)] = votes.get(bool(val), 0.0) + snap.parse_confidence
        if not votes:
            continue
        if len(votes) > 1:
            warnings.append(f"{attr} sin consenso entre fuentes")
            merged[attr] = None
        else:
            merged[attr] = next(iter(votes))
    return merged


def _pick_proposed(
    snapshots: list[SourceSnapshot],
    match: dict[str, Any],
    warnings: list[str],
) -> tuple[MatchResult | None, float]:
    scored: list[tuple[tuple[int, int], SourceSnapshot]] = []
    for snap in snapshots:
        if snap.in_play_signals or not snap.parsed:
            continue
        scored.append((_score_key(snap.parsed), snap))

    if not scored:
        return None, 0.0

    api_snaps = [s for s in snapshots if s.source_id == "api_football" and s.parsed]
    counts: dict[tuple[int, int], float] = {}
    for key, snap in scored:
        counts[key] = counts.get(key, 0.0) + snap.parse_confidence

    best_key = max(counts, key=lambda k: counts[k])
    total_weight = sum(counts.values()) or 1.0
    consensus = counts[best_key] / total_weight

    base_snap = next(s for k, s in scored if k == best_key)
    proposed = base_snap.parsed
    if not proposed:
        return None, 0.0

    if api_snaps:
        api = api_snaps[0].parsed
        if api and _score_key(api) != best_key:
            warnings.append("API-Football discrepa con consenso web; se usa API-Football")
            proposed = api
            consensus = max(consensus, 0.85)
        elif api:
            proposed = api
            consensus = max(consensus, 0.9)

    ext = _merge_extended(snapshots, warnings)
    mvp = proposed.mvp_name
    if not mvp:
        for snap in sorted(snapshots, key=lambda s: -s.parse_confidence):
            if snap.parsed and snap.parsed.mvp_name:
                mvp = snap.parsed.mvp_name
                break

    from dataclasses import replace

    proposed = replace(
        proposed,
        match_id=match.get("match_id"),
        goal_before_5min=ext["goal_before_5min"],
        var_used=ext["var_used"],
        free_kick_goal=ext["free_kick_goal"],
        penalty_saved=ext["penalty_saved"],
        penalty_scored=ext["penalty_scored"],
        mvp_name=mvp,
        phase=match.get("phase", proposed.phase),
    )
    if any(getattr(proposed, f) is None for f in EXTENDED_FIELDS):
        warnings.append("extendidas incompletas en una o más variables")
    return proposed, consensus


class ResultSourceAggregator:
    def aggregate(
        self,
        match: dict[str, Any],
        *,
        api_result: MatchResult | None = None,
    ) -> AggregatedCandidate | None:
        match_id = match.get("match_id") or ""
        warnings: list[str] = []
        snapshots: list[SourceSnapshot] = []

        if api_result:
            snapshots.append(
                SourceSnapshot(
                    source_id="api_football",
                    fetched_at=_now_iso(),
                    raw_excerpt=f"api {api_result.home_goals}-{api_result.away_goals}",
                    parsed=api_result,
                    parse_confidence=1.0,
                    in_play_signals=False,
                )
            )

        search = _web_search_fn or _default_web_search
        for source_id, query in _tavily_queries(match):
            raw = search(query)
            snap = _parse_snapshot(source_id, raw, match, base_confidence=0.75)
            if snap:
                snapshots.append(snap)
                if snap.in_play_signals:
                    warnings.append(f"{source_id}: señales de partido en curso")

        if any(s.in_play_signals for s in snapshots) and not api_result:
            logger.info("aggregate skip in_play match=%s", match_id[:8])
            return None

        proposed, consensus = _pick_proposed(snapshots, match, warnings)
        if not proposed:
            return None

        if consensus < 0.5:
            warnings.append("consenso bajo en marcador 90'")

        return AggregatedCandidate(
            match_id=match_id,
            proposed=proposed,
            consensus_score=round(consensus, 2),
            snapshots=snapshots[:5],
            warnings=warnings,
        )


def assert_match_finished_for_result(
    match: dict[str, Any],
    *,
    allow_sandbox: bool = False,
) -> None:
    """Guard ISSUE-050 / SPEC-051 — kickoff + 130 min."""
    import os

    if allow_sandbox and os.environ.get("RESULT_SKIP_KICKOFF_CHECK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return
    kickoff_raw = match.get("kickoff_utc") or ""
    if not kickoff_raw:
        raise ValueError("match sin kickoff_utc")
    kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
    estimated_end = kickoff + timedelta(minutes=ESTIMATED_MATCH_MINUTES)
    if datetime.now(tz=timezone.utc) < estimated_end:
        raise ValueError("partido aún no alcanzó fin estimado")
