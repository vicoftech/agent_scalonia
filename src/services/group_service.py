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
        owned = self._groups.list_owned_group_ids(user_id)
        max_allowed = self._max_owned_groups(profile)
        if len(owned) >= max_allowed:
            first = self._groups.get_group(owned[0]) or {}
            return False, first.get("name", "tu grupo")
        return True, None

    def _max_owned_groups(self, profile: dict) -> int:
        extra = int(profile.get("extra_owned_group_slots") or 0)
        return _FREE_MAX_OWNED_GROUPS + extra

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
            from src.services.group_upgrade_telegram_ui import (
                limit_reached_with_upgrade_keyboard,
            )

            return (
                f'Ya tenés el máximo de grupos propios ("{existing_name}").\n'
                f"En el plan Free podés tener {self._max_owned_groups(self._users.get_profile(user_id) or {})}.\n"
                "Para crear más:",
                limit_reached_with_upgrade_keyboard(),
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
        if profile.get("group_create_for_user_id"):
            return self.finish_create_group_for_user(user_id, avatar)

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
        owned_count = len(self._groups.list_owned_group_ids(user_id))
        self._users.update_profile(
            user_id,
            groups_owned=owned_count,
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
            group_create_for_user_id=None,
            group_create_for_user_alias=None,
            group_add_member_alias=None,
            group_add_member_target_id=None,
            group_add_member_group_id=None,
            group_context_group_id=None,
        )

    def _set_group_context(self, user_id: str, group_id: str) -> None:
        self._users.update_profile(user_id, group_context_group_id=group_id)

    def resolve_alias_user(self, alias: str) -> dict:
        """Perfil ACTIVE único por alias (SPEC-029)."""
        target = (alias or "").strip()
        if not target:
            raise ValueError("Indicá un alias.")
        profile = self._users.resolve_alias(target)
        if profile:
            if profile.get("status") != "ACTIVE":
                raise ValueError(f'El usuario "{profile.get("alias", target)}" no está activo.')
            return profile
        suggestions = self._users.find_alias_suggestions(target)
        if suggestions:
            raise ValueError(
                f'No encontré usuario con alias "{target}". '
                f"¿Quisiste decir: {', '.join(suggestions)}?"
            )
        raise ValueError(f'No encontré usuario con alias "{target}".')

    def add_member_by_alias(
        self,
        actor_id: str,
        alias: str,
        *,
        group_id: str | None = None,
    ) -> tuple[bool, str]:
        target = self.resolve_alias_user(alias)
        target_id = target["user_id"]
        target_alias = target.get("alias", alias)

        profile = self._users.get_profile(actor_id) or {}
        gid = group_id or profile.get("group_add_member_group_id")
        if not gid:
            if self._auth.is_admin_global(actor_id):
                raise ValueError(
                    "Elegí el grupo en el menú (desde /agregar-miembro) o "
                    "usá ➕ Agregar por alias en /editar-grupo."
                )
            gid = self.get_owned_group_id(actor_id)
        if not gid:
            return False, "Creá un grupo con /crear-grupo antes de agregar miembros."

        if not self._can_manage(actor_id, gid):
            return False, "Sin permiso para agregar miembros a este grupo."

        g = self._groups.get_group(gid)
        if not g:
            return False, "Grupo no encontrado."
        if g.get("is_global") and not self._auth.is_admin_global(actor_id):
            return False, "Solo el admin puede agregar miembros al torneo General (GLOBAL)."

        if self._groups.is_member(gid, target_id):
            return True, f'ℹ️ {target_alias} ya está en "{g.get("name", gid)}".'

        slots = self._auth.slots_available(gid, actor_user_id=actor_id)
        if slots is not None and slots <= 0:
            return False, "El grupo ya no tiene cupo disponible."

        self._groups.add_member(gid, target_id)
        if gid != GLOBAL_GROUP_ID:
            self._groups.add_member(GLOBAL_GROUP_ID, target_id)

        gname = g.get("name", gid)
        self._users.update_profile(
            actor_id,
            group_add_member_group_id=None,
            group_add_member_alias=None,
            group_add_member_target_id=None,
        )
        return True, f'✅ {target_alias} sumado a "{gname}".'

    def begin_add_member_by_alias(self, actor_id: str, alias: str) -> tuple[str, dict | None]:
        """Resuelve alias; admin recibe teclado de grupos."""
        target = self.resolve_alias_user(alias)
        if self._auth.is_admin_global(actor_id):
            from src.services.invitation_telegram_ui import add_member_group_pick_keyboard

            groups = self._groups.list_active_groups(limit=12)
            self._users.update_profile(
                actor_id,
                group_add_member_alias=target.get("alias", alias),
                group_add_member_target_id=target["user_id"],
            )
            return (
                f'¿A qué grupo sumamos a "{target.get("alias", alias)}"?',
                add_member_group_pick_keyboard(groups, target.get("alias", alias)),
            )
        ok, msg = self.add_member_by_alias(actor_id, alias)
        return msg, None

    def create_group_for_user(
        self,
        admin_id: str,
        *,
        target_alias: str,
        name: str,
        avatar: str = "⚽",
    ) -> str:
        """Admin: crea grupo en un paso (tests / agent tool)."""
        if not self._auth.is_admin_global(admin_id):
            raise ValueError("Solo el admin global puede crear grupos en nombre de otro usuario.")
        target = self.resolve_alias_user(target_alias)
        tid = target["user_id"]
        owned = self._groups.get_owner_group_id(tid)
        if owned:
            old = self._groups.get_group(owned) or {}
            raise ValueError(
                f'{target.get("alias", target_alias)} ya tiene un grupo propio '
                f'("{old.get("name", owned)}").'
            )
        valid, n = self.validate_group_name(name)
        if not valid:
            raise ValueError(n)
        group = self._groups.create_group(
            owner_id=tid,
            name=n,
            avatar=avatar,
            max_members=5,
        )
        self._groups.add_member(GLOBAL_GROUP_ID, tid)
        self._users.update_profile(tid, groups_owned=1)
        from src.services.invitation_service import InvitationService

        inv = InvitationService().create_invitation(
            admin_id, max_uses=5, group_id=group["group_id"]
        )
        link = inv.get("link") or self._invite_link(inv["invite_id"])
        return (
            f'✅ Grupo "{n}" creado para {target.get("alias", target_alias)}\n'
            f"Link: {link}"
        )

    def start_create_group_for_user(self, admin_id: str, target_alias: str) -> tuple[str, dict | None]:
        if not self._auth.is_admin_global(admin_id):
            raise ValueError("Solo el admin global puede crear grupos en nombre de otro usuario.")
        target = self.resolve_alias_user(target_alias)
        tid = target["user_id"]
        owned = self._groups.get_owner_group_id(tid)
        if owned:
            old = self._groups.get_group(owned) or {}
            raise ValueError(
                f'{target.get("alias", target_alias)} ya tiene un grupo propio '
                f'("{old.get("name", owned)}"). Editá ese grupo o eliminálo primero.'
            )
        self._clear_create_state(admin_id)
        self._users.update_profile(
            admin_id,
            group_create_step="awaiting_name",
            group_create_for_user_id=tid,
            group_create_for_user_alias=target.get("alias", target_alias),
        )
        label = target.get("alias", target_alias)
        return (
            f'Creando grupo para "{label}".\n\n¿Cómo se va a llamar el grupo?',
            None,
        )

    def finish_create_group_for_user(self, admin_id: str, avatar: str) -> str:
        profile = self._users.get_profile(admin_id) or {}
        target_id = profile.get("group_create_for_user_id")
        draft_name = (profile.get("group_draft_name") or "").strip()
        target_alias = profile.get("group_create_for_user_alias", "el usuario")
        if not target_id or not draft_name:
            self._clear_create_state(admin_id)
            return "No encontré el flujo de creación. Empezá con /crear-grupo-para <alias>."

        group = self._groups.create_group(
            owner_id=target_id,
            name=draft_name,
            avatar=avatar,
            max_members=5,
        )
        self._groups.add_member(GLOBAL_GROUP_ID, target_id)
        self._users.update_profile(
            target_id,
            groups_owned=1,
        )
        self._clear_create_state(admin_id)

        from src.services.invitation_service import InvitationService

        inv = InvitationService().create_invitation(
            admin_id, max_uses=5, group_id=group["group_id"]
        )
        link = inv.get("link") or inv.get("invite_url") or self._invite_link(inv["invite_id"])

        notify = ""
        target_prof = self._users.get_profile(target_id) or {}
        if target_prof.get("tg_chat_id"):
            notify = (
                f'\nSe notificó a "{target_alias}" por Telegram (si tiene el bot abierto).'
            )

        return (
            f'✅ Grupo "{draft_name}" creado para {target_alias}\n\n'
            f"Owner: {target_alias}\n"
            f"Link de invitación (5 cupos):\n{link}"
            f"{notify}"
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

        self._set_group_context(user_id, gid)
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
        slots = self._auth.slots_available(group_id, actor_user_id=user_id)
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
        slots = self._auth.slots_available(group_id, actor_user_id=actor_id)
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

    def _handle_add_member_text(
        self, user_id: str, text: str
    ) -> tuple[str, dict | None] | None:
        """Alias suelto tras «Agregar por alias» en menú del grupo (SPEC-029)."""
        profile = self._users.get_profile(user_id) or {}
        gid = profile.get("group_add_member_group_id")
        if not gid:
            return None
        raw = (text or "").strip()
        if not raw or raw.startswith("/"):
            return None
        try:
            _, msg = self.add_member_by_alias(user_id, raw, group_id=gid)
            menu_text, menu_kb = self.format_edit_menu(user_id, gid)
            return f"{menu_text}\n\n{msg}", menu_kb
        except ValueError as exc:
            return str(exc), None

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
            profile = self._users.get_profile(user_id) or {}
            if profile.get("group_add_member_group_id"):
                gid = profile.get("group_context_group_id") or profile.get(
                    "group_add_member_group_id"
                )
                self._users.update_profile(user_id, group_add_member_group_id=None)
                if gid:
                    return self.format_edit_menu(user_id, gid)
                return "Cancelado.", None
            return None

        ctx_reply = self._handle_add_member_text(user_id, text)
        if ctx_reply is not None:
            return ctx_reply

        if step == "awaiting_name":
            return self.submit_create_name(user_id, text)

        if (pending or {}).get("action") == "rename":
            msg = self.apply_rename(user_id, text)
            return (msg, None) if msg else None

        if step == "awaiting_avatar":
            if text.strip().startswith("/"):
                return None
            from src.services.group_telegram_ui import avatar_picker_keyboard

            who = ""
            if profile.get("group_create_for_user_alias"):
                who = f' para "{profile["group_create_for_user_alias"]}"'
            return (
                f"Elegí un avatar para el grupo{who} 👆\n"
                "O enviá /cancel para salir.",
                avatar_picker_keyboard(),
            )

        return None
