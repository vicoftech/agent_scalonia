"""Curación de calidad en trivias MCQ."""
from src.services.trivia_curation import validate_trivia_mcq


def test_rejects_penalties_question_with_regular_time_explanation():
    bad = {
        "question": (
            "En el Mundial 1990, ¿qué selección eliminó a Inglaterra en semifinales "
            "con los penales de Schillaci y Aldo Serena?"
        ),
        "options": {"A": "Alemania", "B": "Italia", "C": "Argentina", "D": "Brasil"},
        "correct": "B",
        "explanation": "Italia venció a Inglaterra 2-1 en Turín y llegó a la final en casa.",
    }
    ok, reason = validate_trivia_mcq(bad)
    assert not ok
    assert reason == "penalties_question_regular_time_explanation"


def test_accepts_fixed_italy_1990_question():
    good = {
        "question": (
            "En el Mundial 1990, ¿qué selección eliminó a Inglaterra en semifinales "
            "con un 2-1 en Turín, con goles de Schillaci y Tardelli?"
        ),
        "options": {"A": "Alemania", "B": "Italia", "C": "Argentina", "D": "Brasil"},
        "correct": "B",
        "explanation": (
            "Italia venció 2-1 a Inglaterra en semifinales; Schillaci y Tardelli marcaron "
            "para la Azzurra y Lineker descontó para Inglaterra."
        ),
    }
    ok, _ = validate_trivia_mcq(good)
    assert ok


def test_rejects_when_explanation_does_not_support_correct():
    q = {
        "question": "¿Quién ganó el Mundial 2014?",
        "options": {"A": "Brasil", "B": "Alemania", "C": "Argentina", "D": "España"},
        "correct": "B",
        "explanation": "Argentina llegó a la final en el Maracaná.",
    }
    ok, reason = validate_trivia_mcq(q)
    assert not ok
    assert reason == "correct_answer_not_supported"


def test_accepts_penalties_when_explanation_also_mentions_them():
    q = {
        "question": "¿Quién ganó la final de 1994 en penales?",
        "options": {"A": "Italia", "B": "Brasil", "C": "Alemania", "D": "Argentina"},
        "correct": "B",
        "explanation": "Brasil venció a Italia 3-2 en la tanda de penales tras el 0-0.",
    }
    ok, _ = validate_trivia_mcq(q)
    assert ok
