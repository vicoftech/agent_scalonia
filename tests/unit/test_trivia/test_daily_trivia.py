"""Trivia diaria general — historias de mundiales."""
from unittest.mock import MagicMock, patch

from src.services.trivia_service import (
    DAILY_GENERAL_TOPIC,
    DAILY_TRIVIA_JOB,
    TriviaService,
)


def test_generate_historias_mundiales_fallback():
    svc = TriviaService()
    q = svc.generate_trivia_question(topic=DAILY_GENERAL_TOPIC, level="MEDIUM")
    assert q["topic"] == DAILY_GENERAL_TOPIC
    assert q["correct"] in ("A", "B", "C", "D")


def test_publish_daily_not_yet_before_window():
    trivia = MagicMock()
    job = MagicMock()
    matches = MagicMock()
    matches.list_matches.return_value = []
    svc = TriviaService(trivia_dao=trivia, job_ctrl_dao=job, match_dao=matches)
    with patch(
        "src.services.trivia_service.should_publish_daily_trivia",
        return_value=False,
    ):
        r = svc.publish_daily_general()
    assert r["status"] == "NOT_YET"
    trivia.put_broadcast_trivia.assert_not_called()


def test_publish_daily_creates_once():
    trivia = MagicMock()
    job = MagicMock()
    job.is_processed.return_value = False
    trivia.get_daily_general_for_date.return_value = None
    trivia.list_group_member_user_ids.return_value = ["u1", "u2"]
    trivia.put_broadcast_trivia.side_effect = lambda r: {**r, "options": r["options"]}
    matches = MagicMock()
    matches.list_matches.return_value = []

    svc = TriviaService(trivia_dao=trivia, job_ctrl_dao=job, match_dao=matches)
    with patch(
        "src.services.trivia_service.should_publish_daily_trivia",
        return_value=True,
    ):
        r1 = svc.publish_daily_general(created_by="admin-1", force=True)
    assert r1["status"] == "CREATED"
    assert r1["topic"] == DAILY_GENERAL_TOPIC
    trivia.put_broadcast_trivia.assert_called_once()
    call = trivia.put_broadcast_trivia.call_args[0][0]
    assert call["type"] == "DAILY_GENERAL"
    assert call["topic"] == DAILY_GENERAL_TOPIC
    job.mark_processed.assert_called_once()
    assert job.mark_processed.call_args[0][0] == DAILY_TRIVIA_JOB


def test_publish_daily_skips_if_job_ctrl():
    trivia = MagicMock()
    job = MagicMock()
    job.is_processed.return_value = True
    trivia.get_daily_general_for_date.return_value = {"trivia_id": "abc123"}

    matches = MagicMock()
    matches.list_matches.return_value = []
    svc = TriviaService(trivia_dao=trivia, job_ctrl_dao=job, match_dao=matches)
    with patch("src.services.trivia_service.should_publish_daily_trivia", return_value=True):
        r = svc.publish_daily_general()
    assert r["status"] == "SKIPPED"
    assert r["trivia_id"] == "abc123"
    trivia.put_broadcast_trivia.assert_not_called()


def test_build_daily_delivery_prompts_once():
    trivia = MagicMock()
    users = MagicMock()
    today_trivia = {
        "trivia_id": "daily01",
        "question": "¿Quién ganó?",
        "options": {"A": "x", "B": "y", "C": "z", "D": "w"},
        "level": "MEDIUM",
        "closes_at": "2099-01-01T00:00:00Z",
    }
    trivia.get_daily_general_for_date.return_value = today_trivia
    trivia.has_answered.return_value = False

    svc = TriviaService(trivia_dao=trivia, user_dao=users)
    profile = {"notifications_enabled": True}
    d = svc.build_daily_delivery_for_user("u1", profile)
    assert d is not None
    assert "Historias del Mundial" in d["message"]
    users.update_profile.assert_called_once_with("u1", daily_trivia_prompted_id="daily01")

    profile["daily_trivia_prompted_id"] = "daily01"
    assert svc.build_daily_delivery_for_user("u1", profile) is None
