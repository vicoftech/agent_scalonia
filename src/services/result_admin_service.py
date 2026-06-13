"""Aprobación y publicación de resultados — SPEC-2026-051."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.result_dao import (
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    APPROVAL_SUPERSEDED,
    ResultDAO,
)
from src.models.match_result import MatchResult
from src.services.auth_service import AuthService
from src.services.result_admin_notify import ResultAdminNotifier
from src.services.result_gate import is_admin_gate_enabled
from src.services.result_queues import enqueue_scoring
from src.services.result_source_aggregator import (
    AggregatedCandidate,
    ResultSourceAggregator,
    assert_match_finished_for_result,
)
from src.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)

NOTIFY_DEBOUNCE_MINUTES = 15


@dataclass
class PublishOutcome:
    match_id: str
    published: bool = False
    republish: bool = False
    publish_version: int = 0
    notified_users: int = 0
    scoring_enqueued: bool = False
    errors: list[str] = field(default_factory=list)


class ResultAdminService:
    def __init__(
        self,
        *,
        results: ResultDAO | None = None,
        matches: MatchDAO | None = None,
        aggregator: ResultSourceAggregator | None = None,
        notifier: ResultAdminNotifier | None = None,
        scoring: ScoringService | None = None,
        auth: AuthService | None = None,
        result_service: Any | None = None,
        send_text: Callable[[int, str, dict | None], bool] | None = None,
    ):
        self._results = results or ResultDAO()
        self._matches = matches or MatchDAO()
        self._aggregator = aggregator or ResultSourceAggregator()
        self._notifier = notifier or ResultAdminNotifier()
        self._scoring = scoring or ScoringService()
        self._auth = auth or AuthService()
        self._result_service = result_service
        self._send_text = send_text

    def _svc(self):
        if self._result_service is None:
            from src.services.result_service import ResultService

            self._result_service = ResultService(
                result_dao=self._results,
                match_dao=self._matches,
            )
        return self._result_service

    def assert_admin(self, user_id: str) -> None:
        if not self._auth.is_admin_global(user_id):
            raise PermissionError("solo admin global")

    def propose_result(
        self,
        match_id: str,
        *,
        api_result: MatchResult | None = None,
        manual_result: MatchResult | None = None,
        force_notify: bool = False,
    ) -> AggregatedCandidate | None:
        match = self._matches.get_match(match_id)
        if not match:
            logger.warning("propose_result: match not found %s", match_id[:8])
            return None

        try:
            assert_match_finished_for_result(match, allow_sandbox=manual_result is not None)
        except ValueError as exc:
            logger.info("propose_result guard: %s", exc)
            return None

        if manual_result:
            candidate = AggregatedCandidate(
                match_id=match_id,
                proposed=manual_result,
                consensus_score=1.0,
                snapshots=[],
                warnings=["carga manual del operador"],
            )
        else:
            candidate = self._aggregator.aggregate(match, api_result=api_result)
            if not candidate:
                return None

        candidate.proposed.match_id = match_id
        existing = self._results.get_candidate_raw(match_id)
        if existing and existing.get("approval_status") == APPROVAL_REJECTED and not force_notify:
            logger.info("propose_result skip rejected match=%s", match_id[:8])
            return None

        if existing and not force_notify and not manual_result:
            if self._same_proposal(existing, candidate) and self._within_debounce(existing):
                logger.info("propose_result debounce match=%s", match_id[:8])
                return AggregatedCandidate(
                    match_id=match_id,
                    proposed=ResultDAO.candidate_proposed_result(existing) or candidate.proposed,
                    consensus_score=float(existing.get("consensus_score", 0)),
                    warnings=list(existing.get("warnings") or []),
                )

        self._results.save_candidate(
            match_id,
            proposed=candidate.proposed,
            consensus_score=candidate.consensus_score,
            source_snapshots=ResultDAO.snapshots_to_dynamo(candidate.snapshots),
            warnings=candidate.warnings,
            approval_status=APPROVAL_PENDING,
        )

        if force_notify or not existing or not self._within_debounce(existing):
            sent = self._notifier.notify_pending(
                match,
                candidate,
                send_text=self._send_text,
            )
            if sent:
                logger.info("propose_result notified admins match=%s sent=%s", match_id[:8], sent)

        return candidate

    def confirm_and_publish(
        self,
        match_id: str,
        admin_user_id: str,
        *,
        telegram_direct: bool = False,
    ) -> PublishOutcome:
        self.assert_admin(admin_user_id)
        cand = self._results.get_candidate_raw(match_id)
        if not cand or cand.get("approval_status") != APPROVAL_PENDING:
            return PublishOutcome(match_id=match_id, errors=["sin candidato pendiente"])
        proposed = ResultDAO.candidate_proposed_result(cand)
        if not proposed:
            return PublishOutcome(match_id=match_id, errors=["candidato inválido"])
        summary = self._source_summary(cand)
        return self._publish(
            match_id,
            proposed,
            admin_user_id,
            collection_source_summary=summary,
            telegram_direct=telegram_direct,
        )

    def publish_curated(
        self,
        match_id: str,
        result: MatchResult,
        admin_user_id: str,
        *,
        telegram_direct: bool = False,
        collection_source_summary: str = "admin_curated",
    ) -> PublishOutcome:
        self.assert_admin(admin_user_id)
        result.match_id = match_id
        return self._publish(
            match_id,
            result,
            admin_user_id,
            collection_source_summary=collection_source_summary,
            telegram_direct=telegram_direct,
        )

    def republish_result(
        self,
        match_id: str,
        result: MatchResult,
        admin_user_id: str,
        *,
        telegram_direct: bool = False,
    ) -> PublishOutcome:
        self.assert_admin(admin_user_id)
        if not self._results.has_scores(match_id):
            return self.publish_curated(
                match_id,
                result,
                admin_user_id,
                telegram_direct=telegram_direct,
                collection_source_summary="admin_republish",
            )

        reset_n = self._scoring.reset_match_scoring(match_id)
        logger.info("republish reset scoring match=%s rows=%s", match_id[:8], reset_n)

        prev_version = self._results.get_publish_version(match_id)
        result.match_id = match_id
        outcome = self._publish(
            match_id,
            result,
            admin_user_id,
            collection_source_summary="admin_republish",
            telegram_direct=telegram_direct,
            republish=True,
            publish_version=prev_version + 1,
            supersedes_version=prev_version,
        )
        outcome.republish = True
        return outcome

    def reject_candidate(
        self,
        match_id: str,
        admin_user_id: str,
        *,
        reason: str = "",
    ) -> None:
        self.assert_admin(admin_user_id)
        self._results.mark_candidate_status(
            match_id,
            APPROVAL_REJECTED,
            reviewed_by_user_id=admin_user_id,
        )
        if reason:
            logger.info("candidate rejected match=%s reason=%s", match_id[:8], reason[:80])

    def update_candidate_from_admin(
        self,
        match_id: str,
        result: MatchResult,
        admin_user_id: str,
    ) -> None:
        self.assert_admin(admin_user_id)
        result.match_id = match_id
        self._results.update_candidate_draft(match_id, result, edited_by_user_id=admin_user_id)

    def get_candidate_result(self, match_id: str) -> MatchResult | None:
        cand = self._results.get_candidate_raw(match_id)
        if not cand:
            return None
        return ResultDAO.candidate_proposed_result(cand)

    def _publish(
        self,
        match_id: str,
        result: MatchResult,
        admin_user_id: str,
        *,
        collection_source_summary: str,
        telegram_direct: bool = False,
        republish: bool = False,
        publish_version: int | None = None,
        supersedes_version: int | None = None,
    ) -> PublishOutcome:
        outcome = PublishOutcome(match_id=match_id, republish=republish)
        match = self._matches.get_match(match_id)
        if not match:
            outcome.errors.append("partido no encontrado")
            return outcome

        version = publish_version or (1 if not republish else self._results.get_publish_version(match_id) + 1)
        self._results.save_published_result(
            match_id,
            result,
            published_by_user_id=admin_user_id,
            collection_source_summary=collection_source_summary,
            publish_version=version,
            supersedes_version=supersedes_version,
        )
        self._results.mark_candidate_status(
            match_id,
            APPROVAL_SUPERSEDED,
            reviewed_by_user_id=admin_user_id,
        )
        self._matches.update_status(match_id, "FINISHED")

        svc = self._svc()
        notified = svc.notify_match_result(
            match_id,
            match,
            result,
            telegram_direct=telegram_direct,
            republish=republish,
        )
        outcome.notified_users = notified

        enqueued = enqueue_scoring(match_id, result.to_dict())
        if enqueued:
            outcome.scoring_enqueued = True
        else:
            logger.warning(
                "scoring queue unavailable; sync scoring match=%s",
                match_id[:8],
            )
            score_out = self._scoring.process_finish_match(
                match_id,
                result=result,
                force=republish,
            )
            outcome.scoring_enqueued = (
                score_out.scored > 0
                or (not score_out.already_processed and bool(score_out.rows))
            )
            if telegram_direct and score_out.scored > 0:
                self._scoring.notify_scoring_breakdowns(
                    match_id,
                    telegram_direct=True,
                )
        outcome.published = True
        outcome.publish_version = version
        return outcome

    @staticmethod
    def _source_summary(cand: dict[str, Any]) -> str:
        snaps = cand.get("source_snapshots") or []
        ids = [s.get("source_id", "?") for s in snaps if isinstance(s, dict)]
        if not ids:
            return "manual"
        tavily_n = sum(1 for i in ids if str(i).startswith("tavily"))
        parts = []
        if "api_football" in ids:
            parts.append("api_football")
        if tavily_n:
            parts.append(f"tavily({tavily_n})")
        return "+".join(parts) or "web"

    @staticmethod
    def _same_proposal(existing: dict[str, Any], candidate: AggregatedCandidate) -> bool:
        old = ResultDAO.candidate_proposed_result(existing)
        if not old:
            return False
        new = candidate.proposed
        return (
            old.home_goals == new.home_goals
            and old.away_goals == new.away_goals
            and old.mvp_name == new.mvp_name
            and old.var_used == new.var_used
            and old.goal_before_5min == new.goal_before_5min
        )

    @staticmethod
    def _within_debounce(existing: dict[str, Any]) -> bool:
        notified = existing.get("notified_at") or existing.get("proposed_at")
        if not notified:
            return False
        try:
            ts = datetime.fromisoformat(str(notified).replace("Z", "+00:00"))
        except ValueError:
            return False
        return datetime.now(tz=timezone.utc) - ts < timedelta(minutes=NOTIFY_DEBOUNCE_MINUTES)


def collect_or_propose(
    match_id: str,
    *,
    result_service: Any | None = None,
    api_result: MatchResult | None = None,
    manual_result: MatchResult | None = None,
    force_notify: bool = False,
    telegram_direct: bool = False,
) -> MatchResult | None:
    """Entry unificado: gate → propose; legacy → collect directo."""
    if is_admin_gate_enabled():
        admin = ResultAdminService(result_service=result_service)
        cand = admin.propose_result(
            match_id,
            api_result=api_result,
            manual_result=manual_result,
            force_notify=force_notify,
        )
        return cand.proposed if cand else None

    svc = result_service
    if svc is None:
        from src.services.result_service import ResultService

        svc = ResultService()
    if manual_result:
        return svc.apply_manual_result(
            match_id,
            manual_result.home_goals,
            manual_result.away_goals,
            mvp_name=manual_result.mvp_name,
            red_cards=manual_result.red_cards,
            goal_before_5min=manual_result.goal_before_5min,
            var_used=manual_result.var_used,
            free_kick_goal=manual_result.free_kick_goal,
            penalty_saved=manual_result.penalty_saved,
            penalty_scored=manual_result.penalty_scored,
            notify=True,
            telegram_direct=telegram_direct,
        )
    return svc.collect_result(match_id, telegram_direct=telegram_direct, force_notify=force_notify)
