"""Teclados inline Telegram para grupos (SPEC-026)."""
from __future__ import annotations

GROUP_AVATARS = ("⚽", "🏆", "🔥", "🌟", "🎯", "💪", "🤙", "⭐")


def avatar_picker_keyboard(*, prefix: str = "grp:av") -> dict:
    row1 = [{"text": e, "callback_data": f"{prefix}:{e}"} for e in GROUP_AVATARS[:4]]
    row2 = [{"text": e, "callback_data": f"{prefix}:{e}"} for e in GROUP_AVATARS[4:]]
    return {"inline_keyboard": [row1, row2]}


def confirm_delete_group_keyboard(group_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🗑️ Sí, eliminar", "callback_data": f"grp:del:yes:{group_id}"},
                {"text": "Cancelar", "callback_data": "grp:del:cancel"},
            ],
        ],
    }


def confirm_remove_member_keyboard(group_id: str, member_user_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Sí, eliminar",
                    "callback_data": f"grp:rm:yes:{group_id}:{member_user_id}",
                },
                {"text": "Cancelar", "callback_data": f"grp:menu:{group_id}"},
            ],
        ],
    }


def group_edit_menu_keyboard(group_id: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✏️ Cambiar nombre", "callback_data": f"grp:ren:{group_id}"}],
            [{"text": "🎨 Cambiar avatar", "callback_data": f"grp:avpick:{group_id}"}],
            [{"text": "👥 Gestionar miembros", "callback_data": f"grp:members:{group_id}"}],
            [{"text": "🔗 Nueva invitación", "callback_data": f"grp:inv:{group_id}"}],
            [{"text": "➕ Agregar por alias", "callback_data": f"grp:addalias:{group_id}"}],
            [{"text": "🗑️ Eliminar grupo", "callback_data": f"grp:del:ask:{group_id}"}],
            [{"text": "← Volver a /grupos", "callback_data": "grp:list"}],
        ],
    }


def admin_group_menu_keyboard(group_id: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✏️ Renombrar", "callback_data": f"grp:ren:{group_id}"}],
            [{"text": "🎨 Cambiar avatar", "callback_data": f"grp:avpick:{group_id}"}],
            [{"text": "👥 Gestionar miembros", "callback_data": f"grp:members:{group_id}"}],
            [{"text": "⏸️ Suspender grupo", "callback_data": f"grp:susp:ask:{group_id}"}],
            [{"text": "🗑️ Eliminar grupo", "callback_data": f"grp:del:ask:{group_id}"}],
            [{"text": "← Volver", "callback_data": "grp:admin:list"}],
        ],
    }


def limit_reached_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "📩 Pedir al admin", "callback_data": "grp:req_admin"}],
            [{"text": "Cancelar", "callback_data": "grp:cancel"}],
        ],
    }
