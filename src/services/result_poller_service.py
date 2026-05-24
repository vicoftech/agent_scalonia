"""Result poller — SPEC-028 mínimo: API-Football (o mock) → MATCH#/RESULT → collector."""
from __future__ import annotations

import logging
from typing import Any, Protocol

from src.clients.api_football_mock import ApiFootballFixture, MockApiFootballClient
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.result_dao import ResultDAO
from src.models.match_result import MatchResult
from src.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ApiFootballClientProtocol(Protocol):
    def get_fixture(self, api_match_id: int) -> ApiFootballFixture | None: ...

    def list_terminal_fixtures(self) -> list[ApiFootballFixture]: ...


class ResultPollerService:
    """
    Simula el poller en vivo: persiste resultado parcial (sin MVP) y delega
    en ResultService para enriquecer / notificar / scoring.
    """

    def __init__(
        self,
        *,
        api_client: ApiFootballClientProtocol | None = None,
        match_dao: MatchDAO | None = None,
        result_dao: ResultDAO | None = None,
        result_service: ResultService | None = None,
    ):
        self._api = api_client or MockApiFootballClient()
        self._matches = match_dao or MatchDAO()
        self._results = result_dao or ResultDAO()
        self._collector = result_service or ResultService(
            match_dao=self._matches,
            result_dao=self._results,
        )

    def poll_once(
        self,
        *,
        api_match_ids: list[int] | None = None,
        dry_run: bool = False,
        telegram_direct: bool = False,
    ) -> dict[str, Any]:
        fixtures = self._api.list_terminal_fixtures()
        if api_match_ids is not None:
            want = {int(x) for x in api_match_ids}
            fixtures = [f for f in fixtures if f.api_match_id in want]

        processed: list[str] = []
        skipped: list[dict[str, str]] = []

        for fx in fixtures:
            if dry_run:
                processed.append(f"{fx.home_team}_{fx.away_team}")
                logger.info(
                    "[dry-run] poller api=%s %s vs %s → %s-%s",
                    fx.api_match_id,
                    fx.home_team,
                    fx.away_team,
                    fx.home_goals,
                    fx.away_goals,
                )
                continue

            match = self._matches.find_by_teams(fx.home_team, fx.away_team)
            if not match:
                skipped.append(
                    {
                        "api_match_id": str(fx.api_match_id),
                        "reason": f"no Dynamo match {fx.home_team} vs {fx.away_team}",
                    }
                )
                continue
            mid = match["match_id"]

            if self._results.is_scoring_done(mid):
                skipped.append({"match_id": mid, "reason": "scoring_done"})
                continue

            result = fx.to_match_result(match)
            if not self._results.has_scores(mid):
                saved = self._results.save_result(mid, result)
                if saved:
                    self._matches.update_status(mid, "FINISHED")
                    logger.info(
                        "Poller guardó RESULT %s vs %s (%s-%s)",
                        fx.home_team,
                        fx.away_team,
                        result.home_goals,
                        result.away_goals,
                    )
            else:
                logger.info("Poller: RESULT ya existe %s", mid[:8])

            collected = self._collector.collect_result(
                mid,
                telegram_direct=telegram_direct,
                force_notify=telegram_direct,
            )
            if collected:
                processed.append(mid)

        return {
            "fixtures": len(fixtures),
            "processed": processed,
            "skipped": skipped,
        }
