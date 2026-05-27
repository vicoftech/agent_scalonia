"""Ask IA — créditos diarios, sesión AgentCore, upgrade por comprobante (SPEC-2026-043)."""
from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from src.dao.dynamo.ia_purchase_dao import IaPurchaseDAO
from src.dao.dynamo.user_dao import UserDAO

DISPLAY_TZ = timezone(timedelta(hours=-3))

INVALID_COMMAND = (
    "❌ Comando no válido.\n\n"
    "Usá el menú / o los botones de abajo. Ayuda: /help"
)

RESULTADOS_DEPRECATED = (
    "🏁 El atajo Resultados fue reemplazado por Ask IA.\n\n"
    "Usá /ask_ia o el botón «🤖 Ask IA» para consultar al agente sobre el Mundial."
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _today_ar() -> str:
    return datetime.now(DISPLAY_TZ).date().isoformat()


class AskIaService:
    def __init__(
        self,
        users: UserDAO | None = None,
        purchases: IaPurchaseDAO | None = None,
        *,
        invoke_agent: Callable[[str, str, str], str] | None = None,
    ):
        self._users = users or UserDAO()
        self._purchases = purchases or IaPurchaseDAO()
        self._invoke_agent = invoke_agent
        self.daily_free = _env_int("IA_DAILY_FREE_CREDITS", 5)
        self.pack_bonus = _env_int("IA_PACK_BONUS_CREDITS", 20)
        self.min_pack_ars = _env_int("IA_MIN_PACK_ARS", 6999)
        self.payment_alias = os.environ.get("IA_PAYMENT_ALIAS", "Scalonia2026.mp")
        self.purchase_cooldown_h = _env_int("IA_AUTO_PURCHASE_COOLDOWN_H", 24)

    def credits_available(self, profile: dict[str, Any]) -> int:
        daily = int(profile.get("ai_daily_remaining") or 0)
        bonus = int(profile.get("ai_bonus_credits") or 0)
        return daily + bonus

    def ensure_daily_reset(self, user_id: str) -> dict[str, Any]:
        profile = self._users.get_profile(user_id) or {}
        today = _today_ar()
        reset_date = profile.get("ai_credits_reset_date")
        if reset_date != today:
            self._users.update_profile(
                user_id,
                ai_daily_remaining=self.daily_free,
                ai_credits_reset_date=today,
            )
            profile = self._users.get_profile(user_id) or profile
            profile["ai_daily_remaining"] = self.daily_free
            profile["ai_credits_reset_date"] = today
        elif profile.get("ai_daily_remaining") is None:
            self._users.update_profile(
                user_id,
                ai_daily_remaining=self.daily_free,
                ai_credits_reset_date=today,
            )
            profile = self._users.get_profile(user_id) or profile
        return profile

    def _session_id(self, user_id: str, profile: dict[str, Any]) -> str:
        sid = profile.get("ai_session_id")
        if sid and len(str(sid)) >= 33:
            return str(sid)
        new_sid = f"ask-{user_id}-{uuid.uuid4()}"[:64]
        if len(new_sid) < 33:
            new_sid = f"ask-{user_id}-{uuid.uuid4().hex}"[:64]
        return new_sid

    def _consume_credit(self, user_id: str, profile: dict[str, Any]) -> None:
        daily = int(profile.get("ai_daily_remaining") or 0)
        bonus = int(profile.get("ai_bonus_credits") or 0)
        if daily > 0:
            self._users.update_profile(user_id, ai_daily_remaining=daily - 1)
        elif bonus > 0:
            self._users.update_profile(user_id, ai_bonus_credits=bonus - 1)

    def _no_credits_message(self) -> tuple[str, dict]:
        from src.services.ask_ia_ui import no_credits_keyboard

        text = (
            "⛔ Usaste todas tus consultas de hoy.\n\n"
            "Volvé a tener consultas gratis mañana a las 00:01 (hora Argentina).\n"
            "¿Querés más ahora? Tocá el botón de abajo."
        )
        return text, no_credits_keyboard()

    def start_session(self, user_id: str) -> tuple[str, dict | None]:
        profile = self.ensure_daily_reset(user_id)
        n = self.credits_available(profile)
        if n <= 0:
            return self._no_credits_message()

        session_id = self._session_id(user_id, profile)
        self._users.update_profile(
            user_id,
            ai_session_id=session_id,
            ai_awaiting_prompt=True,
            ai_purchase_pending=False,
        )
        text = (
            f"🤖 Ask IA — Mundial 2026\n\n"
            f"Tenés {n} consultas disponibles.\n"
            f"Escribí tu pregunta:"
        )
        return text, None

    def request_upgrade(self, user_id: str) -> tuple[str, dict]:
        from src.services.ask_ia_ui import upgrade_keyboard

        self._users.update_profile(user_id, ai_purchase_pending=True)
        text = (
            "☕ Consultas adicionales\n\n"
            f"Transferí ${self.min_pack_ars:,} ARS (mínimo) al alias:\n"
            f"{self.payment_alias}\n\n"
            "Enviá el comprobante en este chat (captura o PDF).\n"
            "Te acreditamos las consultas automáticamente en esta cuenta de Telegram.\n\n"
            "Las 5 consultas gratis vuelven mañana a las 00:01 (hora Argentina)."
        ).replace(",", ".")
        return text, upgrade_keyboard()

    def end_session(self, user_id: str) -> str:
        self._users.update_profile(
            user_id,
            ai_awaiting_prompt=False,
            ai_purchase_pending=False,
        )
        return "Sesión de IA cerrada. Usá los atajos del menú o /ask_ia cuando quieras."

    def _post_response_keyboard(self, profile: dict[str, Any]) -> dict:
        from src.services.ask_ia_ui import post_response_keyboard

        n = self.credits_available(profile)
        return post_response_keyboard(has_credits=n > 0)

    def handle_user_prompt(self, user_id: str, text: str) -> tuple[str, dict | None]:
        profile = self.ensure_daily_reset(user_id)
        if not profile.get("ai_awaiting_prompt"):
            return INVALID_COMMAND, None

        if self.credits_available(profile) <= 0:
            self._users.update_profile(user_id, ai_awaiting_prompt=False)
            return self._no_credits_message()

        if not self._invoke_agent:
            return (
                "El agente no está disponible en este entorno. Intentá más tarde.",
                None,
            )

        session_id = self._session_id(user_id, profile)
        prompt = (
            "Respondé en español rioplatense, breve, solo fútbol Mundial 2026.\n\n"
            f"{text.strip()}"
        )
        response = self._invoke_agent(user_id, session_id, prompt)
        if not response or not str(response).strip():
            self._users.update_profile(user_id, ai_awaiting_prompt=False)
            return (
                "No pude generar una respuesta. No se descontó una consulta. "
                "Probá de nuevo con /ask_ia.",
                None,
            )

        err_markers = (
            "Hubo un error",
            "No pude generar",
            "error procesando",
            "error temporal",
            "Sin permisos",
            "no está configurado",
        )
        if any(m in response for m in err_markers):
            self._users.update_profile(user_id, ai_awaiting_prompt=False)
            return response, self._post_response_keyboard(
                self._users.get_profile(user_id) or profile
            )

        self._consume_credit(user_id, profile)
        profile = self._users.get_profile(user_id) or profile
        remaining = self.credits_available(profile)
        self._users.update_profile(
            user_id,
            ai_awaiting_prompt=False,
            ai_session_id=session_id,
        )
        body = f"{response.strip()}\n\nConsultas restantes: {remaining}"
        return body, self._post_response_keyboard(profile)

    def callback(self, user_id: str, data: str) -> tuple[str, dict | None] | None:
        if data == "ia:more":
            profile = self.ensure_daily_reset(user_id)
            if self.credits_available(profile) <= 0:
                return self._no_credits_message()
            self._users.update_profile(user_id, ai_awaiting_prompt=True)
            n = self.credits_available(profile)
            return (
                f"Escribí tu siguiente pregunta ({n} consultas disponibles):",
                None,
            )
        if data == "ia:end":
            return self.end_session(user_id), None
        if data == "ia:upgrade":
            return self.request_upgrade(user_id)
        return None

    def _purchase_cooldown_active(self, profile: dict[str, Any]) -> bool:
        raw = profile.get("ai_last_auto_purchase_at")
        if not raw:
            return False
        try:
            last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return False
        delta = datetime.now(timezone.utc) - last.astimezone(timezone.utc)
        return delta < timedelta(hours=self.purchase_cooldown_h)

    def handle_purchase_proof(
        self, user_id: str, *, file_id: str, file_kind: str
    ) -> str:
        profile = self._users.get_profile(user_id) or {}
        if not profile.get("ai_purchase_pending"):
            return (
                "Para enviar un comprobante, primero tocá «☕ Más consultas» "
                "desde /ask_ia o el menú de créditos."
            )

        if self._purchase_cooldown_active(profile):
            return (
                "Ya procesamos un comprobante en las últimas 24 h.\n"
                "Si pagaste de nuevo y no se acreditó, contactá al administrador "
                "con /help."
            )

        bonus = int(profile.get("ai_bonus_credits") or 0) + self.pack_bonus
        now = datetime.now(timezone.utc).isoformat()
        alias = (profile.get("alias") or "jugador").strip()
        self._users.update_profile(
            user_id,
            ai_bonus_credits=bonus,
            ai_purchase_pending=False,
            ai_last_auto_purchase_at=now,
        )
        self._purchases.record_auto_purchase(
            user_id=user_id,
            alias=alias,
            credits_granted=self.pack_bonus,
            amount_ars=self.min_pack_ars,
            telegram_file_id=file_id,
            payment_alias=self.payment_alias,
        )
        profile = self.ensure_daily_reset(user_id)
        total = self.credits_available(profile)
        return (
            f"✅ Acreditamos {self.pack_bonus} consultas en tu cuenta (@{alias}).\n"
            f"Total disponible: {total}.\n"
            f"Usá /ask_ia cuando quieras."
        )

    def admin_grant(self, admin_id: str, alias: str, amount: int) -> str:
        from src.services.auth_service import AuthService

        if not AuthService().is_admin_global(admin_id):
            return "Solo el administrador puede usar este comando."

        target = self._users.resolve_alias(alias.strip())
        if not target:
            suggestions = self._users.find_alias_suggestions(alias, limit=3)
            hint = f" Sugerencias: {', '.join(suggestions)}." if suggestions else ""
            return f"No encontré usuario ACTIVE con alias «{alias}».{hint}"

        uid = target["user_id"]
        profile = self._users.get_profile(uid) or target
        bonus = int(profile.get("ai_bonus_credits") or 0) + int(amount)
        self._users.update_profile(uid, ai_bonus_credits=bonus)
        profile = self.ensure_daily_reset(uid)
        total = self.credits_available(profile)
        return (
            f"✅ +{amount} consultas bonus para @{profile.get('alias', alias)}.\n"
            f"Total disponible: {total}."
        )
