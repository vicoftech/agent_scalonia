"""Servicio de recolección de resultados — SPEC-2026-031."""
from __future__ import annotations

import logging
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

ESTIMATED_MATCH_MINUTES = 110

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

    def collect_result(self, match_id: str) -> MatchResult | None:
        existing = self._results.get_result(match_id)
        if existing and existing.mvp_name:
            return existing

        if existing and self._results.has_scores(match_id):
            enriched = self._enrich_mvp(match_id, existing)
            if enriched.mvp_name and not existing.mvp_name:
                self._results.update_mvp(match_id, enriched.mvp_name)
            if not self._results.is_scoring_done(match_id):
                match = self._matches.get_match(match_id)
                if match:
                    enqueue_scoring(match_id, enriched.to_dict())
                    self._notify_all_groups(match_id, match, enriched)
            return enriched

        match = self._matches.get_match(match_id)
        if not match:
            logger.warning("collect_result: match not found %s", match_id[:8])
            return None

        fetched = self._fetch_via_web_search(match)
        if not fetched:
            return None

        saved = self._save_and_notify(match_id, match, fetched)
        return saved or fetched

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
        if datetime.now(tz=timezone.utc) < estimated_end:
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
            return MatchResult(
                home_goals=existing.home_goals,
                away_goals=existing.away_goals,
                phase=existing.phase,
                playoff_via=existing.playoff_via,
                playoff_winner=existing.playoff_winner,
                home_goals_aet=existing.home_goals_aet,
                away_goals_aet=existing.away_goals_aet,
                scorers=existing.scorers,
                red_cards=existing.red_cards,
                mvp_name=mvp,
                status=existing.status,
                source=existing.source,
                result_processed=existing.result_processed,
                match_id=match_id,
                recorded_at=existing.recorded_at,
            )
        return existing

    def _save_and_notify(
        self,
        match_id: str,
        match: dict[str, Any],
        result: MatchResult,
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
            self._notify_all_groups(match_id, match, result)
            enqueue_scoring(match_id, result.to_dict())

        return self._results.get_result(match_id) or result

    def _notify_all_groups(
        self,
        match_id: str,
        match: dict[str, Any],
        result: MatchResult,
    ) -> int:
        message = format_match_result_message(match, result)
        group_ids = self._preds.get_group_ids_with_predictions(match_id)
        sent = 0
        for group_id in group_ids:
            group = self._groups.get_group(group_id) or {}
            for user_id in self._groups.list_member_user_ids(group_id):
                profile = self._users.get_profile(user_id) or {}
                if profile.get("notifications_enabled") is False:
                    continue
                preds = self._preds.get_predictions_for_match(match_id)
                if not any(
                    p["user_id"] == user_id and p.get("group_id") == group_id
                    for p in preds
                ):
                    continue
                if enqueue_match_result_notification(
                    user_id=user_id,
                    match_id=match_id,
                    group_id=group_id,
                    message=message,
                    match_info=match,
                    result=result.to_dict(),
                ):
                    sent += 1
                else:
                    logger.info(
                        "MATCH_RESULT notify (no queue) user=%s group=%s #%s",
                        user_id[:8],
                        group.get("name", group_id),
                        match.get("match_number"),
                    )
                    sent += 1
        return sent
