"""Banco curado de trivias — sin meta-preguntas."""
from src.fixtures.trivia_questions import FALLBACK_QUESTIONS
from src.services.trivia_question_bank import (
    is_meta_source_question,
    pick_any_curated_question,
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


def test_pick_any_respects_exclude():
    all_fps = {question_fingerprint(q["question"]) for q in FALLBACK_QUESTIONS}
    assert pick_any_curated_question(exclude_fingerprints=all_fps) is None


def test_generate_never_returns_hardcoded_first_when_others_available():
    from src.services.trivia_service import TriviaService

    first_fp = question_fingerprint(FALLBACK_QUESTIONS[0]["question"])
    q = TriviaService().generate_trivia_question(
        topic="records",
        level="EXPERT",
        exclude_fingerprints={first_fp},
    )
    assert question_fingerprint(q["question"]) != first_fp
