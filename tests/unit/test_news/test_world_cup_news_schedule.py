"""Tests horarios noticias — SPEC-2026-046."""
from __future__ import annotations

from datetime import date, datetime

from src.jobs import world_cup_news_schedule as sched
from src.services.match_service import DISPLAY_TZ


def _match(kickoff: str, status: str = "SCHEDULED") -> dict:
    return {
        "match_id": "m1",
        "home_team": "ARG",
        "away_team": "FRA",
        "kickoff_utc": kickoff,
        "status": status,
    }


def test_news_phase_pre_before_first_kickoff():
    matches = [_match("2026-06-11T19:00:00+00:00")]
    now = datetime(2026, 5, 1, 12, 0, tzinfo=DISPLAY_TZ)
    assert sched.news_phase(matches, now=now) == "PRE"


def test_pre_slot_window_morning():
    now = datetime(2026, 5, 1, 11, 2, tzinfo=DISPLAY_TZ)
    assert sched.pre_slot_window_ok("MORNING", now=now) is True
    assert sched.pre_slot_window_ok("MORNING", now=datetime(2026, 5, 1, 10, 0, tzinfo=DISPLAY_TZ)) is False


def test_live_pre_matchday_window():
    # Partido 18:00 ART → pre 16:00
    matches = [_match("2026-06-11T21:00:00+00:00")]  # 18:00 ART approx
    day = date(2026, 6, 11)
    schedule = sched.compute_live_day_schedule(matches, local_date=day)
    assert schedule is not None
    assert schedule.matches_count == 1
    now = schedule.pre_matchday_at
    assert sched.should_publish_pre_matchday(schedule, now=now) is True


def test_job_ctrl_slot_key():
    assert sched.job_ctrl_slot_key("2026-06-11", "MORNING") == "2026-06-11#MORNING"
