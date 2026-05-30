"""Comandos ampliación grupos — SPEC-2026-044."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("boto3")

_LAMBDA_DIR = Path(__file__).resolve().parents[3] / "infrastructure" / "lambdas" / "telegram_webhook"
if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))

from group_upgrade_commands import handle_group_upgrade_command  # noqa: E402


@patch("group_upgrade_commands._service")
def test_ampliar_plan_starts_wizard(mock_svc):
    mock_svc.return_value.start_wizard.return_value = ("wizard", {"inline_keyboard": []})
    text, markup = handle_group_upgrade_command("u1", "/ampliar_plan")
    assert text == "wizard"
    mock_svc.return_value.start_wizard.assert_called_once_with("u1")


@patch("group_upgrade_commands._service")
def test_admin_otorgar_grupo(mock_svc):
    mock_svc.return_value.admin_grant_group_slots.return_value = "ok"
    text, markup = handle_group_upgrade_command("admin", "/grupo_otorgar_grupo toti 2")
    assert text == "ok"
    mock_svc.return_value.admin_grant_group_slots.assert_called_once_with("admin", "toti", 2)
