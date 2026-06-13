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

_send_text_fn: Callable[[int, str, dict | None], bool] | None = None


def set_send_text_fn(fn: Callable[[int, str, dict | None], bool] | None) -> None:
    global _send_text_fn
    _send_text_fn = fn


def pending_result_keyboard(match_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Confirmar y publicar",
                    "callback_data": f"res:pub:confirm:{match_id}",
                },
            ],
            [
                {
                    "text": "✏️ Editar",
                    "callback_data": f"res:pub:edit:{match_id}",
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


def edit_extended_keyboard(match_id: str) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    codes = {
        "goal_before_5min": "gb5",
        "var_used": "var",
        "free_kick_goal": "fk",
        "penalty_saved": "psv",
        "penalty_scored": "psc",
    }
    for attr, code in codes.items():
        label = next(l for a, l in MATCH_EVENT_LINES if a == attr)
        rows.append(
            [
                {
                    "text": f"{label}: Sí",
                    "callback_data": f"res:ext:{match_id}:{code}:1",
                },
                {
                    "text": "No",
                    "callback_data": f"res:ext:{match_id}:{code}:0",
                },
                {
                    "text": "—",
                    "callback_data": f"res:ext:{match_id}:{code}:n",
                },
            ]
        )
    rows.append(
        [
            {
                "text": "📋 Vista previa y publicar",
                "callback_data": f"res:pub:preview:{match_id}",
            },
        ]
    )
    rows.append(
        [
            {
                "text": "← Volver",
                "callback_data": f"res:pub:back:{match_id}",
            },
        ]
    )
    return {"inline_keyboard": rows}


def edit_score_keyboard(match_id: str) -> dict[str, Any]:
    scores = ["0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2", "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"]
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for sc in scores:
        h, a = sc.split("-")
        row.append(
            {
                "text": sc,
                "callback_data": f"res:scr:{match_id}:{h}:{a}",
            }
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            {
                "text": "Siguiente: extendidas →",
                "callback_data": f"res:pub:editext:{match_id}",
            },
        ]
    )
    return {"inline_keyboard": rows}


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
        f"Marcador 90': {result.home_goals}-{result.away_goals}  (consenso {pct}%)",
        f"Fuentes: {sources}",
        "",
        "Extendidas propuestas:",
    ]
    for attr, label in MATCH_EVENT_LINES:
        lines.append(f"  {label}: {bool_label(getattr(result, attr, None))}")
    lines.append(f"  Expulsiones: {result.red_cards}")
    lines.append("")
    lines.append(f"⭐ MVP: {result.mvp_name or '—'}")
    lines.append("")
    lines.append("⚠️ Advertencias:")
    if candidate.warnings:
        for w in candidate.warnings:
            lines.append(f"  • {w}")
    else:
        lines.append("  • Ninguna")
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
        f"MVP: {result.mvp_name or '—'}",
        f"VAR: {bool_label(result.var_used)}",
    ]
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
