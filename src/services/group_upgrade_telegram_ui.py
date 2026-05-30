"""Teclados wizard ampliación grupos — SPEC-2026-044."""
from __future__ import annotations

from typing import Any


def upgrade_entry_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "💳 Ampliar plan", "callback_data": "gup:start"}],
        ],
    }


def limit_reached_with_upgrade_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "💳 Ampliar plan", "callback_data": "gup:start"}],
            [{"text": "📩 Pedir al admin", "callback_data": "grp:req_admin"}],
            [{"text": "Cancelar", "callback_data": "grp:cancel"}],
        ],
    }


def member_limit_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "💳 Ampliar cupos", "callback_data": "gup:start"}],
        ],
    }


def type_picker_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "➕ Solo grupos nuevos", "callback_data": "gup:type:groups"}],
            [{"text": "👥 Solo más integrantes", "callback_data": "gup:type:members"}],
            [{"text": "🔀 Combinación", "callback_data": "gup:type:combo"}],
            [{"text": "Cancelar", "callback_data": "gup:cancel"}],
        ],
    }


def units_picker_keyboard(*, max_units: int = 4) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for n in range(1, max_units + 1):
        row.append({"text": str(n), "callback_data": f"gup:ug:{n}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "Cancelar", "callback_data": "gup:cancel"}])
    return {"inline_keyboard": rows}


def owned_groups_keyboard(groups: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    for g in groups:
        gid = str(g.get("group_id") or "")
        g8 = gid.replace("-", "")[:8]
        label = f"{g.get('avatar', '⚽')} {(g.get('name') or gid)[:28]}"
        rows.append([{"text": label, "callback_data": f"gup:pickgrp:{g8}"}])
    rows.append([{"text": "Cancelar", "callback_data": "gup:cancel"}])
    return {"inline_keyboard": rows}


def combo_allocate_keyboard(
    *,
    groups: list[dict[str, Any]],
    remaining: int,
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    if remaining > 0:
        rows.append([{"text": "➕ 1 grupo nuevo", "callback_data": "gup:new:1"}])
        for g in groups:
            gid = str(g.get("group_id") or "")
            g8 = gid.replace("-", "")[:8]
            label = f"+5 en {(g.get('name') or gid)[:22]}"
            rows.append(
                [{"text": label, "callback_data": f"gup:grp:{g8}:1"}]
            )
    if remaining == 0:
        rows.append([{"text": "✅ Confirmar asignación", "callback_data": "gup:alloc:confirm"}])
    rows.append([{"text": "Cancelar", "callback_data": "gup:cancel"}])
    return {"inline_keyboard": rows}


def confirm_quote_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "✅ Confirmar y ver datos de pago", "callback_data": "gup:confirm_quote"}],
            [{"text": "Cancelar", "callback_data": "gup:cancel"}],
        ],
    }
