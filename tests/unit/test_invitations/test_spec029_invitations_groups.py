"""SPEC-2026-029 — invitaciones avanzadas + grupos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.services.invitation_service import InvitationService

pytestmark = pytest.mark.spec029


def test_admin_invitar_without_group_id_targets_global():
    """AC-04 / US-29-01: admin sin group_id → GLOBAL (comportamiento actual preservado)."""
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
        result = svc.create_invitation("admin-1", max_uses=2)

    assert result["group_id"] == "GLOBAL"
    assert inv_dao.create.call_args.kwargs["group_id"] == "GLOBAL"


def test_existing_user_accept_invite_joins_group():
    """AC-10: usuario ACTIVE no miembro → add_member + mensaje éxito."""
    inv_dao = MagicMock()
    inv_dao.get.return_value = {
        "invite_id": "inv12345",
        "status": "ACTIVE",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "group_id": "grp-1",
        "group_name": "Los Pibes",
        "max_uses": 5,
        "uses_count": 0,
    }
    inv_dao.increment_uses.return_value = {"status": "ACTIVE", "uses_count": 1}
    user_dao = MagicMock()
    user_dao.get_profile.return_value = {"user_id": "u-existing", "status": "ACTIVE"}
    group_dao = MagicMock()
    group_dao.get_group.return_value = {"group_id": "grp-1", "name": "Los Pibes"}
    group_dao.is_member.return_value = False
    group_dao.get_group.return_value = {"group_id": "grp-1", "max_members": 10}
    group_dao.count_members.return_value = 1

    svc = InvitationService(
        invitation_dao=inv_dao,
        user_dao=user_dao,
        group_dao=group_dao,
    )
    result = svc.accept_invitation_for_existing_user("u-existing", "inv12345")

    assert result["joined_new"] is True
    assert result["group_name"] == "Los Pibes"
    group_dao.add_member.assert_any_call("grp-1", "u-existing")
    group_dao.add_member.assert_any_call("GLOBAL", "u-existing")


def test_existing_user_already_member_idempotent():
    """AC-11: ya miembro → no consume cupo invitación."""
    inv_dao = MagicMock()
    inv_dao.get.return_value = {
        "invite_id": "inv12345",
        "status": "ACTIVE",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "group_id": "grp-1",
        "group_name": "Los Pibes",
    }
    user_dao = MagicMock()
    user_dao.get_profile.return_value = {"user_id": "u-existing", "status": "ACTIVE"}
    group_dao = MagicMock()
    group_dao.is_member.return_value = True

    svc = InvitationService(
        invitation_dao=inv_dao,
        user_dao=user_dao,
        group_dao=group_dao,
    )
    result = svc.accept_invitation_for_existing_user("u-existing", "inv12345")

    assert result["joined_new"] is False
    inv_dao.increment_uses.assert_not_called()


def test_start_handler_existing_with_invite_calls_accept():
    """AC-10: /start invite con perfil existente → accept_invitation_for_existing_user."""
    from infrastructure.lambdas.telegram_webhook.start_handler import handle_start_command

    with (
        patch("infrastructure.lambdas.telegram_webhook.start_handler.UserDAO") as mock_users,
        patch("infrastructure.lambdas.telegram_webhook.start_handler.GroupDAO"),
        patch("infrastructure.lambdas.telegram_webhook.start_handler.InvitationDAO"),
        patch(
            "infrastructure.lambdas.telegram_webhook.start_handler.InvitationService"
        ) as mock_inv_svc,
    ):
        mock_users.return_value.get_by_platform_hash.return_value = {
            "user_id": "u1",
            "status": "ACTIVE",
            "alias": "vic",
            "onboarding_stage": "M3_COMPLETE",
        }
        mock_inv_svc.return_value.accept_invitation_for_existing_user.return_value = {
            "group_name": "Los Pibes",
            "joined_new": True,
        }

        msg, _ = handle_start_command(12345, "/start inv12345")

        mock_inv_svc.return_value.accept_invitation_for_existing_user.assert_called_once_with(
            "u1", "inv12345"
        )
        assert "Los Pibes" in msg


def test_add_member_by_alias_owner():
    """AC-20: owner agrega usuario existente por alias."""
    from src.services.group_service import GroupService

    user_dao = MagicMock()
    user_dao.resolve_alias.return_value = {
        "user_id": "target-1",
        "alias": "vic",
        "status": "ACTIVE",
    }
    user_dao.get_profile.return_value = {}
    group_dao = MagicMock()
    group_dao.get_owner_group_id.return_value = "grp-1"
    group_dao.get_group.return_value = {"group_id": "grp-1", "name": "Los Pibes", "is_global": False}
    group_dao.is_member.return_value = False

    svc = GroupService(user_dao=user_dao, group_dao=group_dao)
    with patch.object(svc, "_auth") as mock_auth:
        mock_auth.is_admin_global.return_value = False
        mock_auth.slots_available.return_value = 2
        mock_auth.is_group_owner = MagicMock(return_value=True)
        svc._can_manage = MagicMock(return_value=True)
        ok, message = svc.add_member_by_alias("owner-1", "vic", group_id="grp-1")

    assert ok is True
    assert "vic" in message.lower()
    group_dao.add_member.assert_any_call("grp-1", "target-1")
    group_dao.add_member.assert_any_call("GLOBAL", "target-1")


def test_admin_create_group_for_alias():
    """AC-30: admin crea grupo con owner_id del alias objetivo."""
    from src.services.group_service import GroupService

    user_dao = MagicMock()
    user_dao.resolve_alias.return_value = {
        "user_id": "vic-id",
        "alias": "vic",
        "status": "ACTIVE",
        "is_admin": False,
    }
    group_dao = MagicMock()
    group_dao.get_owner_group_id.return_value = None
    group_dao.create_group.return_value = {
        "group_id": "new-grp",
        "name": "Futbol Total",
        "invite_code": "ABC123",
    }

    svc = GroupService(user_dao=user_dao, group_dao=group_dao)
    with (
        patch.object(svc, "_auth") as mock_auth,
        patch("src.services.invitation_service.InvitationService") as mock_inv,
    ):
        mock_auth.is_admin_global.return_value = True
        mock_inv.return_value.create_invitation.return_value = {
            "link": "https://t.me/scalonia_bot?start=abc",
            "invite_id": "abc",
        }
        msg = svc.create_group_for_user(
            "admin-1",
            target_alias="vic",
            name="Futbol Total",
            avatar="⚽",
        )

    assert "Futbol Total" in msg
    group_dao.create_group.assert_called_once()
    assert group_dao.create_group.call_args.kwargs["owner_id"] == "vic-id"


def test_create_group_for_user_rejects_second_group_free():
    """AC-34: target con grupo propio → rechazo (MVP)."""
    from src.services.group_service import GroupService

    user_dao = MagicMock()
    user_dao.resolve_alias.return_value = {"user_id": "vic-id", "alias": "vic", "status": "ACTIVE"}
    group_dao = MagicMock()
    group_dao.get_owner_group_id.return_value = "existing-grp"
    group_dao.get_group.return_value = {"name": "Grupo Viejo"}

    svc = GroupService(user_dao=user_dao, group_dao=group_dao)
    with patch.object(svc, "_auth") as mock_auth:
        mock_auth.is_admin_global.return_value = True
        with pytest.raises(ValueError, match="grupo propio"):
            svc.create_group_for_user(
                "admin-1",
                target_alias="vic",
                name="Futbol Total",
                avatar="⚽",
            )
