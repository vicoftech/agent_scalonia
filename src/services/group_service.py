"""Gestión de grupos — SPEC-026."""
from __future__ import annotations

import os
import re

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
from src.dao.dynamo.limit_request_dao import LimitRequestDAO
from src.dao.dynamo.user_dao import UserDAO
from src.services.auth_service import AuthService

_GROUP_NAME_RE = re.compile(r"^[\w\s\-áéíóúÁÉÍÓÚñÑ]{2,50}$")
_FREE_MAX_OWNED_GROUPS = 1


class GroupService:
    def __init__(
        self,
        group_dao: GroupDAO | None = None,
        user_dao: UserDAO | None = None,
        auth: AuthService | None = None,
        limit_dao: LimitRequestDAO | None = None,
    ):
        self._groups = group_dao or GroupDAO()
        self._users = user_dao or UserDAO()
        self._auth = auth or AuthService(self._users, self._groups)
        self._limits = limit_dao or LimitRequestDAO()

    def _bot_username(self) -> str:
        return (os.environ.get("TELEGRAM_BOT_USERNAME") or "scalonia_bot").lstrip("@")

    def _invite_link(self, code: str) -> str:
        return f"https://t.me/{self._bot_username()}?start={code.lower()}"

    def validate_group_name(self, name: str) -> tuple[bool, str]:
        n = (name or "").strip()
        if len(n) < 2 or len(n) > 50:
            return False, "El nombre debe tener entre 2 y 50 caracteres."
        if not _GROUP_NAME_RE.match(n):
            return False, "Usá letras, números, espacios o guiones solamente."
        return True, n

    def can_create_group(self, user_id: str) -> tuple[bool, str | None]:
        profile = self._users.get_profile(user_id) or {}
        if profile.get("is_admin"):
            return True, None
        owned = self._groups.get_owner_group_id(user_id)
        if owned:
            group = self._groups.get_group(owned) or {}
            return False, group.get("name", "tu grupo")
        return True, None

    def format_groups_list(self, user_id: str) -> str:
        group_ids = self._groups.list_group_ids_for_user(user_id)
        if not group_ids:
            return (
                "👥 Mis grupos\n\n"
                "Todavía no estás en ningún grupo.\n"
                "Usá /crear-grupo para armar el tuyo o pedí una invitación."
            )
        lines = ["👥 Mis grupos", ""]
        profile = self._users.get_profile(user_id) or {}
        is_admin = bool(profile.get("is_admin"))

        for gid in sorted(group_ids, key=lambda g: (g != GLOBAL_GROUP_ID, g)):
            g = self._groups.get_group(gid)
            if not g or g.get("status") == "DELETED":
                continue
            name = g.get("name", gid)
            avatar = g.get("avatar", "⚽")
            count = self._groups.count_members(gid)
            if g.get("is_global"):
                lines.append(f"{avatar} {name}          GLOBAL")
                lines.append(f"   {count} miembros")
            elif g.get("owner_id") == user_id:
                code = g.get("invite_code") or "—"
                status = g.get("status", "ACTIVE")
                badge = "owner"
                if status == "SUSPENDED":
                    badge = "suspendido"
                lines.append(f"{avatar} {name}             {badge}")
                lines.append(f"   {count} miembros · código: {code}")
                if status == "ACTIVE":
                    lines.append("   /editar-grupo para administrar")
            else:
                lines.append(f"{avatar} {name}             miembro")
                lines.append(f"   {count} miembros")
            lines.append("")

        if is_admin:
            lines.append("Admin: /admin-grupos")
        lines.append("Comandos: /crear-grupo · /invitar")
        return "\n".join(lines).strip()

    def start_create_group(self, user_id: str) -> tuple[str, dict | None]:
        ok, existing_name = self.can_create_group(user_id)
        if not ok:
            from src.services.group_telegram_ui import limit_reached_keyboard

            return (
                f'Ya tenés un grupo propio ("{existing_name}").\n'
                "En el plan Free podés tener 1 grupo.\n"
                "Para crear más:",
                limit_reached_keyboard(),
            )
        self._clear_create_state(user_id)
        self._users.update_profile(user_id, group_create_step="awaiting_name")
        return "¡Vamos a crear tu grupo! 🎉\n\n¿Cómo se va a llamar?", None

    def submit_create_name(self, user_id: str, name: str) -> tuple[str, dict | None]:
        valid, result = self.validate_group_name(name)
        if not valid:
            return result, None
        self._users.update_profile(
            user_id,
            group_create_step="awaiting_avatar",
            group_draft_name=result,
        )
        from src.services.group_telegram_ui import avatar_picker_keyboard

        return (
            "Elegí un avatar para el grupo:\n(/cancel para salir)",
            avatar_picker_keyboard(),
        )

    def finish_create_group(self, user_id: str, avatar: str) -> str:
        profile = self._users.get_profile(user_id) or {}
        draft_name = (profile.get("group_draft_name") or "").strip()
        if not draft_name:
            self._clear_create_state(user_id)
            return "No encontré el nombre del grupo. Empezá de nuevo con /crear-grupo."

        profile = self._users.get_profile(user_id) or {}
        max_members = 5
        if profile.get("is_admin"):
            max_members = 50

        group = self._groups.create_group(
            owner_id=user_id,
            name=draft_name,
            avatar=avatar,
            max_members=max_members,
        )
        self._groups.add_member(GLOBAL_GROUP_ID, user_id)
        self._users.update_profile(
            user_id,
            groups_owned=1,
            group_create_step=None,
            group_draft_name=None,
        )

        from src.services.invitation_service import InvitationService

        inv = InvitationService().create_invitation(
            user_id, max_uses=5, group_id=group["group_id"]
        )
        code = group.get("invite_code", "")
        link = inv.get("link") or inv.get("invite_url") or self._invite_link(inv["invite_id"])

        return (
            f'✅ Grupo "{draft_name}" creado\n\n'
            "┌─────────────────────────────┐\n"
            "│  Tu código de invitación:   │\n"
            f"│  {code:<27}│\n"
            "│  Compartilo con hasta 5      │\n"
            "│  amigos. El link directo:   │\n"
            f"│  {link} │\n"
            "└─────────────────────────────┘\n\n"
            "Usá /grupos para ver tus grupos."
        )

    def request_admin_new_group(self, user_id: str) -> str:
        self._limits.create(requester_user_id=user_id, request_type="NEW_GROUP")
        self._clear_create_state(user_id)
        return (
            "Tu pedido fue enviado al admin.\n"
            "Te avisamos cuando tengamos una respuesta.\n"
            "Estado: Pendiente ⏳"
        )

    def _clear_create_state(self, user_id: str) -> None:
        self._users.update_profile(
            user_id,
            group_create_step=None,
            group_draft_name=None,
            group_edit_pending=None,
        )

    def get_owned_group_id(self, user_id: str) -> str | None:
        if self._auth.is_admin_global(user_id):
            return self._groups.get_owner_group_id(user_id)
        return self._groups.get_owner_group_id(user_id)

    def format_edit_menu(self, user_id: str, group_id: str | None = None) -> tuple[str, dict]:
        gid = group_id or self.get_owned_group_id(user_id)
        if not gid:
            return "No tenés un grupo propio. Creá uno con /crear-grupo.", {}
        g = self._groups.get_group(gid)
        if not g:
            return "Grupo no encontrado.", {}
        if g.get("is_global"):
            return "El grupo GLOBAL no se puede editar desde acá.", {}
        if not self._auth.is_admin_global(user_id) and g.get("owner_id") != user_id:
            return "Solo el dueño del grupo puede editarlo.", {}
        if g.get("status") == "SUSPENDED":
            return "Este grupo está suspendido.", {}
        from src.services.group_telegram_ui import group_edit_menu_keyboard

        name = g.get("name", gid)
        return f'Editando "{name}"', group_edit_menu_keyboard(gid)

    def format_members_list(self, user_id: str, group_id: str) -> str:
        g = self._groups.get_group(group_id)
        if not g:
            return "Grupo no encontrado."
        if not self._can_manage(user_id, group_id):
            return "No tenés permiso para ver miembros de este grupo."

        members = self._groups.list_member_user_ids(group_id)
        max_m = g.get("max_members")
        count = len(members)
        cap = f"{count}/{max_m}" if max_m else str(count)
        lines = [f"👥 {g.get('name')} — {cap} miembros", ""]
        owner_id = g.get("owner_id")
        for uid in members:
            prof = self._users.get_profile(uid) or {}
            alias = prof.get("alias", uid[:8])
            if uid == user_id and uid == owner_id:
                lines.append(f"⚽ {alias} (vos — owner)")
            elif uid == owner_id:
                lines.append(f"⚽ {alias} (owner)")
            elif uid == user_id:
                lines.append(f"👤 {alias} (vos)")
            else:
                lines.append(f"👤 {alias}            /miembros → eliminar vía botón en Telegram")
        slots = self._auth.slots_available(group_id)
        if slots is not None and slots > 0:
            lines.append(f"\nPodés agregar {slots} miembro{'s' if slots != 1 else ''} más.")
            lines.append("Usá /invitar para generar link.")
        return "\n".join(lines)

    def _can_manage(self, user_id: str, group_id: str) -> bool:
        if self._auth.is_admin_global(user_id):
            return True
        return self._auth.is_group_owner(user_id, group_id)

    def start_rename(self, user_id: str, group_id: str) -> str:
        if not self._can_manage(user_id, group_id):
            return "Sin permiso."
        g = self._groups.get_group(group_id)
        if g and g.get("is_global"):
            return "El grupo GLOBAL no puede renombrarse."
        self._users.update_profile(
            user_id,
            group_edit_pending={"group_id": group_id, "action": "rename"},
        )
        return f'¿Nuevo nombre para el grupo?\n(Nombre actual: {g.get("name") if g else "?"})'

    def apply_rename(self, user_id: str, new_name: str) -> str:
        profile = self._users.get_profile(user_id) or {}
        pending = profile.get("group_edit_pending") or {}
        if pending.get("action") != "rename":
            return ""
        gid = pending.get("group_id")
        valid, result = self.validate_group_name(new_name)
        if not valid:
            return result
        self._groups.update_group(gid, name=result)
        self._users.update_profile(user_id, group_edit_pending=None)
        return f'✅ Nombre actualizado a "{result}"'

    def apply_avatar(self, user_id: str, group_id: str, avatar: str) -> str:
        if not self._can_manage(user_id, group_id):
            return "Sin permiso."
        g = self._groups.get_group(group_id)
        if g and g.get("is_global"):
            return "El grupo GLOBAL no puede cambiar avatar."
        self._groups.update_group(group_id, avatar=avatar)
        return "✅ Avatar actualizado"

    def remove_member(
        self, actor_id: str, group_id: str, member_user_id: str
    ) -> tuple[bool, str]:
        if not self._can_manage(actor_id, group_id):
            return False, "Sin permiso."
        g = self._groups.get_group(group_id)
        if not g or g.get("is_global"):
            return False, "Operación no permitida en este grupo."
        if member_user_id == g.get("owner_id"):
            return False, "No podés eliminar al dueño del grupo."
        if not self._groups.is_member(group_id, member_user_id):
            return False, "Esa persona no es miembro."
        self._groups.remove_member(group_id, member_user_id)
        prof = self._users.get_profile(member_user_id) or {}
        alias = prof.get("alias", "el miembro")
        slots = self._auth.slots_available(group_id)
        extra = ""
        if slots is not None:
            extra = f"\nAhora tenés {self._groups.count_members(group_id)}/{g.get('max_members')} miembros."
            if slots > 0:
                extra += f"\nPodés invitar a {slots} persona{'s' if slots != 1 else ''} más."
        return True, f"✅ {alias} fue eliminado del grupo.{extra}"

    def delete_group(self, user_id: str, group_id: str) -> tuple[bool, str]:
        g = self._groups.get_group(group_id)
        if not g:
            return False, "Grupo no encontrado."
        if g.get("is_global") or group_id == GLOBAL_GROUP_ID:
            return False, "El grupo GLOBAL no puede eliminarse."
        if not self._auth.is_admin_global(user_id) and g.get("owner_id") != user_id:
            return False, "Solo el dueño puede eliminar el grupo."
        self._groups.mark_deleted(group_id)
        self._groups.delete_all_memberships(group_id)
        if g.get("owner_id") == user_id:
            self._users.update_profile(user_id, groups_owned=0)
        return True, f'✅ Grupo "{g.get("name")}" eliminado.'

    def suspend_group(self, admin_id: str, group_id: str) -> tuple[bool, str]:
        if not self._auth.is_admin_global(admin_id):
            return False, "Solo admin."
        g = self._groups.get_group(group_id)
        if not g or g.get("is_global"):
            return False, "El grupo GLOBAL no puede suspenderse."
        self._groups.mark_suspended(group_id, suspended_by=admin_id)
        return True, f'✅ Grupo "{g.get("name")}" suspendido.'

    def format_admin_groups_list(self) -> str:
        groups = self._groups.list_active_groups(limit=20)
        lines = [f"📋 Todos los grupos ({len(groups)} en esta página)", ""]
        for g in sorted(groups, key=lambda x: (not x.get("is_global"), x.get("name", ""))):
            gid = g.get("group_id", "?")
            name = g.get("name", gid)
            avatar = g.get("avatar", "⚽")
            count = self._groups.count_members(gid)
            if g.get("is_global"):
                lines.append(f"{avatar} {name}    {count} miembros  GLOBAL")
            else:
                owner = self._users.get_profile(g.get("owner_id", "")) or {}
                lines.append(
                    f"{avatar} {name}    {count} miembros   "
                    f"owner: {owner.get('alias', '?')}  [⚙️ /admin-grupos]"
                )
        lines.append("\nTocá ⚙️ en Telegram (próximo paso) o usá callbacks del menú admin.")
        return "\n".join(lines)

    def handle_pending_message(self, user_id: str, text: str) -> str | None:
        """Flujo crear-grupo o renombrar si hay estado pendiente."""
        profile = self._users.get_profile(user_id) or {}
        step = profile.get("group_create_step")
        if step == "awaiting_name":
            msg, _ = self.submit_create_name(user_id, text)
            return msg
        pending = profile.get("group_edit_pending") or {}
        if pending.get("action") == "rename":
            return self.apply_rename(user_id, text) or None
        return None

    def handle_pending_with_markup(
        self, user_id: str, text: str
    ) -> tuple[str, dict | None] | None:
        """Respuesta solo si el mensaje pertenece al flujo pendiente; si no, None."""
        profile = self._users.get_profile(user_id) or {}
        step = profile.get("group_create_step")
        pending = profile.get("group_edit_pending")
        low = text.strip().lower()

        if low in ("/cancel", "/cancelar"):
            if step or pending:
                self._clear_create_state(user_id)
                return "Creación/edición cancelada.", None
            return None

        if step == "awaiting_name":
            return self.submit_create_name(user_id, text)

        if (pending or {}).get("action") == "rename":
            msg = self.apply_rename(user_id, text)
            return (msg, None) if msg else None

        if step == "awaiting_avatar":
            if text.strip().startswith("/"):
                return None
            from src.services.group_telegram_ui import avatar_picker_keyboard

            return (
                "Elegí un avatar con los botones de arriba 👆\n"
                "O enviá /cancel para salir.",
                avatar_picker_keyboard(),
            )

        return None
