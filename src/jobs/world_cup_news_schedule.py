"""Horarios de noticias Mundial — SPEC-2026-046."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from src.services.match_service import DISPLAY_TZ, _parse_dt

NewsPhase = Literal["PRE", "LIVE"]
PreSlot = Literal["MORNING", "EVENING"]
LiveSlot = Literal["PRE_MATCHDAY", "POST_MATCHDAY"]

ESTIMATED_MATCH_MINUTES = 110
POST_BUFFER_MINUTES = 60
PRE_HOURS_BEFORE_FIRST = 2

MATCHDAY_STATUSES = frozenset({"SCHEDULED", "VEDA", "LIVE", "FINISHED"})


def local_today() -> date:
    return datetime.now(DISPLAY_TZ).date()


def local_today_iso() -> str:
    return local_today().isoformat()


def first_mundial_local_date(matches: list[dict[str, Any]]) -> date:
    kickoffs = [
        _parse_dt(m["kickoff_utc"]).astimezone(DISPLAY_TZ)
        for m in matches
        if m.get("kickoff_utc")
    ]
    if not kickoffs:
        return date(2026, 6, 11)
    return min(kickoffs).date()


def news_phase(
    matches: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> NewsPhase:
    now = now or datetime.now(DISPLAY_TZ)
    first_day = first_mundial_local_date(matches)
    if now.date() < first_day:
        return "PRE"
    return "LIVE"


def matches_on_local_date(
    matches: list[dict[str, Any]],
    local_date: date,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in matches:
        status = (m.get("status") or "SCHEDULED").upper()
        if status not in MATCHDAY_STATUSES:
            continue
        home = (m.get("home_team") or "").upper()
        away = (m.get("away_team") or "").upper()
        if home == "TBD" or away == "TBD":
            continue
        kick = _parse_dt(m["kickoff_utc"]).astimezone(DISPLAY_TZ)
        if kick.date() == local_date:
            out.append(m)
    return out


def job_ctrl_slot_key(run_date: str, slot: str) -> str:
    return f"{run_date}#{slot}"


@dataclass(frozen=True)
class LiveNewsDaySchedule:
    local_date: str
    idempotency_date: str
    first_kickoff_local: datetime
    last_kickoff_local: datetime
    pre_matchday_at: datetime
    post_matchday_at: datetime
    matches_count: int


def compute_live_day_schedule(
    matches: list[dict[str, Any]],
    *,
    local_date: date | None = None,
) -> LiveNewsDaySchedule | None:
    day = local_date or local_today()
    today_matches = matches_on_local_date(matches, day)
    if not today_matches:
        return None
    kickoffs = [_parse_dt(m["kickoff_utc"]).astimezone(DISPLAY_TZ) for m in today_matches]
    first = min(kickoffs)
    last = max(kickoffs)
    pre_at = first - timedelta(hours=PRE_HOURS_BEFORE_FIRST)
    post_at = last + timedelta(minutes=ESTIMATED_MATCH_MINUTES + POST_BUFFER_MINUTES)
    return LiveNewsDaySchedule(
        local_date=day.isoformat(),
        idempotency_date=last.date().isoformat(),
        first_kickoff_local=first,
        last_kickoff_local=last,
        pre_matchday_at=pre_at,
        post_matchday_at=post_at,
        matches_count=len(today_matches),
    )


def _in_five_minute_window(now: datetime, target: datetime) -> bool:
    return target <= now < target + timedelta(minutes=6)


def should_publish_pre_matchday(
    schedule: LiveNewsDaySchedule,
    *,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(DISPLAY_TZ)
    return _in_five_minute_window(now, schedule.pre_matchday_at)


def should_publish_post_matchday(
    schedule: LiveNewsDaySchedule,
    *,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(DISPLAY_TZ)
    return _in_five_minute_window(now, schedule.post_matchday_at)


def pre_slot_window_ok(slot: PreSlot, *, now: datetime | None = None) -> bool:
    """Ventana de 6 min tras la hora fija PRE (cron 11:00 / 17:00)."""
    now = now or datetime.now(DISPLAY_TZ)
    hour = 11 if slot == "MORNING" else 17
    target = datetime.combine(now.date(), time(hour, 0), tzinfo=DISPLAY_TZ)
    return _in_five_minute_window(now, target)
