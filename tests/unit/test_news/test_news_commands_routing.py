"""Routing /noticia vs otros comandos — SPEC-2026-046."""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("boto3")

import sys
from pathlib import Path

_LAMBDA_DIR = Path(__file__).resolve().parents[3] / "infrastructure" / "lambdas" / "telegram_webhook"
if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))

from news_commands import handle_news_command  # noqa: E402


def test_non_admin_partidos_does_not_hit_news_handler():
    with patch("news_commands._admin_only", return_value=False):
        reply, markup = handle_news_command("user-1", "/partidos")
    assert reply is None
    assert markup is None


def test_non_admin_noticia_shows_admin_message():
    with patch("news_commands._admin_only", return_value=False):
        reply, markup = handle_news_command("user-1", "/noticia")
    assert reply == "Solo administradores pueden publicar noticias."
    assert markup is None
