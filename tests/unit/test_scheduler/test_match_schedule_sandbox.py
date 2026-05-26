"""SPEC-2026-041 — sandbox schedule offsets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.services.match_schedule_sandbox import (
    SANDBOX_SCHEDULE_SPECS,
    _build_sandbox_plans,
    build_sandbox_plans_for_dry_run,
    sandbox_schedule_name,
)
def test_sandbox_names_use_devfast_prefix():
    name = sandbox_schedule_name("devfast-trivia", "mid-uuid")
    assert name.startswith("devfast-trivia-")
    assert "trivia-pre-" not in name


def test_staggered_bump_assigns_unique_times():
    started = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    now = started + timedelta(seconds=30)
    arns = {spec[3]: f"arn:aws:lambda:1:{spec[0]}" for spec in SANDBOX_SCHEDULE_SPECS}
    plans = _build_sandbox_plans("mid", started, now, arns)
    times = [p.fire_at for p in plans]
    assert len(times) == len(set(times))


def test_build_sandbox_plans_seven_events():
    started = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    arns = {spec[3]: f"arn:aws:lambda:1:{spec[0]}" for spec in SANDBOX_SCHEDULE_SPECS}
    plans = _build_sandbox_plans("mid", started, started - timedelta(seconds=1), arns)
    assert len(plans) == 7
    offsets = sorted(int((p.fire_at - started).total_seconds()) for p in plans)
    assert offsets == list(range(0, 7 * 15, 15))


def test_dry_run_helper():
    rows = build_sandbox_plans_for_dry_run("abc")
    assert len(rows) == 7
    assert rows[0]["name"].startswith("devfast-trivia-")
