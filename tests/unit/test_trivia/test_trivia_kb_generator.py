"""Trivia KB pre-partido."""
from __future__ import annotations

from unittest.mock import patch

from src.services.trivia_kb_generator import generate_pre_match_question
from src.services.trivia_question_bank import pick_curated_for_teams


def test_pick_curated_for_teams_mex_rsa():
    q = pick_curated_for_teams(home="MEX", away="RSA", level="EXPERT")
    assert q is not None
    blob = (q["question"] + " " + " ".join(q["options"].values())).upper()
    assert "MEX" in blob or "RSA" in blob or "MÉXICO" in blob or "SUDÁFRICA" in blob


def test_generate_pre_match_uses_kb_when_context_rich():
    match = {"match_id": "m1", "home_team": "MEX", "away_team": "RSA"}
    with patch(
        "src.services.trivia_kb_generator.fetch_pre_match_kb_context",
        return_value="x" * 100,
    ):
        with patch(
            "src.services.trivia_kb_generator.generate_question_from_kb",
            return_value={
                "question": "¿Cuántas Copas ganó el equipo?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "correct": "A",
                "level": "EXPERT",
                "question_fp": "abc",
            },
        ):
            q = generate_pre_match_question(match, exclude_fingerprints=set())
    assert q["correct"] == "A"
