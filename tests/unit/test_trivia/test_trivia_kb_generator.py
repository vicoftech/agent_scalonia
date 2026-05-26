"""Trivia KB pre-partido."""
from __future__ import annotations

from unittest.mock import patch

from src.services.trivia_kb_generator import (
    _question_references_match,
    generate_pre_match_question,
)
from src.services.trivia_question_bank import (
    pick_curated_for_match_strict,
    pick_curated_for_teams,
)


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
                "question": "¿Cuántas Copas ganó México frente a Sudáfrica en amistosos?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "correct": "A",
                "level": "EXPERT",
                "question_fp": "abc",
                "source": "kb_bedrock",
            },
        ):
            q = generate_pre_match_question(match, exclude_fingerprints=set())
    assert q["correct"] == "A"
    assert q["source"] == "kb_bedrock"


def test_question_references_match_requires_both_teams():
    assert _question_references_match(
        "México y Sudáfrica se enfrentan en el grupo A",
        "MEX",
        "RSA",
    )
    assert not _question_references_match(
        "¿Quién ganó el Mundial 1998?",
        "MEX",
        "RSA",
    )


def test_pick_curated_strict_no_generic_zidane():
    q = pick_curated_for_match_strict(home="MEX", away="RSA", level="EXPERT")
    if q:
        assert "MEX" in q["question"].upper() or "MÉXICO" in q["question"].upper()
        assert "RSA" in q["question"].upper() or "SUDÁFRICA" in q["question"].upper()


def test_generate_pre_match_fixture_template_when_kb_empty():
    match = {"match_id": "m1", "home_team": "MEX", "away_team": "RSA", "group_letter": "A"}
    with patch(
        "src.services.trivia_kb_generator.fetch_pre_match_kb_context",
        return_value="",
    ):
        with patch(
            "src.services.trivia_kb_generator.pick_curated_for_match_strict",
            return_value=None,
        ):
            q = generate_pre_match_question(match)
    assert q["source"] == "fixture_template"
    assert "México" in q["question"] or "MEX" in q["question"]
