"""Mock API-Football para probar result_poller sin red."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.models.match_result import MatchResult

FixtureStatus = Literal["NS", "LIVE", "FT", "AET", "PEN"]

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "data/fixtures/mock_api_football_fixtures.json"
)

TERMINAL_STATUSES = frozenset({"FT", "AET", "PEN"})


@dataclass(frozen=True)
class ApiFootballFixture:
    api_match_id: int
    status: FixtureStatus
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    scorers: dict[str, int]
    red_cards: int = 0
    goal_before_5min: bool | None = None
    var_used: bool | None = None
    free_kick_goal: bool | None = None
    penalty_saved: bool | None = None
    penalty_scored: bool | None = None
    playoff_winner: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ApiFootballFixture:
        return cls(
            api_match_id=int(raw["api_match_id"]),
            status=str(raw.get("status", "FT")).upper(),  # type: ignore[arg-type]
            home_team=str(raw["home_team"]).upper(),
            away_team=str(raw["away_team"]).upper(),
            home_goals=int(raw["home_goals"]),
            away_goals=int(raw["away_goals"]),
            scorers=dict(raw.get("scorers") or {}),
            red_cards=int(raw.get("red_cards", 0)),
            goal_before_5min=raw.get("goal_before_5min"),
            var_used=raw.get("var_used"),
            free_kick_goal=raw.get("free_kick_goal"),
            penalty_saved=raw.get("penalty_saved"),
            penalty_scored=raw.get("penalty_scored"),
            playoff_winner=raw.get("playoff_winner"),
        )

    def to_match_result(self, match: dict[str, Any]) -> MatchResult:
        status = self.status
        playoff_via = None
        if status == "AET":
            playoff_via = "ET"
        elif status == "PEN":
            playoff_via = "PENALTIES"
        return MatchResult(
            home_goals=self.home_goals,
            away_goals=self.away_goals,
            phase=match.get("phase", "GROUP"),
            playoff_via=playoff_via,
            playoff_winner=self.playoff_winner,
            scorers=dict(self.scorers),
            red_cards=self.red_cards,
            goal_before_5min=self.goal_before_5min,
            var_used=self.var_used,
            free_kick_goal=self.free_kick_goal,
            penalty_saved=self.penalty_saved,
            penalty_scored=self.penalty_scored,
            mvp_name=None,
            status="FT" if status == "FT" else status,  # type: ignore[arg-type]
            source="api_football",
        )


class MockApiFootballClient:
    """Lee fixtures terminados desde JSON (mismo contrato que un cliente real mínimo)."""

    def __init__(self, fixture_path: Path | str | None = None):
        path = Path(fixture_path) if fixture_path else DEFAULT_FIXTURE
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("fixtures") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError(f"mock API fixture inválido: {path}")
        self._by_id: dict[int, ApiFootballFixture] = {
            ApiFootballFixture.from_dict(r).api_match_id: ApiFootballFixture.from_dict(r)
            for r in rows
        }

    def get_fixture(self, api_match_id: int) -> ApiFootballFixture | None:
        return self._by_id.get(int(api_match_id))

    def list_terminal_fixtures(self) -> list[ApiFootballFixture]:
        return [f for f in self._by_id.values() if f.status in TERMINAL_STATUSES]
