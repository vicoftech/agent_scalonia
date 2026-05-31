"""Hub inline de grupos — SPEC-2026-047."""
from __future__ import annotations

import re

from src.services.group_service import GroupService
from src.services.ranking_service import RankingService

_GRUPOS = re.compile(r"^/grupos(?:@[\w_]+)?\s*$", re.IGNORECASE)


def show_hub_home(user_id: str) -> tuple[str, dict]:
    return GroupService().format_hub_home(user_id)


def handle_grupos_command(user_id: str, text: str) -> tuple[str, dict | None] | None:
    if _GRUPOS.match((text or "").strip()):
        return show_hub_home(user_id)
    return None


def handle_group_hub_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("grh:"):
        return None

    svc = GroupService()
    rank_svc = RankingService()
    parts = data.split(":")

    if data == "grh:home":
        return show_hub_home(user_id)

    if len(parts) >= 3 and parts[1] == "g":
        gid = rank_svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido o sin acceso.", None
        g = svc._groups.get_group(gid) or {}
        if g.get("owner_id") == user_id:
            return svc.format_hub_owner_detail(user_id, gid)
        return svc.format_hub_member_detail(user_id, gid)

    if data == "grh:create":
        return svc.start_hub_create(user_id)

    if len(parts) >= 3 and parts[1] == "av":
        avatar = parts[2]
        profile = svc._users.get_profile(user_id) or {}
        if profile.get("group_hub_step") == "awaiting_create_avatar":
            return svc.finish_hub_create(user_id, avatar)
        return None

    if len(parts) >= 3 and parts[1] == "ren":
        gid = rank_svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido.", None
        return svc.start_hub_rename(user_id, gid)

    if len(parts) >= 3 and parts[1] == "add":
        gid = rank_svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido.", None
        return svc.start_hub_add_member(user_id, gid)

    if len(parts) >= 3 and parts[1] == "inv":
        from src.services.group_hub_telegram_ui import group_short, hub_owner_detail_keyboard
        from src.services.invitation_service import InvitationService

        gid = rank_svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido.", None
        try:
            inv = InvitationService().create_invitation(
                user_id, max_uses=1, group_id=gid
            )
            g8 = group_short(gid)
            msg = inv.get("message") or inv.get("link") or inv.get("invite_url", "")
            return msg, hub_owner_detail_keyboard(g8)
        except ValueError as exc:
            return str(exc), None

    if len(parts) >= 3 and parts[1] == "mem":
        gid = rank_svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido.", None
        return svc.format_hub_members(user_id, gid)

    if len(parts) >= 3 and parts[1] == "rank":
        from ranking_commands import show_group_ranking

        gid = rank_svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido.", None
        return show_group_ranking(user_id, gid)

    if len(parts) >= 4 and parts[1] == "rm":
        gid = rank_svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido.", None
        member_id = svc.resolve_member_short(gid, parts[3])
        if not member_id:
            return "Miembro no encontrado.", None
        ok, msg = svc.remove_member(user_id, gid, member_id)
        if ok:
            detail, kb = svc.format_hub_members(user_id, gid)
            return f"{msg}\n\n{detail}", kb
        return msg, None

    return None


def handle_group_hub_pending(
    user_id: str, profile: dict, text: str
) -> tuple[str, dict | None] | None:
    if not profile.get("group_hub_step"):
        return None
    return GroupService().handle_hub_pending(user_id, text)
