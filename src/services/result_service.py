"""Servicio de recolección de resultados — SPEC-2026-031."""
from __future__ import annotations

import logging
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from src.dao.dynamo.group_dao import GroupDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.prediction_dao import PredictionDAO
from src.dao.dynamo.result_dao import ResultDAO
from src.dao.dynamo.user_dao import UserDAO
from src.models.match_result import MatchResult
from src.services.result_notification import format_match_result_message
from src.services.result_parser import extract_mvp_from_text, parse_web_result
from src.services.result_queues import (
    enqueue_match_result_notification,
    enqueue_scoring,
)

logger = logging.getLogger(__name__)

ESTIMATED_MATCH_MINUTES = 130

_web_search_fn: Optional[Callable[[str], Optional[str]]] = None


def set_web_search_fn(fn: Optional[Callable[[str], Optional[str]]]) -> None:
    global _web_search_fn
    _web_search_fn = fn


def _default_web_search(query: str) -> Optional[str]:
    from src.web.tavily_search import perform_web_search

    return perform_web_search(query)


def _match_status_from_result(result: MatchResult) -> str:
    return "FINISHED"


class ResultService:
    def __init__(
        self,
        *,
        result_dao: ResultDAO | None = None,
        match_dao: MatchDAO | None = None,
        prediction_dao: PredictionDAO | None = None,
        group_dao: GroupDAO | None = None,
        user_dao: UserDAO | None = None,
    ):
        self._results = result_dao or ResultDAO()
        self._matches = match_dao or MatchDAO()
        self._preds = prediction_dao or PredictionDAO()
        self._groups = group_dao or GroupDAO()
        self._users = user_dao or UserDAO()

    def collect_result(
        self,
        match_id: str,
        *,
        telegram_direct: bool = False,
        force_notify: bool = False,
    ) -> MatchResult | None:
        existing = self._results.get_result(match_id)
        if existing and existing.mvp_name and not force_notify:
            return existing

        if existing and self._results.has_scores(match_id):
            enriched = self._enrich_mvp(match_id, existing)
            if enriched.mvp_name and not existing.mvp_name:
                self._results.update_mvp(match_id, enriched.mvp_name)
            should_notify = force_notify or not self._results.is_scoring_done(
                match_id
            )
            if should_notify:
                match = self._matches.get_match(match_id)
                if match:
                    if not self._results.is_scoring_done(match_id):
                        enqueue_scoring(match_id, enriched.to_dict())
                    sent = self._notify_all_groups(
                        match_id,
                        match,
                        enriched,
                        telegram_direct=telegram_direct,
                    )
                    if sent == 0:
                        logger.warning(
                            "Sin notificaciones enviadas match=%s "
                            "(¿NOTIFICATION_QUEUE_URL, --telegram-direct, "
                            "o usuarios sin tg_chat_id?)",
                            match_id[:8],
                        )
            return enriched

        match = self._matches.get_match(match_id)
        if not match:
            logger.warning("collect_result: match not found %s", match_id[:8])
            return None

        fetched = self._fetch_via_web_search(match)
        if not fetched:
            return None

        saved = self._save_and_notify(
            match_id, match, fetched, telegram_direct=telegram_direct
        )
        return saved or fetched

    def apply_manual_result(
        self,
        match_id: str,
        home_goals: int,
        away_goals: int,
        *,
        mvp_name: str | None = None,
        red_cards: int = 0,
        goal_before_5min: bool | None = None,
        var_used: bool | None = None,
        free_kick_goal: bool | None = None,
        penalty_saved: bool | None = None,
        penalty_scored: bool | None = None,
        replace: bool = True,
        notify: bool = True,
        telegram_direct: bool = False,
    ) -> MatchResult | None:
        """
        Carga manual de resultado (pruebas / operador).
        replace=True borra RESULT previo y re-dispara notify + scoring.
        """
        match = self._matches.get_match(match_id)
        if not match:
            logger.warning("apply_manual_result: match not found %s", match_id[:8])
            return None

        if replace and self._results.has_scores(match_id):
            self._results.delete_result(match_id)

        result = MatchResult(
            home_goals=home_goals,
            away_goals=away_goals,
            phase=match.get("phase", "GROUP"),
            mvp_name=mvp_name,
            red_cards=red_cards,
            goal_before_5min=goal_before_5min,
            var_used=var_used,
            free_kick_goal=free_kick_goal,
            penalty_saved=penalty_saved,
            penalty_scored=penalty_scored,
            source="web_search",
        )
        if not notify:
            self._results.save_result(match_id, result, allow_overwrite=replace)
            self._matches.update_status(match_id, _match_status_from_result(result))
            return self._results.get_result(match_id) or result

        return self._save_and_notify(
            match_id, match, result, telegram_direct=telegram_direct
        )

    def find_incomplete_match_ids(self) -> list[str]:
        """Partidos que debieron terminar y aún no tienen resultado completo (sin MVP)."""
        ids: list[str] = []
        for m in self._matches.list_matches_estimated_finished():
            mid = m["match_id"]
            if not self._results.is_complete(mid):
                ids.append(mid)
        return ids

    def _fetch_via_web_search(self, match: dict[str, Any]) -> MatchResult | None:
        home = match["home_team"]
        away = match["away_team"]
        kickoff_raw = match.get("kickoff_utc") or ""
        if not kickoff_raw:
            return None
        kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
        estimated_end = kickoff + timedelta(minutes=ESTIMATED_MATCH_MINUTES)
        skip_kickoff = os.environ.get("RESULT_SKIP_KICKOFF_CHECK", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not skip_kickoff and datetime.now(tz=timezone.utc) < estimated_end:
            logger.info("Partido %s vs %s aún en curso", home, away)
            return None

        query = f"{home} vs {away} resultado final Copa Mundial 2026"
        search = _web_search_fn or _default_web_search
        raw = search(query)
        if not raw:
            return None
        return parse_web_result(raw, match)

    def _enrich_mvp(self, match_id: str, existing: MatchResult) -> MatchResult:
        match = self._matches.get_match(match_id)
        if not match:
            return existing
        query = (
            f"jugador del partido {match['home_team']} vs {match['away_team']} "
            "Copa Mundial 2026 MVP"
        )
        search = _web_search_fn or _default_web_search
        raw = search(query)
        if not raw:
            return existing
        mvp = extract_mvp_from_text(raw)
        if mvp:
            return replace(existing, mvp_name=mvp, match_id=match_id)
        return existing

    def _save_and_notify(
        self,
        match_id: str,
        match: dict[str, Any],
        result: MatchResult,
        *,
        telegram_direct: bool = False,
    ) -> MatchResult | None:
        result.match_id = match_id
        already_scored = self._results.is_scoring_done(match_id)

        created = self._results.save_result(match_id, result)
        if not created:
            existing = self._results.get_result(match_id)
            if existing:
                return existing
            return None

        self._matches.update_status(match_id, _match_status_from_result(result))

        if not already_scored:
            self._notify_all_groups(
                match_id, match, result, telegram_direct=telegram_direct
            )
            enqueue_scoring(match_id, result.to_dict())

        return self._results.get_result(match_id) or result

    def _notify_recipients_by_user(self) -> dict[str, list[str]]:
        """
        user_id → group_ids ACTIVE donde es miembro.
        Un solo envío Telegram por usuario (opción A).
        """
        by_user: dict[str, list[str]] = {}
        for group in self._groups.list_groups_for_broadcast():
            gid = group.get("group_id")
            if not gid:
                continue
            for user_id in self._groups.list_member_user_ids(gid):
                if gid not in by_user.setdefault(user_id, []):
                    by_user[user_id].append(gid)
        return by_user

    def _notify_all_groups(
        self,
        match_id: str,
        match: dict[str, Any],
        result: MatchResult,
        *,
        telegram_direct: bool = False,
    ) -> int:
        """Notifica el resultado: un mensaje Telegram por usuario (miembros ACTIVE)."""
        by_user = self._notify_recipients_by_user()

        if not by_user:
            logger.warning(
                "Sin grupos ACTIVE con miembros — no hay notificaciones match #%s",
                match.get("match_number"),
            )
            return 0

        dispatcher = None
        if telegram_direct:
            from src.services.match_notify_dispatcher import MatchNotifyDispatcher

            dispatcher = MatchNotifyDispatcher(users=self._users)

        sent = 0
        skipped = 0
        for user_id, group_ids in by_user.items():
            profile = self._users.get_profile(user_id) or {}
            if profile.get("notifications_enabled") is False:
                skipped += 1
                continue
            if not profile.get("tg_chat_id"):
                logger.warning(
                    "Usuario %s sin tg_chat_id — no se puede enviar Telegram",
                    user_id[:8],
                )
                skipped += 1
                continue

            message = format_match_result_message(match, result)
            primary_gid = group_ids[0]
            payload = {
                "type": "MATCH_RESULT",
                "user_id": user_id,
                "match_id": match_id,
                "group_id": primary_gid,
                "group_ids": group_ids,
                "message": message,
                "result": result.to_dict(),
                "match_info": match,
            }

            if telegram_direct and dispatcher:
                outcome = dispatcher.dispatch_payload(payload)
                if outcome == "SENT":
                    sent += 1
                    logger.info(
                        "Telegram enviado user=%s groups=%s #%s",
                        user_id[:8],
                        len(group_ids),
                        match.get("match_number"),
                    )
                else:
                    skipped += 1
                    logger.warning(
                        "Telegram no enviado user=%s outcome=%s",
                        user_id[:8],
                        outcome,
                    )
            elif enqueue_match_result_notification(
                user_id=user_id,
                match_id=match_id,
                group_id=primary_gid,
                message=message,
                match_info=match,
                result=result.to_dict(),
                group_ids=group_ids,
            ):
                sent += 1
            else:
                skipped += 1

        if skipped and not telegram_direct:
            logger.warning(
                "Algunas notificaciones no se encolaron. "
                "Definí NOTIFICATION_QUEUE_URL o usá --telegram-direct"
            )
        logger.info(
            "Notify match #%s: sent=%s skipped=%s users=%s mode=%s",
            match.get("match_number"),
            sent,
            skipped,
            len(by_user),
            "telegram" if telegram_direct else "sqs",
        )
        return sent
