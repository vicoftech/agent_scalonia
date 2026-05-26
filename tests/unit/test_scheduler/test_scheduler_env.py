"""Scheduler env normalization — SPEC-032 / SPEC-041."""
from __future__ import annotations

import os

import pytest

from src.services.scheduler_manager import (
    _lambda_arns_configured_count,
    auto_configure_scheduler_env,
    normalize_scheduler_env,
)


@pytest.fixture(autouse=True)
def _clean_scheduler_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("SCHEDULER_", "LAMBDA_ARN_", "ENABLE_MATCH_SCHEDULES")):
            monkeypatch.delenv(key, raising=False)


def test_normalize_scheduler_env_replaces_terraform_garbage(monkeypatch):
    monkeypatch.setenv(
        "SCHEDULER_GROUP_NAME",
        "╷\n│ Warning: No outputs found\n╵",
    )
    out = normalize_scheduler_env("dev")
    assert out == "prode-match-dev"
    assert os.environ["SCHEDULER_GROUP_NAME"] == "prode-match-dev"


def test_auto_configure_ok_when_arns_already_set(monkeypatch):
    monkeypatch.setenv("SCHEDULER_GROUP_NAME", "prode-match-dev")
    monkeypatch.setenv("SCHEDULER_INVOKE_ROLE_ARN", "arn:aws:iam::1:role/x")
    for i, key in enumerate(
        (
            "LAMBDA_ARN_TRIVIA_PRE_MATCH",
            "LAMBDA_ARN_MATCH_REMINDER",
            "LAMBDA_ARN_VEDA_ACTIVATOR",
            "LAMBDA_ARN_RESULT_COLLECTOR",
            "LAMBDA_ARN_SCORING_PROCESSOR",
        )
    ):
        monkeypatch.setenv(key, f"arn:aws:lambda:1:fn:{i}")

    assert _lambda_arns_configured_count() == 5
    assert auto_configure_scheduler_env("dev", profile="nope") is True
