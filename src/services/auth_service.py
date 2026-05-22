"""Verificación de permisos — SPEC-018 / SPEC-020."""
from __future__ import annotations

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
from src.dao.dynamo.user_dao import UserDAO

USER_STATUS_ACTIVE = "ACTIVE"

# Mensaje genérico: no revelar si falta registro, invitación o baneo.
INACTIVE_USER_MESSAGE = (
    "Todavía no estás registrado en el Prode Mundial 2026. "
    "Tocá el link de invitación que te compartieron (termina en ?start=...) "
    "y después enviá /start ahí antes de escribirle al bot."
)

INVITATION_REQUIRED_MESSAGE = (
    "Para unirte al Prode Mundial 2026 necesitás una invitación. "
    "Pedile a quien te invitó el link de Telegram con el código de invitación."
)


class AuthService:
    def __init__(
        self,
        user_dao: UserDAO | None = None,
        group_dao: GroupDAO | None = None,
    ):
        self._users = user_dao or UserDAO()
        self._groups = group_dao or GroupDAO()

    def resolve_telegram_access(
        self, platform_id_hash: str, *, platform: str = "TELEGRAM"
    ) -> tuple[str | None, str | None]:
        """
        Valida usuario antes de invocar el agente (ahorro de tokens LLM).

        Retorna (user_id, None) si puede usar el bot.
        Retorna (None, mensaje) si debe bloquearse sin llamar a Bedrock.
        """
        profile = self._users.get_by_platform_hash(platform, platform_id_hash)
        if not profile:
            return None, INACTIVE_USER_MESSAGE
        if profile.get("status") != USER_STATUS_ACTIVE:
            return None, INACTIVE_USER_MESSAGE
        return profile["user_id"], None

    def require_active_user_id(self, user_id: str) -> tuple[bool, str]:
        """Para @tools: rechaza unregistered/anonymous o perfil no ACTIVE."""
        if not user_id or user_id in ("unregistered", "anonymous"):
            return False, INACTIVE_USER_MESSAGE
        profile = self._users.get_profile(user_id)
        if not profile or profile.get("status") != USER_STATUS_ACTIVE:
            return False, INACTIVE_USER_MESSAGE
        return True, ""

    def is_admin_global(self, user_id: str) -> bool:
        profile = self._users.get_profile(user_id)
        return bool(profile and profile.get("is_admin"))

    def is_group_owner(self, user_id: str, group_id: str) -> bool:
        group = self._groups.get_group(group_id)
        return bool(group and group.get("owner_id") == user_id)

    def bypasses_member_cap(self, user_id: str) -> bool:
        """Admin global: puede invitar/agregar sin límite de cupos del grupo."""
        return self.is_admin_global(user_id)

    def check_can_invite(self, user_id: str, group_id: str) -> tuple[bool, str]:
        user = self._users.get_profile(user_id)
        if not user:
            return False, "USER_NOT_FOUND"
        if user.get("is_admin"):
            return True, "ok"
        group = self._groups.get_group(group_id)
        if not group:
            return False, "GROUP_NOT_FOUND"
        if group.get("owner_id") != user_id:
            return False, "NOT_GROUP_OWNER"
        max_members = group.get("max_members")
        if max_members is not None:
            count = self._groups.count_members(group_id)
            if count >= int(max_members):
                return False, "LIMIT_REACHED_INVITES"
        return True, "ok"

    def slots_available(self, group_id: str, *, actor_user_id: str | None = None) -> int | None:
        """Slots libres para owners; None = sin tope (GLOBAL o admin actuando)."""
        if actor_user_id and self.bypasses_member_cap(actor_user_id):
            return None
        group = self._groups.get_group(group_id)
        if not group:
            return None
        if group_id == GLOBAL_GROUP_ID or group.get("is_global"):
            return None
        max_members = group.get("max_members")
        if max_members is None:
            return None
        return max(0, int(max_members) - self._groups.count_members(group_id))
