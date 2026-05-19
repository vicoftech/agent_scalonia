"""SPEC-025 — trivia service."""
from unittest.mock import MagicMock, patch

from src.services.trivia_service import TriviaService


def test_level_from_profile():
    users = MagicMock()
    users.get_profile.return_value = {"football_knowledge": "hard"}
    svc = TriviaService(user_dao=users)
    assert svc.level_for_user("u1") == "EXPERT"


def test_generate_fallback_question():
    svc = TriviaService()
    q = svc.generate_trivia_question(topic="records", level="EXPERT")
    assert q["correct"] in ("A", "B", "C", "D")
    assert len(q["options"]) == 4


def test_answer_play_correct_points():
    trivia = MagicMock()
    users = MagicMock()
    users.get_profile.return_value = {"total_points": 10, "trivia_rounds_today": 1}
    users.get_answered_question_fingerprints.return_value = set()
    trivia.get_play_session.return_value = {
        "state": "PENDING",
        "correct_answer": "B",
        "correct": "B",
        "points": 3,
        "question_fp": "abc123",
        "options_map": {"B": "México"},
        "explanation": "1986 en México",
        "level": "MEDIUM",
    }
    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    msg = svc.answer_play_session("u1", "sess-1", "B")
    assert "Correcto" in msg
    assert "+3" in msg
    users.add_trivia_round.assert_called_once_with("u1", points=3)


def test_answer_play_duplicate_fingerprint_no_points():
    trivia = MagicMock()
    users = MagicMock()
    users.get_profile.return_value = {"total_points": 10, "trivia_rounds_today": 1}
    users.get_answered_question_fingerprints.return_value = {"samefp"}
    trivia.get_play_session.return_value = {
        "state": "PENDING",
        "correct": "B",
        "points": 3,
        "question_fp": "samefp",
        "options_map": {"B": "México"},
        "explanation": "x",
    }
    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    msg = svc.answer_play_session("u1", "sess-1", "B")
    assert "duplicados" in msg.lower() or "Ya habías" in msg
    users.add_trivia_round.assert_called_once_with("u1", points=0)


def test_answer_broadcast_counts_round():
    trivia = MagicMock()
    users = MagicMock()
    users.get_profile.return_value = {"total_points": 0, "trivia_rounds_today": 0}
    users.get_answered_question_fingerprints.return_value = set()
    trivia.get_trivia.return_value = {
        "correct": "A",
        "points": 5,
        "options": {"A": "Brasil"},
        "closes_at": "2099-01-01T00:00:00Z",
        "explanation": "x",
        "question": "Q?",
    }
    trivia.has_answered.return_value = False
    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    svc.answer_broadcast("u1", "triv-1", "A")
    users.add_trivia_round.assert_called_once_with("u1", points=5)


def test_answer_play_wrong_answer_still_counts_round():
    trivia = MagicMock()
    users = MagicMock()
    users.get_profile.return_value = {"total_points": 0, "trivia_rounds_today": 0}
    users.get_answered_question_fingerprints.return_value = set()
    trivia.get_play_session.return_value = {
        "state": "PENDING",
        "correct": "B",
        "points": 3,
        "question_fp": "fp1",
        "options_map": {"B": "x"},
        "explanation": "x",
    }
    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    svc.answer_play_session("u1", "sess-1", "A")
    users.add_trivia_round.assert_called_once_with("u1", points=0)


def test_daily_limit():
    users = MagicMock()
    users.get_profile.return_value = {"trivia_rounds_today": 5}
    svc = TriviaService(user_dao=users)
    try:
        svc.start_play("u1")
        assert False, "expected DAILY_LIMIT"
    except ValueError as e:
        assert str(e) == "DAILY_LIMIT"


def test_broadcast_already_answered():
    trivia = MagicMock()
    users = MagicMock()
    users.get_profile.return_value = {"trivia_rounds_today": 0}
    trivia.get_trivia.return_value = {
        "correct": "C",
        "points": 5,
        "options": {"C": "Klose"},
        "closes_at": "2099-01-01T00:00:00Z",
        "explanation": "x",
    }
    trivia.has_answered.return_value = True
    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    assert "Ya respondiste" in svc.answer_broadcast("u1", "abc", "C")
    users.add_trivia_round.assert_not_called()
