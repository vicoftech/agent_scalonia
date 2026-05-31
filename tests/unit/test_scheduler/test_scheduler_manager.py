"""SPEC-2026-032 — MatchScheduleManager."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.services.scheduler_manager import (
    MatchScheduleManager,
    schedule_expression_at,
    schedule_name,
)


def test_schedule_name_fits_uuid():
    mid = "7ec4c6ec-f11b-5a24-8fd8-7ba47082508b"
    assert len(schedule_name("trivia-pre", mid)) <= 64


def test_schedule_name_hashes_long_ids():
    long_id = "x" * 80
    name = schedule_name("scoring-catchup", long_id)
    assert len(name) <= 64


def test_schedule_expression_at_utc():
    dt = datetime(2026, 6, 15, 18, 30, 0, tzinfo=timezone.utc)
    assert schedule_expression_at(dt) == "at(2026-06-15T18:30:00)"


def test_build_plans_skips_past_fire_times():
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    kickoff = now + timedelta(hours=3)
    mgr = MatchScheduleManager(
        group_name="prode-match-dev",
        invoke_role_arn="arn:aws:iam::123:role/x",
        lambda_arns={
            "LAMBDA_ARN_TRIVIA_PRE_MATCH": "arn:aws:lambda:1",
            "LAMBDA_ARN_MATCH_REMINDER": "arn:aws:lambda:2",
            "LAMBDA_ARN_VEDA_ACTIVATOR": "arn:aws:lambda:3",
            "LAMBDA_ARN_RESULT_COLLECTOR": "arn:aws:lambda:4",
            "LAMBDA_ARN_SCORING_PROCESSOR": "arn:aws:lambda:5",
        },
        enabled=True,
    )
    plans = mgr._build_plans("mid-1", kickoff, now)
    suffixes = {p.suffix for p in plans}
    assert "trivia-pre" in suffixes
    assert "result" in suffixes
    veda = next(p for p in plans if p.suffix == "veda")
    assert veda.fire_at == kickoff - timedelta(minutes=5)


def test_build_plans_empty_when_kickoff_past():
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    kickoff = now - timedelta(days=3)
    mgr = MatchScheduleManager(
        group_name="g",
        invoke_role_arn="arn:aws:iam::123:role/x",
        lambda_arns={
            "LAMBDA_ARN_TRIVIA_PRE_MATCH": "arn:1",
            "LAMBDA_ARN_MATCH_REMINDER": "arn:2",
            "LAMBDA_ARN_VEDA_ACTIVATOR": "arn:3",
            "LAMBDA_ARN_RESULT_COLLECTOR": "arn:4",
            "LAMBDA_ARN_SCORING_PROCESSOR": "arn:5",
        },
        enabled=True,
    )
    assert mgr._build_plans("mid", kickoff, now) == []


def test_is_enabled_requires_config():
    mgr = MatchScheduleManager(enabled=True)
    assert mgr.is_enabled() is False
