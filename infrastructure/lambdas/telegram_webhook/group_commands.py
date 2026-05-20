"""Comandos /grupos, /crear-grupo, /editar-grupo — SPEC-026 (Lambda directa)."""
from __future__ import annotations

import re

from src.services.group_service import GroupService

_GRUPOS = re.compile(r"^/grupos(?:@[\w_]+)?\s*$", re.IGNORECASE)
_CREAR = re.compile(r"^/crear[-_]grupo(?:@[\w_]+)?\s*$", re.IGNORECASE)
_EDITAR = re.compile(r"^/editar[-_]grupo(?:@[\w_]+)?\s*$", re.IGNORECASE)
_MIEMBROS = re.compile(r"^/miembros(?:@[\w_]+)?\s*$", re.IGNORECASE)
_ADMIN = re.compile(r"^/admin[-_]grupos(?:@[\w_]+)?\s*$", re.IGNORECASE)
_CREAR_PARA = re.compile(
    r"^/crear[-_]grupo[-_]para(?:@[\w_]+)?\s+(\S+)\s*$",
    re.IGNORECASE,
)
_AGREGAR = re.compile(
    r"^/agregar[-_]miembro(?:@[\w_]+)?(?:\s+(\S+))?\s*$",
    re.IGNORECASE,
)


def handle_group_command(user_id: str, text: str) -> tuple[str, dict | None] | None:
    svc = GroupService()
    if _GRUPOS.match(text.strip()):
        return svc.format_groups_list(user_id), None
    if _CREAR.match(text.strip()):
        return svc.start_create_group(user_id)
    if _EDITAR.match(text.strip()):
        return svc.format_edit_menu(user_id)
    if _MIEMBROS.match(text.strip()):
        gid = svc.get_owned_group_id(user_id)
        if not gid:
            return "No tenés un grupo propio.", None
        return svc.format_members_list(user_id, gid), None
    if _ADMIN.match(text.strip()):
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(user_id):
            return "Solo el admin global puede usar este comando.", None
        return svc.format_admin_groups_list(), None

    m = _CREAR_PARA.match(text.strip())
    if m:
        try:
            return svc.start_create_group_for_user(user_id, m.group(1))
        except ValueError as exc:
            return str(exc), None

    m = _AGREGAR.match(text.strip())
    if m:
        alias = m.group(1)
        if not alias:
            return (
                "Uso: /agregar-miembro <alias>\n"
                "Ejemplo: /agregar-miembro vic",
                None,
            )
        try:
            return svc.begin_add_member_by_alias(user_id, alias)
        except ValueError as exc:
            return str(exc), None

    return None


