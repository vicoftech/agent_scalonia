"""Import smoke — telegram webhook debe incluir src/models en el zip."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
TG_DIR = ROOT / "infrastructure" / "lambdas" / "telegram_webhook"
if str(TG_DIR) not in sys.path:
    sys.path.insert(0, str(TG_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_result_admin_commands_imports_match_result():
    import result_admin_commands  # noqa: F401

    from src.models.match_result import MatchResult

    assert MatchResult(home_goals=1, away_goals=0)


def test_resultado_editar_usage_without_teams():
    from result_admin_commands import handle_result_admin_command

    with patch("result_admin_commands._admin_only", return_value=True):
        with patch("result_admin_commands._list_published", return_value=""):
            reply, markup = handle_result_admin_command("admin-1", "/resultado_editar")
    assert reply
    assert "MEX RSA" in reply or "HOME AWAY" in reply
    assert markup is None
