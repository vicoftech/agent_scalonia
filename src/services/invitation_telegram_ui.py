"""Teclados inline Telegram para invitaciones — SPEC-029."""
from __future__ import annotations

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID


def invite_destination_keyboard(max_uses: int, *, is_admin: bool, owner_group: dict | None) -> dict:
    """Admin: GLOBAL + elegir otro. Owner: su grupo."""
    n = max(1, int(max_uses))
    rows: list[list[dict[str, str]]] = []
    if is_admin:
        rows.append(
            [
                {
                    "text": f"🌍 General (GLOBAL) — {n} cupo{'s' if n != 1 else ''}",
                    "callback_data": f"inv:grp:{GLOBAL_GROUP_ID}:{n}",
                },
            ]
        )
        rows.append([{"text": "📋 Elegir otro grupo…", "callback_data": f"inv:pick:{n}"}])
    elif owner_group:
        gid = owner_group.get("group_id", "")
        name = (owner_group.get("name") or gid)[:28]
        rows.append(
            [
                {
                    "text": f"👥 {name} — {n} cupo{'s' if n != 1 else ''}",
                    "callback_data": f"inv:grp:{gid}:{n}",
                },
            ]
        )
    rows.append([{"text": "Cancelar", "callback_data": "inv:cancel"}])
    return {"inline_keyboard": rows}


def invite_group_pick_keyboard(groups: list[dict], max_uses: int) -> dict:
    """Lista de grupos para invitar (admin u owner con varios)."""
    n = max(1, int(max_uses))
    rows: list[list[dict[str, str]]] = []
    for g in groups[:15]:
        if g.get("is_global"):
            continue
        gid = g.get("group_id", "")
        if not gid:
            continue
        label = f"{g.get('avatar', '⚽')} {(g.get('name') or gid)[:24]}"
        rows.append([{"text": label, "callback_data": f"inv:grp:{gid}:{n}"}])
    if not rows:
        rows.append([{"text": "🌍 GLOBAL", "callback_data": f"inv:grp:{GLOBAL_GROUP_ID}:{n}"}])
    rows.append([{"text": "← Volver", "callback_data": f"inv:dest:{n}"}])
    return {"inline_keyboard": rows}


def add_member_group_pick_keyboard(groups: list[dict], target_alias: str) -> dict:
    """Admin elige grupo para /agregar-miembro <alias> (alias en PROFILE)."""
    _ = target_alias
    rows: list[list[dict[str, str]]] = []
    for g in groups[:15]:
        if g.get("is_global"):
            continue
        gid = g.get("group_id", "")
        if not gid:
            continue
        label = f"{g.get('avatar', '⚽')} {(g.get('name') or gid)[:22]}"
        rows.append([{"text": label, "callback_data": f"grp:add:{gid}"}])
    rows.append([{"text": "Cancelar", "callback_data": "grp:cancel"}])
    return {"inline_keyboard": rows}