def handle_group_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    """Callbacks inline grp:*"""
    if not data.startswith("grp:"):
        return None
    svc = GroupService()
    parts = data.split(":", maxsplit=4)

    if data == "grp:list":
        return svc.format_groups_list(user_id), None
    if data == "grp:cancel":
        svc._clear_create_state(user_id)
        return "Cancelado.", None
    if data == "grp:req_admin":
        return svc.request_admin_new_group(user_id), None

    if len(parts) >= 3 and parts[1] == "av":
        avatar = parts[2]
        profile = svc._users.get_profile(user_id) or {}
        if profile.get("group_create_step") == "awaiting_avatar":
            return svc.finish_create_group(user_id, avatar), None
        return None

    if len(parts) >= 3 and parts[1] == "menu":
        return svc.format_edit_menu(user_id, parts[2])

    if len(parts) >= 3 and parts[1] == "ren":
        return svc.start_rename(user_id, parts[2]), None

    if len(parts) >= 3 and parts[1] == "avpick":
        from src.services.group_telegram_ui import avatar_picker_keyboard

        gid = parts[2]
        return (
            "Elegí el nuevo avatar:",
            avatar_picker_keyboard(prefix=f"grp:setav:{gid}"),
        )

    if len(parts) >= 4 and parts[1] == "setav":
        gid = parts[2]
        avatar = parts[3]
        msg = svc.apply_avatar(user_id, gid, avatar)
        _, kb = svc.format_edit_menu(user_id, gid)
        return msg, kb

    if len(parts) >= 3 and parts[1] == "members":
        gid = parts[2]
        return svc.format_members_list(user_id, gid), None

    if len(parts) >= 3 and parts[1] == "addalias":
        gid = parts[2]
        svc._users.update_profile(user_id, group_add_member_group_id=gid)
        return (
            "Enviá /agregar-miembro <alias> para sumar a este grupo.\n"
            "Ejemplo: /agregar-miembro vic",
            None,
        )

    if len(parts) >= 3 and parts[1] == "add":
        gid = parts[2]
        alias = parts[3] if len(parts) > 3 else None
        profile = svc._users.get_profile(user_id) or {}
        alias = alias or profile.get("group_add_member_alias")
        if not alias:
            return "No encontré el alias. Usá /agregar-miembro <alias>.", None
        try:
            ok, msg = svc.add_member_by_alias(user_id, alias, group_id=gid)
            return msg, None
        except ValueError as exc:
            return str(exc), None

    if len(parts) >= 3 and parts[1] == "inv":
        from src.services.invitation_service import InvitationService

        gid = parts[2]
        try:
            inv = InvitationService().create_invitation(
                user_id, max_uses=5, group_id=gid
            )
            return (
                f"🔗 Invitación creada ({inv['max_uses']} cupos):\n"
                f"{inv.get('link', inv.get('invite_url', ''))}",
                None,
            )
        except ValueError as exc:
            return str(exc), None

    if len(parts) >= 4 and parts[1] == "del" and parts[2] == "ask":
        from src.services.group_telegram_ui import confirm_delete_group_keyboard

        gid = parts[3]
        g = svc._groups.get_group(gid)
        name = g.get("name", gid) if g else gid
        return (
            f'¿Seguro que querés eliminar "{name}"?\n'
            "Los miembros perderán acceso al ranking del grupo.\n"
            "Esta acción no se puede deshacer.",
            confirm_delete_group_keyboard(gid),
        )

    if len(parts) >= 3 and parts[1] == "del" and parts[2] == "yes" and len(parts) >= 4:
        ok, msg = svc.delete_group(user_id, parts[3])
        return msg, None

    if data == "grp:del:cancel":
        return "Eliminación cancelada.", None

    if len(parts) >= 5 and parts[1] == "rm" and parts[2] == "yes":
        _, _, _, gid, member_id = parts[0], parts[1], parts[2], parts[3], parts[4]
        ok, msg = svc.remove_member(user_id, gid, member_id)
        return msg, None

    if len(parts) >= 4 and parts[1] == "susp" and parts[2] == "yes":
        ok, msg = svc.suspend_group(user_id, parts[3])
        return msg, None

    if len(parts) >= 4 and parts[1] == "susp" and parts[2] == "ask":
        gid = parts[3]
        from src.services.group_telegram_ui import confirm_delete_group_keyboard

        g = svc._groups.get_group(gid)
        name = g.get("name", gid) if g else gid
        kb = {
            "inline_keyboard": [
                [
                    {"text": "⏸️ Sí, suspender", "callback_data": f"grp:susp:yes:{gid}"},
                    {"text": "Cancelar", "callback_data": f"grp:menu:{gid}"},
                ],
            ],
        }
        return (
            f'¿Suspendés "{name}"?\n'
            "Los miembros no podrán ver el ranking ni interactuar en el grupo.",
            kb,
        )

    if data == "grp:admin:list":
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(user_id):
            return "Solo admin.", None
        return svc.format_admin_groups_list(), None

    return None


def handle_group_pending_message(
    user_id: str, profile: dict, text: str
) -> tuple[str, dict | None] | None:
    """Mensajes de texto durante crear-grupo o renombrar."""
    step = profile.get("group_create_step")
    pending = profile.get("group_edit_pending")
    if not step and not pending:
        return None
    svc = GroupService()
    return svc.handle_pending_with_markup(user_id, text)
