"""Lógica de negocio — invitaciones SPEC-020."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
from src.dao.dynamo.invitation_dao import InvitationDAO, generate_invite_id
from src.dao.dynamo.user_dao import UserDAO
from src.services.auth_service import AuthService, USER_STATUS_ACTIVE

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_expires(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y %H:%M UTC")
    except ValueError:
        return iso


class InvitationService:
    def __init__(
        self,
        invitation_dao: InvitationDAO | None = None,
        user_dao: UserDAO | None = None,
        group_dao: GroupDAO | None = None,
        auth: AuthService | None = None,
    ):
        self._invites = invitation_dao or InvitationDAO()
        self._users = user_dao or UserDAO()
        self._groups = group_dao or GroupDAO()
        self._auth = auth or AuthService(self._users, self._groups)
        self._bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "scalonia_bot").lstrip("@")

    def _invite_link(self, invite_id: str) -> str:
        return f"https://t.me/{self._bot_username}?start={invite_id}"

    def create_invitation(
        self,
        creator_user_id: str,
        max_uses: int = 1,
        *,
        group_id: str | None = None,
    ) -> dict:
        if max_uses < 1:
            raise ValueError("max_uses debe ser al menos 1")

        creator = self._users.get_profile(creator_user_id)
        if not creator or creator.get("status") != USER_STATUS_ACTIVE:
            raise ValueError("Usuario no encontrado o inactivo")

        if self._auth.is_admin_global(creator_user_id) and not group_id:
            target_group_id = GLOBAL_GROUP_ID
        else:
            target_group_id = group_id or self._groups.get_owner_group_id(creator_user_id)
            if not target_group_id:
                raise ValueError("Creá un grupo antes de invitar (o pasá group_id).")

        allowed, reason = self._auth.check_can_invite(creator_user_id, target_group_id)
        if not allowed:
            if reason == "LIMIT_REACHED_INVITES":
                raise ValueError("El grupo ya alcanzó el cupo de miembros")
            if reason == "NOT_GROUP_OWNER":
                raise ValueError("Solo el dueño del grupo puede crear invitaciones")
            raise ValueError(f"No podés invitar: {reason}")

        slots = self._auth.slots_available(target_group_id)
        if slots is not None and max_uses > slots:
            raise ValueError(
                f"Solo tenés {slots} slot{'s' if slots != 1 else ''} disponible{'s' if slots != 1 else ''} en tu grupo"
            )

        group = self._groups.get_group(target_group_id)
        if not group:
            raise ValueError("Grupo no encontrado")

        invite_id = generate_invite_id(self._invites)
        inv = self._invites.create(
            invite_id=invite_id,
            group_id=target_group_id,
            created_by=creator_user_id,
            max_uses=max_uses,
            group_name=group.get("name", target_group_id),
            inviter_alias=creator.get("alias", "Admin"),
        )

        return {
            "invite_id": invite_id,
            "link": self._invite_link(invite_id),
            "max_uses": max_uses,
            "uses_count": 0,
            "expires_at": inv["expires_at"],
            "expires_at_display": _format_expires(inv["expires_at"]),
            "group_id": target_group_id,
            "group_name": inv["group_name"],
            "message": self._format_created_message(inv, max_uses),
        }

    def _format_created_message(self, inv: dict, max_uses: int) -> str:
        return (
            "✅ Invitación creada\n\n"
            f"Código: {inv['invite_id']}\n"
            f"Slots disponibles: {max_uses} de {max_uses}\n"
            f"Expira: { _format_expires(inv['expires_at']) } (24hs)\n"
            f"Grupo destino: \"{inv['group_name']}\"\n\n"
            f"📎 Link para compartir:\n{self._invite_link(inv['invite_id'])}\n\n"
            f"Cuando alguien lo use, te aviso. Podés cancelarla con /revocar {inv['invite_id']}"
        )

    def _load_active_invite(self, invite_id: str) -> dict:
        invite = self._invites.get(invite_id)
        if not invite:
            raise ValueError("INVITATION_INVALID")
        if invite.get("status") != "ACTIVE":
            raise ValueError("INVITATION_NOT_ACTIVE")
        if invite.get("expires_at", "") < _now_iso():
            self._invites.update_status(invite_id, "EXPIRED")
            raise ValueError("INVITATION_EXPIRED")
        return invite

    def _join_user_to_invite_group(
        self, user_id: str, invite_id: str, invite: dict, *, consume_slot: bool
    ) -> dict:
        group_id = invite["group_id"]
        group_name = invite.get("group_name", group_id)
        already_in_target = self._groups.is_member(group_id, user_id)

        if already_in_target:
            return {
                "group_id": group_id,
                "group_name": group_name,
                "joined_new": False,
            }

        slots = self._auth.slots_available(group_id)
        if slots is not None and slots <= 0:
            raise ValueError("LIMIT_REACHED_INVITES")

        updated = None
        if consume_slot:
            try:
                updated = self._invites.increment_uses(invite_id)
            except ValueError as exc:
                if str(exc) == "INVITATION_NOT_USABLE":
                    raise ValueError("INVITATION_NOT_USABLE") from exc
                raise
            self._invites.record_use(invite_id, user_id, group_joined=group_id)

        self._groups.add_member(group_id, user_id)
        if group_id != GLOBAL_GROUP_ID:
            self._groups.add_member(GLOBAL_GROUP_ID, user_id)

        if updated and updated.get("status") == "EXHAUSTED":
            self._notify_inviter_exhausted(updated)

        return {
            "group_id": group_id,
            "group_name": group_name,
            "joined_new": True,
        }

    def accept_invitation_for_existing_user(
        self, user_id: str, invite_id: str, *, consume_slot: bool = True
    ) -> dict:
        """Usuario ACTIVE: unirse al grupo de la invitación sin crear USER# nuevo."""
        creator = self._users.get_profile(user_id)
        if not creator or creator.get("status") != USER_STATUS_ACTIVE:
            raise ValueError("Usuario no encontrado o inactivo")
        invite = self._load_active_invite(invite_id)
        return self._join_user_to_invite_group(
            user_id, invite_id, invite, consume_slot=consume_slot
        )

    def validate_and_use(self, invite_id: str, new_user_id: str) -> dict:
        invite = self._load_active_invite(invite_id)
        result = self._join_user_to_invite_group(
            new_user_id, invite_id, invite, consume_slot=True
        )
        return {
            "group_id": result["group_id"],
            "group_name": result["group_name"],
            "is_new_group_member": result["joined_new"],
            "is_global_member": True,
        }

    def revoke_invitation(self, invite_id: str, revoker_user_id: str) -> bool:
        invite = self._invites.get(invite_id)
        if not invite:
            raise ValueError("Invitación no encontrada")
        if invite["created_by"] != revoker_user_id and not self._auth.is_admin_global(
            revoker_user_id
        ):
            raise ValueError("No tenés permiso para revocar esta invitación")
        if not self._invites.revoke(invite_id):
            raise ValueError("La invitación no está activa o ya fue usada/revocada")
        return True

    def list_my_invitations(
        self, user_id: str, status_filter: str | None = None
    ) -> list[dict]:
        rows = self._invites.list_by_creator(user_id, status_filter=status_filter)
        return [
            {
                "invite_id": r["invite_id"],
                "status": r.get("status"),
                "max_uses": int(r.get("max_uses", 0)),
                "uses_count": int(r.get("uses_count", 0)),
                "expires_at": r.get("expires_at"),
                "group_name": r.get("group_name"),
                "link": self._invite_link(r["invite_id"]),
            }
            for r in rows
        ]

    def get_invitation_uses(self, invite_id: str, requester_user_id: str) -> list[dict]:
        invite = self._invites.get(invite_id)
        if not invite:
            raise ValueError("Invitación no encontrada")
        if invite["created_by"] != requester_user_id and not self._auth.is_admin_global(
            requester_user_id
        ):
            raise ValueError("No tenés permiso para ver los usos")
        return self._invites.list_uses(invite_id)

    def _notify_inviter_exhausted(self, invite: dict) -> None:
        """Fire-and-forget: SQS opcional o log."""
        queue_url = os.environ.get("INVITATION_NOTIFY_QUEUE_URL", "").strip()
        payload = {
            "type": "INVITATION_EXHAUSTED",
            "invite_id": invite.get("invite_id"),
            "created_by": invite.get("created_by"),
            "group_name": invite.get("group_name"),
        }
        if queue_url:
            try:
                boto3.client("sqs").send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(payload),
                )
            except Exception:
                logger.exception("SQS notify failed invite_id=%s", invite.get("invite_id"))
        else:
            logger.info("Invitation exhausted: %s", payload)
