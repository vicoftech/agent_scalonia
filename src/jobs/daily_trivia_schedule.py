"""
Horario de publicación de la trivia diaria (Argentina GMT-3).

- Objetivo: 10:00 ART.
- Límite: al menos 2 h antes del primer partido del día (calendario local).
- Hora efectiva: min(10:00, primer_partido − 2h).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from src.services.match_service import DISPLAY_TZ, _parse_dt

DAILY_TRIVIA_LOCAL_HOUR = 10
MIN_HOURS_BEFORE_FIRST_MATCH = 2
EARLIEST_PUBLISH_HOUR = 6  # no publicar antes de las 06:00 ART


def local_today() -> date:
    return datetime.now(DISPLAY_TZ).date()


def local_today_iso() -> str:
    return local_today().isoformat()


def matches_on_local_date(matches: list[dict[str, Any]], local_date: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in matches:
        status = (m.get("status") or "SCHEDULED").upper()
        if status not in ("SCHEDULED", "LIVE"):
            continue
        kick = _parse_dt(m["kickoff_utc"]).astimezone(DISPLAY_TZ)
        if kick.date() == local_date:
            out.append(m)
    return out


def first_kickoff_local(matches_today: list[dict[str, Any]]) -> datetime | None:
    if not matches_today:
        return None
    return min(_parse_dt(m["kickoff_utc"]).astimezone(DISPLAY_TZ) for m in matches_today)


@dataclass(frozen=True)
class DailyTriviaSchedule:
    local_date: str
    publish_at_local: datetime
    first_kickoff_local: datetime | None
    matches_today: int

    @property
    def publish_at_iso(self) -> str:
        return self.publish_at_local.isoformat()


def compute_daily_trivia_schedule(
    matches: list[dict[str, Any]],
    *,
    local_date: date | None = None,
) -> DailyTriviaSchedule:
    day = local_date or local_today()
    today_matches = matches_on_local_date(matches, day)
    first = first_kickoff_local(today_matches)
    target = datetime.combine(day, time(DAILY_TRIVIA_LOCAL_HOUR, 0), tzinfo=DISPLAY_TZ)
    if first is None:
        publish_at = target
    else:
        deadline = first - timedelta(hours=MIN_HOURS_BEFORE_FIRST_MATCH)
        publish_at = min(target, deadline)
    return DailyTriviaSchedule(
        local_date=day.isoformat(),
        publish_at_local=publish_at,
        first_kickoff_local=first,
        matches_today=len(today_matches),
    )


def in_publish_window(now: datetime | None = None) -> bool:
    """Evita invocaciones inútiles antes de las 06:00 ART."""
    now = now or datetime.now(DISPLAY_TZ)
    return now.hour >= EARLIEST_PUBLISH_HOUR


def should_publish_daily_trivia(
    schedule: DailyTriviaSchedule,
    *,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(DISPLAY_TZ)
    if not in_publish_window(now):
        return False
    return now >= schedule.publish_at_local
