"""tests/unit/test_invitations/test_invitation_service.py — SPEC-020"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.dao.dynamo.invitation_dao import generate_invite_id
from src.services.invitation_service import InvitationService
from src.utils.telegram_start import parse_start_payload


def test_parse_start_payload():
    assert parse_start_payload("/start a3F9bC1d") == "a3F9bC1d"
    assert parse_start_payload("/start") is None
    assert parse_start_payload("hola") is None


def test_generate_invite_id_unique():
    dao = MagicMock()
    dao.exists.side_effect = [True, False]
    invite = generate_invite_id(dao)
    assert len(invite) == 8
    assert dao.exists.call_count == 2


def test_create_invitation_admin_global():
    inv_dao = MagicMock()
    inv_dao.exists.return_value = False
    user_dao = MagicMock()
    user_dao.get_profile.return_value = {
        "user_id": "admin-1",
        "alias": "GolazoAdmin",
        "is_admin": True,
        "status": "ACTIVE",
    }
    group_dao = MagicMock()
    group_dao.get_group.return_value = {
        "group_id": "GLOBAL",
        "name": "Mundial 2026 — General",
        "max_members": None,
    }

    svc = InvitationService(
        invitation_dao=inv_dao,
        user_dao=user_dao,
        group_dao=group_dao,
    )
    inv_dao.create.return_value = {
        "invite_id": "abc12345",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "group_name": "Mundial 2026 — General",
    }

    with patch("src.services.invitation_service.generate_invite_id", return_value="abc12345"):
        result = svc.create_invitation("admin-1", max_uses=3)

    assert result["invite_id"] == "abc12345"
    assert "t.me/" in result["link"]
    inv_dao.create.assert_called_once()
    call_kw = inv_dao.create.call_args.kwargs
    assert call_kw["group_id"] == "GLOBAL"
    assert call_kw["max_uses"] == 3


def test_create_invitation_rejects_over_slots():
    user_dao = MagicMock()
    user_dao.get_profile.return_value = {
        "user_id": "owner-1",
        "alias": "Owner",
        "is_admin": False,
        "status": "ACTIVE",
    }
    group_dao = MagicMock()
    group_dao.get_owner_group_id.return_value = "grp-1"
    group_dao.get_group.return_value = {
        "group_id": "grp-1",
        "name": "Los Pibes",
        "owner_id": "owner-1",
        "max_members": 5,
    }
    group_dao.count_members.return_value = 4

    svc = InvitationService(
        invitation_dao=MagicMock(),
        user_dao=user_dao,
        group_dao=group_dao,
    )

    with pytest.raises(ValueError, match="Solo tenés 1 slot"):
        svc.create_invitation("owner-1", max_uses=3)


def test_validate_and_use_adds_global():
    now = datetime.now(timezone.utc)
    invite = {
        "invite_id": "inv12345",
        "group_id": "grp-1",
        "group_name": "Los Pibes",
        "status": "ACTIVE",
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "max_uses": 1,
    }
    inv_dao = MagicMock()
    inv_dao.get.return_value = invite
    inv_dao.increment_uses.return_value = {**invite, "uses_count": 1, "status": "EXHAUSTED"}

    group_dao = MagicMock()
    svc = InvitationService(invitation_dao=inv_dao, group_dao=group_dao)

    result = svc.validate_and_use("inv12345", "user-new")

    assert result["group_name"] == "Los Pibes"
    group_dao.add_member.assert_any_call("grp-1", "user-new")
    group_dao.add_member.assert_any_call("GLOBAL", "user-new")
    inv_dao.record_use.assert_called_once()


def test_revoke_invitation_by_creator():
    inv_dao = MagicMock()
    inv_dao.get.return_value = {"invite_id": "abc", "created_by": "owner-1"}
    inv_dao.revoke.return_value = True
    user_dao = MagicMock()
    user_dao.get_profile.return_value = {
        "user_id": "owner-1",
        "is_admin": False,
        "status": "ACTIVE",
    }

    svc = InvitationService(
        invitation_dao=inv_dao,
        user_dao=user_dao,
        group_dao=MagicMock(),
    )
    assert svc.revoke_invitation("abc", "owner-1") is True
    inv_dao.revoke.assert_called_once_with("abc")


def test_notify_exhausted_sends_sqs():
    inv_dao = MagicMock()
    group_dao = MagicMock()
    svc = InvitationService(invitation_dao=inv_dao, group_dao=group_dao)

    with patch.dict("os.environ", {"INVITATION_NOTIFY_QUEUE_URL": "https://sqs.example/q"}):
        with patch("boto3.client") as mock_boto:
            svc._notify_inviter_exhausted({"invite_id": "x", "created_by": "u1", "group_name": "G"})
            mock_boto.return_value.send_message.assert_called_once()
