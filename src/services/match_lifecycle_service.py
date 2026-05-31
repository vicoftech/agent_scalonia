"""Trivia reminders, veda — SPEC-032 / SPEC-021 (dev + Lambdas)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import os

from src.clients.telegram_client import get_bot_token, send_telegram_message
from src.services.result_queues import enqueue_lifecycle_notification
from src.dao.dynamo.group_dao import GroupDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.prediction_dao import PredictionDAO
from src.dao.dynamo.user_dao import UserDAO
from src.services.prediction_rules import VEDA_MINUTES_BEFORE_KICKOFF
from src.services.prediction_service import PredictionService

logger = logging.getLogger(__name__)

REMINDER_TEMPLATES: dict[int, str] = {
    1: (
        "⏰ Quedan ~60 min\n"
        "Todavía podés predecir {title}.\n"
        f"La veda cierra {VEDA_MINUTES_BEFORE_KICKOFF} min antes del kickoff."
    ),
    2: (
        "⚠️ Quedan ~30 min\n"
        "{title} empieza pronto.\n"
        "¡Última chance antes de la veda!"
    ),
    3: (
        "🔥 Quedan ~15 min\n"
        "{title} — la veda cierra en minutos.\n"
        "¡Predecí ahora!"
    ),
}


class MatchLifecycleService:
    def __init__(
        self,
        *,
        matches: MatchDAO | None = None,
        groups: GroupDAO | None = None,
        users: UserDAO | None = None,
        predictions: PredictionDAO | None = None,
        prediction_svc: PredictionService | None = None,
    ) -> None:
        self._matches = matches or MatchDAO()
        self._groups = groups or GroupDAO()
        self._users = users or UserDAO()
        self._predictions = predictions or PredictionDAO()
        self._pred = prediction_svc or PredictionService(
            group_dao=self._groups,
            user_dao=self._users,
            prediction_dao=self._predictions,
            match_dao=self._matches,
        )

    def send_match_reminders(
        self,
        match_id: str,
        reminder_tier: int,
        *,
        telegram_direct: bool = False,
        sandbox: bool = False,
    ) -> dict[str, Any]:
        if reminder_tier not in REMINDER_TEMPLATES:
            return {"status": "ERROR", "error": f"reminder_tier invalid: {reminder_tier}"}

        match = self._matches.get_match(match_id)
        if not match:
            return {"status": "NOT_FOUND", "match_id": match_id}

        title = self._pred.format_match_title(match)
        body_tpl = REMINDER_TEMPLATES[reminder_tier]
        message = body_tpl.format(title=title)

        if sandbox:
            by_user = self._all_notify_users()
            recipients = [(uid, gids[0]) for uid, gids in by_user.items() if gids]
        else:
            recipients = self._users_without_prediction_in_active_group(match_id)
        sent = 0
        skipped = 0
        errors = 0

        use_queue = not telegram_direct and bool(
            os.environ.get("NOTIFICATION_QUEUE_URL", "").strip()
        )

        if not telegram_direct and not use_queue:
            return {
                "status": "OK",
                "dry_delivery": True,
                "tier": reminder_tier,
                "would_send": len(recipients),
                "recipients": [u[:8] for u, _ in recipients],
                "hint": "Configurá NOTIFICATION_QUEUE_URL o telegram_direct=True.",
            }

        for user_id, gid in recipients:
            profile = self._users.get_profile(user_id) or {}
            if profile.get("notifications_enabled") is False:
                skipped += 1
                continue
            if profile.get("tg_chat_id") is None:
                skipped += 1
                continue
            try:
                if use_queue:
                    ok = enqueue_lifecycle_notification(
                        user_id=user_id,
                        match_id=match_id,
                        message=message,
                        msg_type="MATCH_REMINDER",
                        group_id=gid,
                    )
                    if ok:
                        sent += 1
                    else:
                        errors += 1
                else:
                    token = get_bot_token()
                    send_telegram_message(int(profile["tg_chat_id"]), message, token)
                    sent += 1
            except Exception:
                logger.exception(
                    "reminder send failed user=%s tier=%s", user_id[:8], reminder_tier
                )
                errors += 1

        return {
            "status": "OK",
            "tier": reminder_tier,
            "sent": sent,
            "skipped": skipped,
            "errors": errors,
            "eligible": len(recipients),
            "delivery": "queue" if use_queue else "telegram_direct",
        }

    def activate_veda(
        self,
        match_id: str,
        *,
        telegram_direct: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        match = self._matches.get_match(match_id)
        if not match:
            return {"status": "NOT_FOUND", "match_id": match_id}

        already = bool(match.get("veda_active"))
        if already and not force:
            return {"status": "ALREADY_ACTIVE", "match_id": match_id}

        if force and already:
            self._matches.set_veda_active(match_id, active=False)

        self._matches.set_veda_active(match_id, active=True)
        match = self._matches.get_match(match_id) or match

        by_user = self._all_notify_users()
        title = self._pred.format_match_title(match)
        kickoff_line = self._kickoff_countdown_line(match)

        use_queue = not telegram_direct and bool(
            os.environ.get("NOTIFICATION_QUEUE_URL", "").strip()
        )

        if not telegram_direct and not use_queue:
            return {
                "status": "OK",
                "veda_active": True,
                "dry_delivery": True,
                "would_notify": len(by_user),
                "hint": "Configurá NOTIFICATION_QUEUE_URL o telegram_direct=True.",
            }

        sent = skipped = errors = 0
        for user_id, group_ids in by_user.items():
            profile = self._users.get_profile(user_id) or {}
            if profile.get("notifications_enabled") is False or profile.get("tg_chat_id") is None:
                skipped += 1
                continue
            gid = group_ids[0]
            pred = self._predictions.get_active(user_id, match_id, gid)
            if pred:
                pred_line = (
                    f"Tu predicción: {pred['home_goals']}-{pred['away_goals']} "
                    f"está guardada ✅"
                )
            else:
                pred_line = "No tenías predicción para este partido ⚠️"
            text = (
                "🎰 ¡NO VA MÁS!\n"
                f"La veda para {title} está activa\n"
                f"{kickoff_line}\n\n"
                f"{pred_line}"
            )
            try:
                if use_queue:
                    ok = enqueue_lifecycle_notification(
                        user_id=user_id,
                        match_id=match_id,
                        message=text,
                        msg_type="MATCH_VEDA",
                        group_id=gid,
                    )
                    if ok:
                        sent += 1
                    else:
                        errors += 1
                else:
                    token = get_bot_token()
                    send_telegram_message(int(profile["tg_chat_id"]), text, token)
                    sent += 1
            except Exception:
                logger.exception("veda notify failed user=%s", user_id[:8])
                errors += 1

        return {
            "status": "OK",
            "veda_active": True,
            "sent": sent,
            "skipped": skipped,
            "errors": errors,
            "delivery": "queue" if use_queue else "telegram_direct",
        }

    def _users_without_prediction_in_active_group(
        self, match_id: str
    ) -> list[tuple[str, str]]:
        seen: set[str] = set()
        out: list[tuple[str, str]] = []
        for group in self._groups.list_groups_for_broadcast():
            gid = str(group.get("group_id") or "")
            if not gid:
                continue
            for user_id in self._groups.list_member_user_ids(gid):
                if user_id in seen:
                    continue
                active_gid = self._pred.get_active_group_id(user_id)
                if active_gid != gid:
                    continue
                if self._predictions.get_active(user_id, match_id, gid):
                    continue
                seen.add(user_id)
                out.append((user_id, gid))
        return out

    def _all_notify_users(self) -> dict[str, list[str]]:
        by_user: dict[str, list[str]] = {}
        for group in self._groups.list_groups_for_broadcast():
            gid = group.get("group_id")
            if not gid:
                continue
            for user_id in self._groups.list_member_user_ids(gid):
                if gid not in by_user.setdefault(user_id, []):
                    by_user[user_id].append(gid)
        return by_user

    def _kickoff_countdown_line(self, match: dict[str, Any]) -> str:
        raw = match.get("kickoff_utc")
        if not raw:
            return "El partido empieza pronto."
        try:
            kickoff = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return "El partido empieza pronto."
        delta = kickoff - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "El partido ya empezó o está por empezar."
        mins = max(1, int(delta.total_seconds() // 60))
        return f"El partido empieza en {mins} minutos"
