"""Pie de mensaje Telegram: countdown al primer partido + comandos básicos."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.services.match_service import MatchService, _parse_dt
from src.services.team_flags import format_team_display

logger = logging.getLogger(__name__)

DISPLAY_TZ = timezone(timedelta(hours=-3))
FOOTER_MARKER = "⏳ Faltan"
BASIC_COMMANDS_LINE = (
    "/partidos · /proximo · /ask_ia · /grupos · "
    "/mi_ranking · /trivia · /reglas · /help"
)


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _fixture_fallback_matches() -> list[dict[str, Any]]:
    path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "fixtures"
        / "mundial2026_matches.json"
    )
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("matches") or [])
    except Exception:
        logger.exception("fixture fallback read failed path=%s", path)
        return []


@lru_cache(maxsize=1)
def _cached_opener_match() -> dict[str, Any] | None:
    try:
        match = MatchService().first_tournament_match()
        if match:
            return match
    except Exception:
        logger.exception("first_tournament_match from Dynamo failed")
    rows = _fixture_fallback_matches()
    if not rows:
        return None
    return sorted(rows, key=lambda m: (m.get("kickoff_utc") or "", m.get("match_number") or 0))[0]


def first_tournament_match() -> dict[str, Any] | None:
    return _cached_opener_match()


def clear_opener_cache() -> None:
    _cached_opener_match.cache_clear()


def countdown_parts(*, now: datetime | None = None) -> dict[str, Any]:
    """
    Retorna días/horas/minutos hasta el primer partido y metadatos del partido.
    Si ya arrancó el torneo, started=True.
    """
    match = first_tournament_match()
    if not match:
        return {"started": False, "missing": True}

    try:
        kickoff = _parse_dt(str(match["kickoff_utc"]))
    except (KeyError, ValueError, TypeError):
        return {"started": False, "missing": True, "match": match}

    ref = now or datetime.now(timezone.utc)
    if ref >= kickoff:
        return {
            "started": True,
            "missing": False,
            "match": match,
            "kickoff": kickoff,
        }

    delta = kickoff - ref
    total_minutes = int(delta.total_seconds() // 60)
    days = total_minutes // (24 * 60)
    rem = total_minutes % (24 * 60)
    hours = rem // 60
    minutes = rem % 60
    return {
        "started": False,
        "missing": False,
        "match": match,
        "kickoff": kickoff,
        "days": days,
        "hours": hours,
        "minutes": minutes,
    }


def _match_opener_label(match: dict[str, Any]) -> str:
    home = format_team_display(match.get("home_team") or "?")
    away = format_team_display(match.get("away_team") or "?")
    return f"{home} vs {away}"


def countdown_text(*, now: datetime | None = None) -> str:
    info = countdown_parts(now=now)
    if info.get("missing"):
        return "⏳ Próximamente: fixture del Mundial 2026"

    match = info.get("match") or {}
    label = _match_opener_label(match)
    kickoff = info.get("kickoff")
    when = ""
    if kickoff:
        local = kickoff.astimezone(DISPLAY_TZ)
        when = f" · {local.strftime('%d/%m %H:%M')} ART"

    if info.get("started"):
        return f"🏁 ¡El Mundial 2026 ya arrancó! ({label})"

    days = int(info.get("days") or 0)
    hours = int(info.get("hours") or 0)
    minutes = int(info.get("minutes") or 0)
    return (
        f"⏳ Faltan {days} {_plural(days, 'día', 'días')}, "
        f"{hours} h y {minutes} min para el primer partido "
        f"({label}{when})"
    )


def interaction_footer_lines(*, html: bool = False) -> str:
    countdown = countdown_text()
    if html:
        from src.services.ai_telegram_format import escape_html

        return (
            f"<i>{escape_html(countdown)}</i>\n"
            f"<i>{escape_html(BASIC_COMMANDS_LINE)}</i>"
        )
    return f"{countdown}\n{BASIC_COMMANDS_LINE}"


def append_interaction_footer(text: str, *, parse_mode: str | None = None) -> str:
    """Agrega countdown + comandos básicos si aún no están presentes."""
    body = (text or "").rstrip()
    if not body:
        return text or ""
    if FOOTER_MARKER in body and "/partidos" in body:
        return text
    html = (parse_mode or "").upper() == "HTML"
    footer = interaction_footer_lines(html=html)
    return f"{body}\n\n{footer}"
