"""Lectura y formato de briefs de partido (SPEC-2026-045)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from src.dao.dynamo.brief_dao import MatchBriefDAO, TeamBriefDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.services.team_flags import resolve_team_display_name

_ACTIVE_STATUSES = frozenset({"SCHEDULED", "VEDA", "LIVE"})


def is_unplayed_match(match: dict[str, Any]) -> bool:
    status = (match.get("status") or "").upper()
    if status == "FINISHED" or match.get("brief_frozen"):
        return False
    return status in _ACTIVE_STATUSES


def should_regenerate_match_brief(match: dict[str, Any]) -> bool:
    if match.get("brief_frozen") or (match.get("status") or "").upper() == "FINISHED":
        return False
    if (match.get("status") or "").upper() not in _ACTIVE_STATUSES:
        return False
    return is_unplayed_match(match)


def _brief_enabled() -> bool:
    return os.environ.get("ENABLE_DAILY_BRIEFS", "true").lower() in ("1", "true", "yes")


class MatchBriefService:
    def __init__(
        self,
        *,
        match_briefs: MatchBriefDAO | None = None,
        team_briefs: TeamBriefDAO | None = None,
        matches: MatchDAO | None = None,
    ):
        self._match_briefs = match_briefs or MatchBriefDAO()
        self._team_briefs = team_briefs or TeamBriefDAO()
        self._matches = matches or MatchDAO()

    def get_team_brief(self, iso3: str) -> dict[str, Any] | None:
        if not _brief_enabled():
            return None
        return self._team_briefs.get_current(iso3)

    def get_match_brief(self, match_id: str) -> dict[str, Any] | None:
        if not _brief_enabled():
            return None
        item = self._match_briefs.get_current(match_id)
        if not item:
            return None
        if item.get("brief_frozen"):
            return item
        ttl = item.get("ttl_expiry")
        if ttl is not None and int(ttl) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return item

    def freeze_match_brief(self, match_id: str) -> None:
        self._match_briefs.freeze(match_id)

    def format_ia_prediction_for_ui(self, match_brief: dict[str, Any]) -> str:
        line = (match_brief.get("ia_prediction_line") or "").strip()
        if not line:
            return ""
        home = match_brief.get("home_team") or ""
        away = match_brief.get("away_team") or ""
        bullets_home_s = match_brief.get("home_strengths") or []
        bullets_home_w = match_brief.get("home_weaknesses") or []
        bullets_away_s = match_brief.get("away_strengths") or []
        bullets_away_w = match_brief.get("away_weaknesses") or []

        def _fmt_bullets(label: str, items: list) -> str:
            if not items:
                return ""
            return "\n".join([f"• {label}: {x}" for x in items[:4]])

        lines = [
            "── Contexto IA ──",
            f"🤖 IA Prediction: {line}",
            _fmt_bullets(f"Fortalezas {home}", bullets_home_s),
            _fmt_bullets(f"Debilidades {home}", bullets_home_w),
            _fmt_bullets(f"Fortalezas {away}", bullets_away_s),
            _fmt_bullets(f"Debilidades {away}", bullets_away_w),
            "_(Análisis informativo; no es recomendación de apuesta ni marcador exacto.)_",
        ]
        return "\n".join(x for x in lines if x)


def append_match_brief_context(lines: list[str], match_id: str) -> None:
    """Inserta bloque IA en wizard / brief de predicción si hay TTL vigente."""
    brief = MatchBriefService().get_match_brief(match_id)
    if not brief:
        return
    block = MatchBriefService().format_ia_prediction_for_ui(brief)
    if block:
        lines.append("")
        lines.append(block)
