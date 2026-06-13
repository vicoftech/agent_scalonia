"""Notificación Telegram a admins — borrador de resultado SPEC-2026-051."""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from src.dao.dynamo.user_dao import UserDAO
from src.models.match_result import MatchResult
from src.services.prediction_rules import bool_label
from src.services.result_notification import MATCH_EVENT_LINES
from src.services.team_flags import format_team
from src.services.result_source_aggregator import AggregatedCandidate

logger = logging.getLogger(__name__)

# step 0 = marcador; resto = extendidas (SI/NO); red_cards: SI→1, NO→0
WIZARD_STEPS: tuple[tuple[str, str], ...] = (
    ("score", "marcador"),
    ("goal_before_5min", "Gol antes del 5'"),
    ("var_used", "Intervención VAR"),
    ("free_kick_goal", "Gol de tiro libre"),
    ("penalty_saved", "Penal atajado"),
    ("penalty_scored", "Penal convertido"),
    ("red_cards", "¿Hubo tarjetas rojas?"),
)

_send_text_fn: Callable[[int, str, dict | None], bool] | None = None


def set_send_text_fn(fn: Callable[[int, str, dict | None], bool] | None) -> None:
    global _send_text_fn
    _send_text_fn = fn


def pending_result_keyboard(match_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✏️ Ingresar resultado",
                    "callback_data": f"res:pub:wizard:{match_id}",
                },
            ],
            [
                {
                    "text": "🔄 Re-recolectar",
                    "callback_data": f"res:pub:recolect:{match_id}",
                },
                {
                    "text": "❌ Rechazar",
                    "callback_data": f"res:pub:reject:{match_id}",
                },
            ],
        ]
    }


def publish_confirm_keyboard(match_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Publicar",
                    "callback_data": f"res:pub:publish:{match_id}",
                },
                {
                    "text": "❌ Cancelar",
                    "callback_data": f"res:pub:cancel:{match_id}",
                },
            ],
        ]
    }


def wizard_prompt_for_step(match: dict[str, Any], step_idx: int) -> str:
    home = format_team(match["home_team"])
    away = format_team(match["away_team"])
    num = match.get("match_number", "?")
    header = f"Partido #{num} — {home} vs {away}"

    if step_idx <= 0 or step_idx >= len(WIZARD_STEPS):
        return f"{header}\n\nIngresá el resultado (ej. 2-0):"

    _field, label = WIZARD_STEPS[step_idx]
    return f"{header}\n\n{label}\nRespondé SI o NO:"


def format_admin_result_detail_lines(result: MatchResult) -> list[str]:
    """Resumen extendido para admin (sin MVP)."""
    lines = ["", "Extendidas:"]
    for attr, label in MATCH_EVENT_LINES:
        lines.append(f"  {label}: {bool_label(getattr(result, attr, None))}")
    lines.append(f"  Expulsiones (total): {result.red_cards}")
    return lines


def format_admin_pending_message(
    match: dict[str, Any],
    candidate: AggregatedCandidate,
) -> str:
    result = candidate.proposed
    home = format_team(match["home_team"])
    away = format_team(match["away_team"])
    num = match.get("match_number", "?")
    pct = int(candidate.consensus_score * 100)
    sources = ", ".join(s.source_id for s in candidate.snapshots[:5]) or "sin fuentes"

    lines = [
        f"📋 RESULTADO PENDIENTE — Partido #{num}",
        f"{home}  {result.home_goals} - {result.away_goals}  {away}",
        "",
        f"Propuesta automática: {result.home_goals}-{result.away_goals}  (consenso {pct}%)",
        f"Fuentes: {sources}",
        "",
        "Revisá y cargá el resultado manual con el botón de abajo.",
    ]
    if candidate.warnings:
        lines.append("")
        lines.append("⚠️ Advertencias:")
        for w in candidate.warnings:
            lines.append(f"  • {w}")
    if candidate.consensus_score < 0.5:
        lines.append("")
        lines.append("🔴 ATENCIÓN: consenso bajo — revisar antes de publicar.")
    return "\n".join(lines)


def format_admin_preview_message(
    match: dict[str, Any],
    result: MatchResult,
    *,
    republish: bool = False,
) -> str:
    prefix = "🔄 REPUBLICAR — " if republish else "📋 VISTA PREVIA — "
    home = format_team(match["home_team"])
    away = format_team(match["away_team"])
    lines = [
        f"{prefix}Partido #{match.get('match_number', '?')}",
        f"{home}  {result.home_goals} - {result.away_goals}  {away}",
    ]
    lines.extend(format_admin_result_detail_lines(result))
    lines.append("")
    lines.append("Confirmá con el botón Publicar.")
    return "\n".join(lines)


class ResultAdminNotifier:
    def __init__(self, users: UserDAO | None = None):
        self._users = users or UserDAO()

    def _admin_targets(self) -> list[dict[str, Any]]:
        targets = self._users.list_admin_telegram_targets()
        if targets:
            return targets
        raw = (os.environ.get("TELEGRAM_ADMIN_CHAT_IDS") or "").strip()
        if not raw:
            return []
        out: list[dict[str, Any]] = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(
                    {
                        "user_id": "env-admin",
                        "tg_chat_id": int(part),
                        "alias": "admin",
                    }
                )
        return out

    def notify_pending(
        self,
        match: dict[str, Any],
        candidate: AggregatedCandidate,
        *,
        send_text: Callable[[int, str, dict | None], bool] | None = None,
    ) -> int:
        targets = self._admin_targets()
        if not targets:
            logger.warning("result_admin notify skipped: no admin targets")
            return 0

        message = format_admin_pending_message(match, candidate)
        markup = pending_result_keyboard(candidate.match_id)
        sender = send_text or _send_text_fn or _default_send_text
        if not sender:
            logger.warning("result_admin notify skipped: no send_text fn")
            return 0

        sent = 0
        for admin in targets:
            chat_id = int(admin["tg_chat_id"])
            try:
                if sender(chat_id, message[:4096], markup):
                    sent += 1
            except Exception:
                logger.exception(
                    "result_admin notify failed admin=%s",
                    str(admin.get("user_id", ""))[:8],
                )
        return sent


def _default_send_text(chat_id: int, text: str, markup: dict | None) -> bool:
    try:
        from src.clients.telegram_client import get_bot_token, send_telegram_message

        send_telegram_message(int(chat_id), text, get_bot_token(), reply_markup=markup)
        return True
    except Exception:
        logger.exception("result_admin default send failed chat=%s", chat_id)
        return False
