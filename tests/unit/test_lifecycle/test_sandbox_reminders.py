"""Sandbox reminders — todos los usuarios."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.match_lifecycle_service import MatchLifecycleService


def test_sandbox_reminder_targets_all_notify_users():
    svc = MatchLifecycleService(
        matches=MagicMock(),
        groups=MagicMock(),
        users=MagicMock(),
        predictions=MagicMock(),
    )
    svc._matches.get_match.return_value = {
        "match_id": "m1",
        "home_team": "MEX",
        "away_team": "RSA",
    }
    svc._pred.format_match_title = lambda m: "MEX vs RSA"
    svc._all_notify_users = MagicMock(return_value={"u1": ["g1"], "u2": ["g1"]})
    svc._users_without_prediction_in_active_group = MagicMock(return_value=[])

    with patch.dict("os.environ", {"NOTIFICATION_QUEUE_URL": ""}):
        out = svc.send_match_reminders("m1", 1, sandbox=True)

    assert out["would_send"] == 2
    svc._users_without_prediction_in_active_group.assert_not_called()
