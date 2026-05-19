"""Banco curado de trivias — sin meta-preguntas."""
from src.services.trivia_question_bank import (
    is_meta_source_question,
    pick_curated_question,
    question_fingerprint,
)


def test_meta_source_question_detected():
    assert is_meta_source_question(
        "¿Qué información es más precisa?",
        {"A": "Knowledge Base", "B": "Wikipedia", "C": "Tavily", "D": "Fixture"},
    )


def test_pick_excludes_fingerprint():
    q1 = pick_curated_question(topic="mundiales", level="MEDIUM")
    assert q1
    fp = q1["question_fp"]
    q2 = pick_curated_question(
        topic="mundiales",
        level="MEDIUM",
        exclude_fingerprints={fp},
    )
    if q2:
        assert q2["question_fp"] != fp


def test_fingerprint_stable():
    assert question_fingerprint("  Hola   Mundo ") == question_fingerprint("hola mundo")
