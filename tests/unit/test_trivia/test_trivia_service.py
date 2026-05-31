"""SPEC-025 / SPEC-049 — trivia service."""
from unittest.mock import MagicMock, patch

from src.services.trivia_service import TriviaService


def test_level_from_profile():
    users = MagicMock()
    users.get_profile.return_value = {"football_knowledge": "hard"}
    svc = TriviaService(user_dao=users)
    assert svc.level_for_user("u1") == "EXPERT"


def test_level_maps_casual_fanatico_experto():
    users = MagicMock()
    svc = TriviaService(user_dao=users)
    users.get_profile.return_value = {"football_knowledge": "easy"}
    assert svc.level_for_user("u1") == "BASIC"
    users.get_profile.return_value = {"football_knowledge": "medium"}
    assert svc.level_for_user("u1") == "MEDIUM"
    users.get_profile.return_value = {"football_knowledge": "hard"}
    assert svc.level_for_user("u1") == "EXPERT"


def test_generate_fallback_question():
    svc = TriviaService()
    with patch(
        "src.services.trivia_service.TriviaService._fetch_context",
        return_value=("", "kb"),
    ):
        q = svc.generate_trivia_question(topic="records", level="EXPERT")
    assert q["correct"] in ("A", "B", "C", "D")
    assert len(q["options"]) == 4
    assert q.get("source") == "manual"


def test_generate_uses_kb_not_only_fallback():
    trivia = MagicMock()
    trivia.get_used_question_fingerprints.return_value = set()
    users = MagicMock()
    users.get_answered_question_fingerprints.return_value = set()
    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    generated = {
        "question": "¿Cuántos Mundiales ganó Brasil?",
        "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
        "correct": "C",
        "level": "MEDIUM",
        "topic": "records",
        "question_fp": "genfp1",
        "source": "kb_bedrock",
        "explanation": "Cinco títulos.",
    }
    with patch.object(svc, "_fetch_context", return_value=("x" * 100, "kb")):
        with patch(
            "src.services.trivia_kb_generator.generate_question_from_context",
            return_value=generated,
        ):
            q = svc.generate_trivia_question(topic="records", level="MEDIUM")
    assert q["source"] == "kb_bedrock"
    assert q["question_fp"] == "genfp1"


def test_fingerprint_retry_on_collision():
    trivia = MagicMock()
    trivia.get_used_question_fingerprints.return_value = {"blocked"}
    svc = TriviaService(trivia_dao=trivia)
    blocked = {
        "question": "Q1?",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "correct": "A",
        "question_fp": "blocked",
        "source": "kb_bedrock",
        "level": "BASIC",
        "topic": "mundiales",
    }
    ok = {
        "question": "Q2?",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "correct": "B",
        "question_fp": "newfp",
        "source": "kb_bedrock",
        "level": "BASIC",
        "topic": "mundiales",
    }
    with patch.object(svc, "_fetch_context", return_value=("x" * 100, "kb")):
        with patch(
            "src.services.trivia_kb_generator.generate_question_from_context",
            side_effect=[blocked, ok],
        ):
            q = svc.generate_trivia_question(
                topic="mundiales",
                level="BASIC",
                exclude_fingerprints={"blocked"},
            )
    assert q["question_fp"] == "newfp"


def test_admin_skips_daily_limit():
    users = MagicMock()
    users.get_profile.return_value = {
        "is_admin": True,
        "trivia_rounds_today": 10,
        "football_knowledge": "medium",
    }
    users.get_answered_question_fingerprints.return_value = set()
    trivia = MagicMock()
    trivia.get_used_question_fingerprints.return_value = set()
    trivia.put_play_session.return_value = {}
    svc = TriviaService(user_dao=users, trivia_dao=trivia)
    generated = {
        "question": "Admin Q?",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "correct": "A",
        "level": "MEDIUM",
        "topic": "mundiales",
        "question_fp": "adm1",
        "source": "kb_bedrock",
    }
    with patch.object(svc, "_fetch_context", return_value=("x" * 100, "kb")):
        with patch(
            "src.services.trivia_kb_generator.generate_question_from_context",
            return_value=generated,
        ):
            result = svc.start_play("admin1")
    assert "session_id" in result
    assert "ilimitadas" in result["message"]


def test_generation_failed_when_no_context_and_no_curated():
    trivia = MagicMock()
    trivia.get_used_question_fingerprints.return_value = {f"fp{i}" for i in range(100)}
    users = MagicMock()
    users.get_answered_question_fingerprints.return_value = set()
    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    with patch.object(svc, "_fetch_context", return_value=("", "kb")):
        with patch(
            "src.services.trivia_service.pick_curated_question",
            return_value=None,
        ):
            with patch(
                "src.services.trivia_service.pick_any_curated_question",
                return_value=None,
            ):
                try:
                    svc.generate_trivia_question(topic="mundiales", level="BASIC")
                    assert False, "expected GENERATION_FAILED"
                except ValueError as exc:
                    assert str(exc) == "GENERATION_FAILED"


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
