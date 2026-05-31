"""Ampliación grupos y cupos — SPEC-2026-044."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
from src.dao.dynamo.group_upgrade_dao import GroupUpgradeDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.user_dao import UserDAO

UNIT_LIST_PRICE = 14999
PROMO_PRICES: dict[int, int] = {1: 14999, 2: 27000, 3: 29997, 4: 49999}
FREE_BASE_OWNED_GROUPS = 1
MEMBERS_PER_PACK = 5


class GroupUpgradeService:
    def __init__(
        self,
        *,
        users: UserDAO | None = None,
        groups: GroupDAO | None = None,
        matches: MatchDAO | None = None,
        purchases: GroupUpgradeDAO | None = None,
        telegram_notify: Callable[[int, str], None] | None = None,
    ):
        self._users = users or UserDAO()
        self._groups = groups or GroupDAO()
        self._matches = matches or MatchDAO()
        self._purchases = purchases or GroupUpgradeDAO()
        self._telegram_notify = telegram_notify
        self.payment_alias = os.environ.get(
            "IA_PAYMENT_ALIAS", os.environ.get("GUP_PAYMENT_ALIAS", "Scalonia2026.mp")
        )
        self.purchase_cooldown_h = int(
            os.environ.get("GUP_AUTO_PURCHASE_COOLDOWN_H", "24")
        )

    def is_promo_period(self) -> bool:
        m = self._matches.find_by_teams("MEX", "RSA")
        return m is not None and not bool(m.get("veda_active"))

    def quote_units(self, units: int) -> tuple[int, bool, str]:
        units = max(1, int(units))
        promo = self.is_promo_period()
        if promo and units in PROMO_PRICES:
            total = PROMO_PRICES[units]
            label = "Precio promocional hasta la veda MEX vs RSA"
            return total, True, label
        total = units * UNIT_LIST_PRICE
        label = "Precio lista" if not promo else "Promoción finalizada — precio lista"
        return total, False, label

    def max_owned_groups(self, profile: dict[str, Any]) -> int:
        if profile.get("is_admin"):
            return 999
        extra = int(profile.get("extra_owned_group_slots") or 0)
        return FREE_BASE_OWNED_GROUPS + extra

    def list_owned_private_groups(self, user_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for gid in self._groups.list_owned_group_ids(user_id):
            g = self._groups.get_group(gid)
            if not g or g.get("status") == "DELETED" or g.get("is_global"):
                continue
            out.append(
                {
                    "group_id": gid,
                    "name": g.get("name") or gid[:8],
                    "avatar": g.get("avatar") or "⚽",
                    "max_members": int(g.get("max_members") or 5),
                }
            )
        out.sort(key=lambda x: str(x.get("name") or "").lower())
        return out

    def resolve_owned_group(self, user_id: str, ref: str) -> dict[str, Any] | None:
        needle = (ref or "").strip().lower()
        if not needle:
            return None
        for g in self.list_owned_private_groups(user_id):
            gid = str(g["group_id"])
            name = str(g.get("name") or "").lower()
            compact = gid.replace("-", "").lower()
            if (
                compact.startswith(needle)
                or gid.lower().startswith(needle)
                or name == needle
                or needle in name
            ):
                return g
        return None

    def _clear_wizard(self, user_id: str) -> None:
        self._users.update_profile(
            user_id,
            group_upgrade_wizard_type=None,
            group_upgrade_wizard_units=None,
            group_upgrade_alloc_draft=None,
            group_upgrade_purchase_id=None,
            group_upgrade_quote_ars=None,
            group_upgrade_promo_applied=None,
            group_upgrade_purchase_pending=False,
        )

    def start_wizard(self, user_id: str) -> tuple[str, dict]:
        from src.services.group_upgrade_telegram_ui import type_picker_keyboard

        self._clear_wizard(user_id)
        promo_hint = (
            "Precio promocional hasta el inicio del Mundial (veda MEX vs RSA).\n\n"
            if self.is_promo_period()
            else "Promoción finalizada — precio lista ($14.999 por unidad).\n\n"
        )
        text = (
            "💳 Ampliar tu plan\n\n"
            f"{promo_hint}"
            "1 unidad = 1 grupo nuevo o +5 integrantes en un grupo.\n\n"
            "¿Qué necesitás?"
        )
        return text, type_picker_keyboard()

    def start_member_pack_upgrade(
        self, user_id: str, group_id: str
    ) -> tuple[str, dict]:
        g = self._groups.get_group(group_id) or {}
        if str(g.get("owner_id")) != user_id:
            profile = self._users.get_profile(user_id) or {}
            if not profile.get("is_admin"):
                return "Sin permiso para ampliar este grupo.", {}
        self._clear_wizard(user_id)
        self._users.update_profile(
            user_id,
            group_upgrade_wizard_type="members",
            group_upgrade_pick_group_id=group_id,
        )
        allocation = [{"type": "MEMBER_PACK", "group_id": group_id, "packs": 1}]
        return self._set_quote(user_id, units=1, allocation=allocation)

    def _format_allocation_summary(self, allocation: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in allocation:
            if item.get("type") == "NEW_GROUP":
                lines.append("· 1 grupo nuevo")
            elif item.get("type") == "MEMBER_PACK":
                gid = item.get("group_id", "")
                g = self._groups.get_group(gid) or {}
                name = g.get("name") or gid[:8]
                packs = int(item.get("packs") or 1)
                lines.append(f"· +{packs * MEMBERS_PER_PACK} integrantes en «{name}»")
        return "\n".join(lines) if lines else "· (sin asignar)"

    def _set_quote(
        self,
        user_id: str,
        *,
        units: int,
        allocation: list[dict[str, Any]],
    ) -> tuple[str, dict]:
        from src.services.group_upgrade_telegram_ui import confirm_quote_keyboard

        total, promo, label = self.quote_units(units)
        purchase_id = self._purchases.create_purchase(
            user_id=user_id,
            units=units,
            amount_ars=total,
            promo_applied=promo,
            allocation_json=allocation,
        )
        self._users.update_profile(
            user_id,
            group_upgrade_wizard_units=units,
            group_upgrade_alloc_draft=json.dumps(allocation),
            group_upgrade_purchase_id=purchase_id,
            group_upgrade_quote_ars=total,
            group_upgrade_promo_applied=promo,
        )
        text = (
            "💳 Resumen de compra\n\n"
            f"Unidades: {units}\n"
            f"{self._format_allocation_summary(allocation)}\n\n"
            f"Total: ${total:,} ARS\n{label}".replace(",", ".")
        )
        return text, confirm_quote_keyboard()

    def confirm_quote(self, user_id: str) -> tuple[str, dict | None]:
        profile = self._users.get_profile(user_id) or {}
        units = int(profile.get("group_upgrade_wizard_units") or 0)
        total = int(profile.get("group_upgrade_quote_ars") or 0)
        if units <= 0 or total <= 0:
            return "No hay una cotización activa. Usá /ampliar_plan.", None

        raw_alloc = profile.get("group_upgrade_alloc_draft") or "[]"
        try:
            allocation = json.loads(raw_alloc) if isinstance(raw_alloc, str) else raw_alloc
        except json.JSONDecodeError:
            allocation = []

        promo = bool(profile.get("group_upgrade_promo_applied"))
        promo_tag = " (promo)" if promo else ""
        self._users.update_profile(user_id, group_upgrade_purchase_pending=True)
        text = (
            "💳 Ampliar tu plan\n\n"
            f"Resumen: {units} unidades\n"
            f"{self._format_allocation_summary(allocation)}\n"
            f"Precio: ${total:,} ARS{promo_tag}\n\n"
            f"Transferí a alias:\n{self.payment_alias}\n\n"
            "Enviá el comprobante en este chat (foto o PDF).\n"
            "Si no completaste el wizard, indicá en un mensaje si querés "
            "grupos nuevos o más integrantes y en qué grupo."
        ).replace(",", ".")
        return text, None

    def callback(self, user_id: str, data: str) -> tuple[str, dict | None] | None:
        from src.services.group_upgrade_telegram_ui import (
            combo_allocate_keyboard,
            owned_groups_keyboard,
            units_picker_keyboard,
        )

        if data == "gup:start":
            return self.start_wizard(user_id)
        if data.startswith("gup:quickmem:"):
            g8 = data.split(":", 2)[2]
            group = self.resolve_owned_group(user_id, g8)
            if not group:
                return "Grupo no encontrado.", None
            return self.start_member_pack_upgrade(user_id, group["group_id"])
        if data == "gup:cancel":
            self._clear_wizard(user_id)
            return "Compra cancelada.", None
        if data == "gup:confirm_quote":
            return self.confirm_quote(user_id)

        profile = self._users.get_profile(user_id) or {}

        if data == "gup:type:groups":
            self._users.update_profile(user_id, group_upgrade_wizard_type="groups")
            return "¿Cuántos grupos nuevos querés?", units_picker_keyboard()

        if data == "gup:type:members":
            groups = self.list_owned_private_groups(user_id)
            if not groups:
                return (
                    "No tenés grupos propios para ampliar cupos.\n"
                    "Creá uno con /crear-grupo o comprá un grupo nuevo.",
                    None,
                )
            self._users.update_profile(user_id, group_upgrade_wizard_type="members")
            return "Elegí el grupo:", owned_groups_keyboard(groups)

        if data == "gup:type:combo":
            self._users.update_profile(
                user_id,
                group_upgrade_wizard_type="combo",
                group_upgrade_alloc_draft=json.dumps([]),
            )
            return "¿Cuántas unidades querés comprar?", units_picker_keyboard()

        if data.startswith("gup:ug:"):
            try:
                units = int(data.split(":")[2])
            except (IndexError, ValueError):
                return "Cantidad inválida.", None
            wtype = profile.get("group_upgrade_wizard_type")
            if wtype == "groups":
                allocation = [{"type": "NEW_GROUP"} for _ in range(units)]
                return self._set_quote(user_id, units=units, allocation=allocation)
            if wtype == "members":
                gid = profile.get("group_upgrade_pick_group_id")
                if not gid:
                    return "Elegí primero un grupo.", None
                allocation = [
                    {"type": "MEMBER_PACK", "group_id": gid, "packs": units}
                ]
                return self._set_quote(user_id, units=units, allocation=allocation)
            if wtype == "combo":
                self._users.update_profile(
                    user_id,
                    group_upgrade_wizard_units=units,
                    group_upgrade_alloc_draft=json.dumps([]),
                )
                groups = self.list_owned_private_groups(user_id)
                return (
                    f"Te quedan {units} U por asignar:",
                    combo_allocate_keyboard(groups=groups, remaining=units),
                )
            return "Elegí primero el tipo de ampliación.", None

        if data.startswith("gup:pickgrp:"):
            g8 = data.split(":", 2)[2]
            group = self.resolve_owned_group(user_id, g8)
            if not group:
                return "Grupo no encontrado.", None
            self._users.update_profile(
                user_id,
                group_upgrade_pick_group_id=group["group_id"],
            )
            return (
                f'Grupo «{group["name"]}». ¿Cuántos packs de 5 integrantes? '
                "(1 unidad = +5)",
                units_picker_keyboard(max_units=4),
            )

        if data.startswith("gup:grp:"):
            parts = data.split(":")
            if len(parts) < 4:
                return None
            g8, packs_s = parts[2], parts[3]
            try:
                packs = int(packs_s)
            except ValueError:
                return "Cantidad inválida.", None
            group = self.resolve_owned_group(user_id, g8)
            if not group:
                return "Grupo no encontrado.", None
            wtype = profile.get("group_upgrade_wizard_type")
            if wtype == "members":
                gid = profile.get("group_upgrade_pick_group_id") or group["group_id"]
                allocation = [
                    {"type": "MEMBER_PACK", "group_id": gid, "packs": packs}
                ]
                return self._set_quote(user_id, units=packs, allocation=allocation)
            if wtype == "combo":
                return self._combo_add_pack(user_id, group["group_id"], packs)
            return None

        if data.startswith("gup:new:"):
            try:
                n = int(data.split(":")[2])
            except (IndexError, ValueError):
                return "Cantidad inválida.", None
            return self._combo_add_groups(user_id, n)

        if data == "gup:alloc:confirm":
            return self._combo_finish(user_id)

        return None

    def _load_alloc_draft(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        raw = profile.get("group_upgrade_alloc_draft") or "[]"
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return list(data) if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def _save_alloc_draft(self, user_id: str, allocation: list[dict[str, Any]]) -> None:
        self._users.update_profile(
            user_id, group_upgrade_alloc_draft=json.dumps(allocation)
        )

    def _combo_remaining(self, profile: dict[str, Any]) -> int:
        total = int(profile.get("group_upgrade_wizard_units") or 0)
        alloc = self._load_alloc_draft(profile)
        used = sum(
            1 if a.get("type") == "NEW_GROUP" else int(a.get("packs") or 1)
            for a in alloc
        )
        return max(0, total - used)

    def _combo_add_groups(self, user_id: str, n: int) -> tuple[str, dict]:
        from src.services.group_upgrade_telegram_ui import combo_allocate_keyboard

        profile = self._users.get_profile(user_id) or {}
        remaining = self._combo_remaining(profile)
        if n > remaining:
            return f"Solo te quedan {remaining} U por asignar.", None
        alloc = self._load_alloc_draft(profile)
        alloc.extend([{"type": "NEW_GROUP"} for _ in range(n)])
        self._save_alloc_draft(user_id, alloc)
        left = self._combo_remaining(self._users.get_profile(user_id) or {})
        groups = self.list_owned_private_groups(user_id)
        return (
            f"Asignado {n} grupo(s). Te quedan {left} U:",
            combo_allocate_keyboard(groups=groups, remaining=left),
        )

    def _combo_add_pack(self, user_id: str, group_id: str, packs: int) -> tuple[str, dict]:
        from src.services.group_upgrade_telegram_ui import combo_allocate_keyboard

        profile = self._users.get_profile(user_id) or {}
        remaining = self._combo_remaining(profile)
        if packs > remaining:
            return f"Solo te quedan {remaining} U por asignar.", None
        alloc = self._load_alloc_draft(profile)
        alloc.append({"type": "MEMBER_PACK", "group_id": group_id, "packs": packs})
        self._save_alloc_draft(user_id, alloc)
        left = self._combo_remaining(self._users.get_profile(user_id) or {})
        groups = self.list_owned_private_groups(user_id)
        return (
            f"Asignado +{packs * MEMBERS_PER_PACK} integrantes. Te quedan {left} U:",
            combo_allocate_keyboard(groups=groups, remaining=left),
        )

    def _combo_finish(self, user_id: str) -> tuple[str, dict]:
        profile = self._users.get_profile(user_id) or {}
        units = int(profile.get("group_upgrade_wizard_units") or 0)
        alloc = self._load_alloc_draft(profile)
        if self._combo_remaining(profile) != 0:
            return "Todavía tenés unidades sin asignar.", None
        if not alloc:
            return "Asigná al menos una unidad.", None
        return self._set_quote(user_id, units=units, allocation=alloc)

    def _purchase_cooldown_active(self, profile: dict[str, Any]) -> bool:
        raw = profile.get("last_group_upgrade_purchase_at")
        if not raw:
            return False
        try:
            last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return False
        delta = datetime.now(timezone.utc) - last.astimezone(timezone.utc)
        return delta < timedelta(hours=self.purchase_cooldown_h)

    def handle_payment_proof(self, user_id: str, *, file_id: str) -> str:
        profile = self._users.get_profile(user_id) or {}
        if not profile.get("group_upgrade_purchase_pending"):
            return "Para enviar un comprobante, primero usá /ampliar_plan y confirmá la cotización."

        if self._purchase_cooldown_active(profile):
            return (
                "Ya procesamos un comprobante de ampliación en las últimas 24 h.\n"
                "Si pagaste de nuevo, contactá al admin."
            )

        if self._purchases.find_by_file_id(file_id):
            return "Ese comprobante ya fue registrado."

        units = int(profile.get("group_upgrade_wizard_units") or 0)
        purchase_id = profile.get("group_upgrade_purchase_id") or ""
        if units <= 0:
            return "No hay una compra en curso. Usá /ampliar_plan de nuevo."

        pending = int(profile.get("pending_group_upgrade_units") or 0) + units
        now = datetime.now(timezone.utc).isoformat()
        if purchase_id:
            self._purchases.mark_paid(purchase_id, telegram_file_id=file_id)

        self._users.update_profile(
            user_id,
            pending_group_upgrade_units=pending,
            group_upgrade_purchase_pending=False,
            last_group_upgrade_purchase_at=now,
        )

        raw_alloc = profile.get("group_upgrade_alloc_draft") or "[]"
        try:
            allocation = json.loads(raw_alloc) if isinstance(raw_alloc, str) else raw_alloc
        except json.JSONDecodeError:
            allocation = []

        if allocation and self._allocation_units(allocation) <= pending:
            summary = self.apply_allocation(user_id, allocation)
            return (
                f"✅ Pago registrado ({units} U).\n{summary}\n\n"
                "Ya podés crear grupos o invitar más integrantes."
            )

        return (
            f"✅ Pago registrado: {units} unidad(es) acreditadas.\n"
            f"Tenés {pending} U pendientes de asignar.\n"
            "Usá /ampliar_plan → Combinación para asignarlas, "
            "o escribile al admin con tu comprobante."
        )

    def _allocation_units(self, allocation: list[dict[str, Any]]) -> int:
        total = 0
        for item in allocation:
            if item.get("type") == "NEW_GROUP":
                total += 1
            elif item.get("type") == "MEMBER_PACK":
                total += int(item.get("packs") or 1)
        return total

    def apply_allocation(
        self, user_id: str, allocation: list[dict[str, Any]]
    ) -> str:
        profile = self._users.get_profile(user_id) or {}
        pending = int(profile.get("pending_group_upgrade_units") or 0)
        need = self._allocation_units(allocation)
        if need > pending:
            raise ValueError(f"Solo tenés {pending} U pendientes")

        lines: list[str] = []
        extra_slots = int(profile.get("extra_owned_group_slots") or 0)

        for item in allocation:
            if item.get("type") == "NEW_GROUP":
                extra_slots += 1
                lines.append("· +1 slot para grupo nuevo")
            elif item.get("type") == "MEMBER_PACK":
                gid = str(item.get("group_id") or "")
                packs = int(item.get("packs") or 1)
                g = self._groups.get_group(gid)
                if not g or g.get("owner_id") != user_id:
                    raise ValueError("Grupo inválido para ampliar cupos")
                if g.get("is_global"):
                    raise ValueError("No se amplió GLOBAL")
                current = int(g.get("max_members") or 5)
                new_cap = current + packs * MEMBERS_PER_PACK
                self._groups.update_group(gid, max_members=new_cap)
                lines.append(
                    f"· «{g.get('name', gid[:8])}»: cupo {current} → {new_cap}"
                )

        self._users.update_profile(
            user_id,
            extra_owned_group_slots=extra_slots,
            pending_group_upgrade_units=pending - need,
            group_upgrade_alloc_draft=None,
            group_upgrade_wizard_units=None,
            group_upgrade_purchase_id=None,
        )
        purchase_id = profile.get("group_upgrade_purchase_id")
        if purchase_id:
            self._purchases.mark_allocated(str(purchase_id))
        return "Aplicado:\n" + "\n".join(lines)

    def admin_grant_group_slots(self, admin_id: str, alias: str, count: int = 1) -> str:
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(admin_id):
            return "Solo el administrador puede usar este comando."
        target = self._users.resolve_alias(alias.strip())
        if not target:
            return f"No encontré el alias «{alias}»."
        uid = target["user_id"]
        profile = self._users.get_profile(uid) or {}
        extra = int(profile.get("extra_owned_group_slots") or 0) + max(1, int(count))
        self._users.update_profile(uid, extra_owned_group_slots=extra)
        n = max(1, int(count))
        notify_text = (
            f"🎁 Te habilitaron crear {n} grupo(s) más. "
            "Tocá 👥 Grupos → Crear grupo nuevo."
        )
        notified = self._notify(uid, profile, notify_text)
        suffix = "" if notified else " (sin notificación — sin tg_chat_id)"
        return (
            f"✅ {alias}: +{count} slot(s) de grupo "
            f"(total extra: {extra}).{suffix}"
        )

    def admin_grant_member_packs(
        self, admin_id: str, alias: str, group_ref: str, packs: int
    ) -> str:
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(admin_id):
            return "Solo el administrador puede usar este comando."
        target = self._users.resolve_alias(alias.strip())
        if not target:
            return f"No encontré el alias «{alias}»."
        uid = target["user_id"]
        profile = self._users.get_profile(uid) or {}
        group = self.resolve_owned_group(uid, group_ref)
        if not group:
            return f"No encontré grupo «{group_ref}» de ese usuario."
        gid = group["group_id"]
        g = self._groups.get_group(gid) or {}
        current = int(g.get("max_members") or 5)
        packs = max(1, int(packs))
        new_cap = current + packs * MEMBERS_PER_PACK
        self._groups.update_group(gid, max_members=new_cap)
        gname = g.get("name", gid[:8])
        notify_text = (
            f'🎁 «{gname}» ahora admite {new_cap} miembros (+{packs * MEMBERS_PER_PACK}). '
            "Tocá 👥 Grupos para invitar."
        )
        notified = self._notify(uid, profile, notify_text)
        suffix = "" if notified else " (sin notificación — sin tg_chat_id)"
        return (
            f"✅ {alias} — «{gname}»: "
            f"max_members {current} → {new_cap}{suffix}"
        )

    def admin_apply_units(self, admin_id: str, alias: str, units: int) -> str:
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(admin_id):
            return "Solo el administrador puede usar este comando."
        target = self._users.resolve_alias(alias.strip())
        if not target:
            return f"No encontré el alias «{alias}»."
        uid = target["user_id"]
        profile = self._users.get_profile(uid) or {}
        pending = int(profile.get("pending_group_upgrade_units") or 0) + max(
            1, int(units)
        )
        self._users.update_profile(uid, pending_group_upgrade_units=pending)
        added = max(1, int(units))
        notify_text = (
            f"🎁 Tenés {added} unidad(es) para asignar. "
            "Tocá 💳 Ampliar plan o 👥 Grupos."
        )
        notified = self._notify(uid, profile, notify_text)
        suffix = "" if notified else " (sin notificación — sin tg_chat_id)"
        return f"✅ {alias}: +{units} U pendientes (total {pending}).{suffix}"

    def admin_list_pending(self, admin_id: str) -> str:
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(admin_id):
            return "Solo el administrador puede usar este comando."
        items = self._purchases.list_recent(limit=15)
        pending = [
            i
            for i in items
            if i.get("status") in ("PENDING_PAYMENT", "PAID")
        ]
        if not pending:
            return "No hay compras GROUP_UPGRADE recientes pendientes."
        lines = ["📋 Compras ampliación (recientes)", ""]
        for it in pending[:10]:
            lines.append(
                f"· {str(it.get('purchase_id', ''))[:8]}… "
                f"U={it.get('units')} ${it.get('amount_ars')} "
                f"st={it.get('status')}"
            )
        return "\n".join(lines)

    def admin_show_quotas(self, admin_id: str, alias: str) -> str:
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(admin_id):
            return "Solo el administrador puede usar este comando."
        target = self._users.resolve_alias(alias.strip())
        if not target:
            return f"No encontré el alias «{alias}»."
        uid = target["user_id"]
        profile = self._users.get_profile(uid) or {}
        lines = [
            f"📊 Cuotas — {alias}",
            "",
            f"Slots extra grupos: {int(profile.get('extra_owned_group_slots') or 0)}",
            f"U pendientes: {int(profile.get('pending_group_upgrade_units') or 0)}",
            f"Máx grupos: {self.max_owned_groups(profile)}",
            "",
            "Grupos propios:",
        ]
        for g in self.list_owned_private_groups(uid):
            lines.append(
                f"· {g.get('name')} — max {g.get('max_members')} miembros"
            )
        return "\n".join(lines)

    def _notify(self, user_id: str, profile: dict[str, Any], text: str) -> bool:
        if not self._telegram_notify:
            return False
        if profile.get("notifications_enabled") is False:
            return False
        chat_id = profile.get("tg_chat_id")
        if chat_id is None:
            return False
        try:
            self._telegram_notify(int(chat_id), text)
            return True
        except Exception:
            return False

    def member_limit_message(self, group_name: str, max_members: int) -> tuple[str, dict]:
        from src.services.group_upgrade_telegram_ui import member_limit_keyboard

        return (
            f"El grupo «{group_name}» llegó al cupo ({max_members}/{max_members}).\n"
            "Comprá +5 integrantes con una unidad:",
            member_limit_keyboard(),
        )
