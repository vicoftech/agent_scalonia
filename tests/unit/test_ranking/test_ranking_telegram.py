"""Mi ranking Telegram — SPEC-2026-042."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("boto3")

_LAMBDA_DIR = Path(__file__).resolve().parents[3] / "infrastructure" / "lambdas" / "telegram_webhook"
if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))

from ranking_commands import handle_mi_ranking_command  # noqa: E402
from ranking_telegram_ui import format_ranking_message, group_picker_keyboard  # noqa: E402


@patch("ranking_commands.RankingService")
@patch("ranking_commands.PredictionService")
def test_no_groups_uses_no_group_message(mock_pred_svc, mock_rank_svc):
    mock_rank_svc.return_value.list_user_groups_for_ranking.return_value = []
    mock_pred_svc.return_value.no_group_message.return_value = ("sin grupo", {"inline_keyboard": []})

    text, markup = handle_mi_ranking_command("u1")
    assert text == "sin grupo"
    assert markup == {"inline_keyboard": []}


@patch("ranking_commands.show_group_ranking")
@patch("ranking_commands.RankingService")
def test_single_group_skips_picker(mock_rank_svc, mock_show):
    mock_rank_svc.return_value.list_user_groups_for_ranking.return_value = [
        {"group_id": "g1", "name": "Scaloneta", "avatar": "⚽"}
    ]
    mock_show.return_value = ("ranking", None)

    text, markup = handle_mi_ranking_command("u1")
    mock_show.assert_called_once_with("u1", "g1")
    assert text == "ranking"
    assert markup is None


@patch("ranking_commands.RankingService")
def test_multiple_groups_show_picker(mock_rank_svc):
    mock_rank_svc.return_value.list_user_groups_for_ranking.return_value = [
        {"group_id": "g1", "name": "A", "avatar": "⚽"},
        {"group_id": "g2", "name": "B", "avatar": "🏆"},
    ]

    text, markup = handle_mi_ranking_command("u1")
    assert text == "Elegí el grupo:"
    assert markup == group_picker_keyboard(mock_rank_svc.return_value.list_user_groups_for_ranking.return_value)


def test_format_ranking_marks_viewer_and_footer():
    ranking = {
        "group_name": "Scaloneta",
        "rows": [
            {"position": 1, "alias": "Ana", "points": 23, "is_viewer": False},
            {"position": 2, "alias": "Luis", "points": 19, "is_viewer": False},
            {"position": 3, "alias": "toti", "points": 12, "is_viewer": True},
        ],
    }
    text = format_ranking_message(ranking)
    assert "🏆 Ranking — Scaloneta" in text
    assert "👉 #3 vos — 12 pts" in text
    assert "Actualizado tras cada partido puntuado." in text


def test_format_ranking_global_title():
    ranking = {
        "group_name": "Global",
        "is_global": True,
        "rows": [{"position": 1, "alias": "toti", "points": 0, "is_viewer": True}],
    }
    text = format_ranking_message(ranking)
    assert "🌍 Ranking Global" in text
    assert "👉 #1 vos — 0 pts" in text
