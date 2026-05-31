"""Teclados inline hub de grupos — SPEC-2026-047."""
from __future__ import annotations

from typing import Any

from src.services.group_telegram_ui import GROUP_AVATARS


def group_short(group_id: str) -> str:
    return str(group_id or "").replace("-", "")[:8]


def hub_back_home_row() -> list[dict[str, str]]:
    return [{"text": "← Volver a mis grupos", "callback_data": "grh:home"}]


def hub_home_keyboard(
    groups: list[dict[str, Any]],
    *,
    can_create: bool,
    show_upgrade: bool,
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    for g in groups:
        gid = str(g.get("group_id") or "")
        g8 = group_short(gid)
        avatar = g.get("avatar") or "⚽"
        name = (g.get("name") or gid)[:24]
        role = g.get("role") or "miembro"
        badge = "owner" if role == "owner" else "miembro"
        rows.append(
            [
                {
                    "text": f"{avatar} {name}  {badge}",
                    "callback_data": f"grh:g:{g8}",
                }
            ]
        )
    if can_create:
        rows.append([{"text": "➕ Crear grupo nuevo", "callback_data": "grh:create"}])
    elif show_upgrade:
        rows.append([{"text": "💳 Ampliar plan", "callback_data": "gup:start"}])
    return {"inline_keyboard": rows}


def hub_owner_detail_keyboard(g8: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "✏️ Cambiar nombre", "callback_data": f"grh:ren:{g8}"}],
            [{"text": "➕ Agregar jugadores", "callback_data": f"grh:add:{g8}"}],
            [{"text": "🔗 Invitar con link", "callback_data": f"grh:inv:{g8}"}],
            [{"text": "👥 Ver miembros", "callback_data": f"grh:mem:{g8}"}],
            hub_back_home_row(),
        ],
    }


def hub_member_detail_keyboard(g8: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🏆 Ver mi ranking", "callback_data": f"rnk:g:{g8}"}],
            hub_back_home_row(),
        ],
    }


def hub_avatar_keyboard() -> dict[str, Any]:
    row1 = [{"text": e, "callback_data": f"grh:av:{e}"} for e in GROUP_AVATARS[:4]]
    row2 = [{"text": e, "callback_data": f"grh:av:{e}"} for e in GROUP_AVATARS[4:]]
    rows = [row1, row2, [hub_back_home_row()[0]]]
    return {"inline_keyboard": rows}


def hub_created_keyboard(g8: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🔗 Invitar amigos", "callback_data": f"grh:inv:{g8}"}],
            hub_back_home_row(),
        ],
    }


def hub_member_limit_keyboard(g8: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "💳 Ampliar cupos (+5)", "callback_data": f"gup:quickmem:{g8}"}],
            hub_back_home_row(),
        ],
    }


def hub_create_limit_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "💳 Ampliar plan", "callback_data": "gup:start"}],
            hub_back_home_row(),
        ],
    }


def hub_members_keyboard(
    g8: str,
    members: list[dict[str, Any]],
    *,
    owner_id: str,
    viewer_id: str,
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    for m in members:
        uid = str(m.get("user_id") or "")
        if uid == owner_id or uid == viewer_id:
            continue
        alias = (m.get("alias") or uid[:8])[:20]
        u8 = uid.replace("-", "")[:8]
        rows.append(
            [
                {
                    "text": f"❌ {alias}",
                    "callback_data": f"grh:rm:{g8}:{u8}",
                }
            ]
        )
    rows.append(hub_back_home_row())
    return {"inline_keyboard": rows}


def hub_after_add_keyboard(g8: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "➕ Agregar otro", "callback_data": f"grh:add:{g8}"}],
            [{"text": "👥 Ver miembros", "callback_data": f"grh:mem:{g8}"}],
            hub_back_home_row(),
        ],
    }
