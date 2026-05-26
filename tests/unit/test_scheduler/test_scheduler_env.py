"""Scheduler env normalization — SPEC-032 / SPEC-041."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.services.scheduler_manager import (
    _lambda_arns_configured_count,
    _scheduler_env_fully_configured,
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


def test_normalize_clears_invalid_scheduler_role_arn(monkeypatch):
    monkeypatch.setenv(
        "SCHEDULER_INVOKE_ROLE_ARN",
        "╷\n│ Warning: No outputs found\n╵",
    )
    normalize_scheduler_env("dev")
    assert "SCHEDULER_INVOKE_ROLE_ARN" not in os.environ


def test_garbage_role_not_fully_configured(monkeypatch):
    monkeypatch.setenv("SCHEDULER_GROUP_NAME", "prode-match-dev")
    monkeypatch.setenv(
        "SCHEDULER_INVOKE_ROLE_ARN",
        "╷\n│ Warning: No outputs found\n╵",
    )
    monkeypatch.setenv(
        "LAMBDA_ARN_TRIVIA_PRE_MATCH",
        "arn:aws:lambda:us-east-1:615216531593:function:prode-trivia-pre-match-dev",
    )
    assert not _scheduler_env_fully_configured()
    normalize_scheduler_env("dev")
    assert "SCHEDULER_INVOKE_ROLE_ARN" not in os.environ


def test_auto_configure_ok_when_arns_already_set(monkeypatch):
    monkeypatch.setenv("SCHEDULER_GROUP_NAME", "prode-match-dev")
    monkeypatch.setenv("SCHEDULER_INVOKE_ROLE_ARN", "arn:aws:iam::123456789012:role/prode-scheduler-invoke-dev")
    for i, key in enumerate(
        (
            "LAMBDA_ARN_TRIVIA_PRE_MATCH",
            "LAMBDA_ARN_MATCH_REMINDER",
            "LAMBDA_ARN_VEDA_ACTIVATOR",
            "LAMBDA_ARN_RESULT_COLLECTOR",
            "LAMBDA_ARN_SCORING_PROCESSOR",
        )
    ):
        monkeypatch.setenv(
            key,
            f"arn:aws:lambda:us-east-1:123456789012:function:prode-fn-{i}",
        )

    assert _lambda_arns_configured_count() == 5
    assert _scheduler_env_fully_configured()
    with patch("src.dao.dynamo.table.configure_aws"):
        assert auto_configure_scheduler_env("dev", profile="nope") is True


def test_auto_configure_resolves_role_when_garbage_cleared(monkeypatch):
    monkeypatch.setenv("SCHEDULER_GROUP_NAME", "prode-match-dev")
    for key in (
        "LAMBDA_ARN_TRIVIA_PRE_MATCH",
        "LAMBDA_ARN_MATCH_REMINDER",
        "LAMBDA_ARN_VEDA_ACTIVATOR",
        "LAMBDA_ARN_RESULT_COLLECTOR",
        "LAMBDA_ARN_SCORING_PROCESSOR",
    ):
        monkeypatch.setenv(
            key,
            "arn:aws:lambda:us-east-1:123456789012:function:prode-x-dev",
        )
    mock_iam = MagicMock()
    mock_iam.get_role.return_value = {
        "Role": {"Arn": "arn:aws:iam::123456789012:role/prode-scheduler-invoke-dev"}
    }
    mock_lam = MagicMock()
    with patch("src.dao.dynamo.table.configure_aws"):
        with patch("src.dao.dynamo.table.get_session") as gs:
            gs.return_value.client.side_effect = (
                lambda svc, **_: mock_iam if svc == "iam" else mock_lam
            )
            assert auto_configure_scheduler_env("dev") is True
    assert os.environ["SCHEDULER_INVOKE_ROLE_ARN"].startswith("arn:aws:iam::")
