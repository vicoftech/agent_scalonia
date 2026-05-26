"""Procesa FINISH_MATCH: puntúa predicciones ACTIVE y marca result_processed."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.dao.dynamo.group_dao import GroupDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.prediction_dao import PredictionDAO, STATUS_ACTIVE, STATUS_SCORED
from src.dao.dynamo.result_dao import ResultDAO
from src.dao.dynamo.user_dao import UserDAO
from src.models.match_result import MatchResult
from src.scoring.scoring_engine import PointsResult, calculate_points
from src.scoring.scoring_extended import extended_points, ko_playoff_points, normalize_phase
from src.services.prediction_result_report import actual_score_from_result

logger = logging.getLogger(__name__)


@dataclass
class PredictionScoreRow:
    user_id: str
    group_id: str
    points: int
    base_points: int
    extended_points: int
    ko_points: int
    reason: str
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class ScoringOutcome:
    match_id: str
    scored: int = 0
    skipped: int = 0
    already_processed: bool = False
    rows: list[PredictionScoreRow] = field(default_factory=list)


class ScoringService:
    def __init__(
        self,
        *,
        results: ResultDAO | None = None,
        predictions: PredictionDAO | None = None,
        matches: MatchDAO | None = None,
        users: UserDAO | None = None,
        groups: GroupDAO | None = None,
    ):
        self._results = results or ResultDAO()
        self._preds = predictions or PredictionDAO()
        self._matches = matches or MatchDAO()
        self._users = users or UserDAO()
        self._groups = groups or GroupDAO()

    def process_finish_match(
        self,
        match_id: str,
        *,
        result: MatchResult | dict[str, Any] | None = None,
        force: bool = False,
    ) -> ScoringOutcome:
        """
        Puntúa todas las predicciones ACTIVE del partido.
        Idempotente: si result_processed y no force → no hace nada.
        """
        outcome = ScoringOutcome(match_id=match_id)

        if self._results.is_scoring_done(match_id) and not force:
            outcome.already_processed = True
            logger.info("Scoring ya procesado match=%s", match_id[:8])
            return outcome

        match = self._matches.get_match(match_id)
        if not match:
            logger.warning("Scoring: partido no encontrado %s", match_id[:8])
            return outcome

        if result is None:
            loaded = self._results.get_result(match_id)
            if not loaded:
                logger.warning("Scoring: sin RESULT match=%s", match_id[:8])
                return outcome
            result = loaded
        elif isinstance(result, dict):
            result = MatchResult.from_dynamo({**result, "match_id": match_id})

        raw_result = self._results.get_raw(match_id) or result.to_dict()
        ah, aa = actual_score_from_result(match, raw_result)
        phase = normalize_phase(match.get("phase") or result.phase)

        predictions = self._preds.get_predictions_for_match(match_id)
        if not predictions:
            logger.info("Scoring: sin predicciones ACTIVE match=%s", match_id[:8])
            self._results.mark_result_processed(match_id)
            outcome.already_processed = True
            return outcome

        for pred in predictions:
            row = self._score_one(pred, match, result, ah, aa, phase)
            outcome.rows.append(row)
            if row.skipped:
                outcome.skipped += 1
                continue
            applied = self._preds.mark_scored(
                pred["user_id"],
                match_id,
                pred["group_id"],
                points=row.points,
                scoring_reason=row.reason,
                scoring_detail={
                    "base_points": row.base_points,
                    "extended_points": row.extended_points,
                    "ko_points": row.ko_points,
                    "actual_home": ah,
                    "actual_away": aa,
                },
            )
            if applied:
                self._users.add_match_points(pred["user_id"], row.points)
                outcome.scored += 1
            else:
                outcome.skipped += 1

        self._results.mark_result_processed(match_id)
        logger.info(
            "Scoring match #%s: scored=%s skipped=%s",
            match.get("match_number"),
            outcome.scored,
            outcome.skipped,
        )
        return outcome

    def reset_match_scoring(self, match_id: str) -> int:
        """Quita puntuación del partido para volver a probar (dev)."""
        reset = 0
        items = self._preds.list_predictions_for_match(
            match_id, statuses=(STATUS_SCORED, STATUS_ACTIVE)
        )
        for pred in items:
            if pred.get("status") != STATUS_SCORED:
                continue
            pts = int(pred.get("points_earned") or 0)
            if pts:
                self._users.add_match_points(pred["user_id"], -pts)
            self._preds.reset_to_active(
                pred["user_id"], match_id, pred["group_id"]
            )
            reset += 1
        if self._results.get_raw(match_id):
            self._results.clear_result_processed(match_id)
        return reset

    def _score_one(
        self,
        pred: dict[str, Any],
        match: dict[str, Any],
        result: MatchResult,
        actual_home: int,
        actual_away: int,
        phase: str,
    ) -> PredictionScoreRow:
        user_id = pred["user_id"]
        group_id = pred["group_id"]
        ph, pa = int(pred["home_goals"]), int(pred["away_goals"])

        base: PointsResult = calculate_points(
            ph, pa, actual_home, actual_away, phase  # type: ignore[arg-type]
        )
        ext_pts, _ = extended_points(pred, result)
        ko_pts, _ = ko_playoff_points(pred, result, phase)
        total = base.points + ext_pts + ko_pts

        return PredictionScoreRow(
            user_id=user_id,
            group_id=group_id,
            points=total,
            base_points=base.points,
            extended_points=ext_pts,
            ko_points=ko_pts,
            reason=base.reason,
        )

    def process_sqs_payload(self, payload: dict[str, Any]) -> ScoringOutcome | None:
        if payload.get("event_type") != "FINISH_MATCH":
            logger.info("Scoring skip event_type=%s", payload.get("event_type"))
            return None
        match_id = payload.get("match_id")
        if not match_id:
            return None
        result_data = payload.get("result")
        result = MatchResult.from_dynamo(result_data) if isinstance(result_data, dict) else None
        return self.process_finish_match(match_id, result=result)
