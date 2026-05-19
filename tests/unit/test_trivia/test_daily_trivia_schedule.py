"""Horario trivia diaria — 10:00 ART y 2 h antes del primer partido."""
from datetime import date, datetime, time, timedelta

from src.jobs.daily_trivia_schedule import (
    compute_daily_trivia_schedule,
    should_publish_daily_trivia,
)
from src.services.match_service import DISPLAY_TZ


def _kickoff_utc(local_day: date, hour: int, minute: int = 0) -> str:
    local = datetime.combine(local_day, time(hour, minute), tzinfo=DISPLAY_TZ)
    return local.astimezone(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_publish_at_10_when_late_first_match():
    day = date(2026, 6, 17)
    matches = [
        {
            "kickoff_utc": _kickoff_utc(day, 22, 0),
            "status": "SCHEDULED",
        }
    ]
    sched = compute_daily_trivia_schedule(matches, local_date=day)
    assert sched.publish_at_local.hour == 10
    assert sched.publish_at_local.minute == 0


def test_publish_2h_before_early_first_match():
    day = date(2026, 6, 17)
    matches = [
        {
            "kickoff_utc": _kickoff_utc(day, 11, 0),
            "status": "SCHEDULED",
        }
    ]
    sched = compute_daily_trivia_schedule(matches, local_date=day)
    assert sched.publish_at_local.hour == 9
    assert sched.publish_at_local.minute == 0


def test_publish_at_10_when_no_matches():
    day = date(2026, 6, 18)
    sched = compute_daily_trivia_schedule([], local_date=day)
    assert sched.publish_at_local.hour == 10
    assert sched.matches_today == 0


def test_should_publish_after_target():
    day = date(2026, 6, 17)
    sched = compute_daily_trivia_schedule([], local_date=day)
    now = datetime.combine(day, time(10, 5), tzinfo=DISPLAY_TZ)
    assert should_publish_daily_trivia(sched, now=now)


def test_not_yet_before_target():
    day = date(2026, 6, 17)
    sched = compute_daily_trivia_schedule([], local_date=day)
    now = datetime.combine(day, time(9, 30), tzinfo=DISPLAY_TZ)
    assert not should_publish_daily_trivia(sched, now=now)
