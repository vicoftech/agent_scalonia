"""MatchResult — SPEC-2026-031 resultado final de partido."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

ResultStatus = Literal["FT", "AET", "PEN"]
PlayoffVia = Literal["ET", "PENALTIES"] | None
ResultSource = Literal["api_football", "web_search"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_via(status: str) -> PlayoffVia:
    s = (status or "FT").upper()
    if s == "AET":
        return "ET"
    if s == "PEN":
        return "PENALTIES"
    return None


@dataclass
class MatchResult:
    home_goals: int
    away_goals: int
    phase: str = "GROUP"
    playoff_via: PlayoffVia = None
    playoff_winner: str | None = None
    home_goals_aet: int | None = None
    away_goals_aet: int | None = None
    scorers: dict[str, int] = field(default_factory=dict)
    red_cards: int = 0
    mvp_name: str | None = None
    status: ResultStatus = "FT"
    source: ResultSource = "web_search"
    result_processed: bool = False
    match_id: str | None = None
    recorded_at: str | None = None
    mvp_enriched_at: str | None = None

    @property
    def home_goals_ft(self) -> int:
        return self.home_goals

    @property
    def away_goals_ft(self) -> int:
        return self.away_goals

    def to_dict(self) -> dict[str, Any]:
        return {
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "home_goals_ft": self.home_goals_ft,
            "away_goals_ft": self.away_goals_ft,
            "phase": self.phase,
            "playoff_via": self.playoff_via,
            "playoff_winner": self.playoff_winner,
            "home_goals_aet": self.home_goals_aet,
            "away_goals_aet": self.away_goals_aet,
            "scorers": dict(self.scorers),
            "red_cards": self.red_cards,
            "mvp_name": self.mvp_name,
            "status": self.status,
            "source": self.source,
            "result_processed": self.result_processed,
            "match_id": self.match_id,
            "recorded_at": self.recorded_at,
            "mvp_enriched_at": self.mvp_enriched_at,
        }

    @classmethod
    def from_dynamo(cls, item: dict[str, Any]) -> MatchResult:
        home = item.get("home_goals_ft")
        away = item.get("away_goals_ft")
        if home is None:
            home = item.get("result_90min_home", item.get("result_final_home", 0))
        if away is None:
            away = item.get("result_90min_away", item.get("result_final_away", 0))
        scorers = item.get("scorers") or {}
        if isinstance(scorers, str):
            import json

            try:
                scorers = json.loads(scorers)
            except json.JSONDecodeError:
                scorers = {}
        return cls(
            home_goals=int(home),
            away_goals=int(away),
            phase=item.get("phase", "GROUP"),
            playoff_via=item.get("playoff_via"),
            playoff_winner=item.get("playoff_winner"),
            home_goals_aet=item.get("home_goals_aet"),
            away_goals_aet=item.get("away_goals_aet"),
            scorers=dict(scorers) if isinstance(scorers, dict) else {},
            red_cards=int(item.get("red_cards", 0)),
            mvp_name=item.get("mvp_name"),
            status=item.get("status", "FT"),  # type: ignore[arg-type]
            source=item.get("source", "web_search"),  # type: ignore[arg-type]
            result_processed=bool(item.get("result_processed", False)),
            match_id=item.get("match_id"),
            recorded_at=item.get("recorded_at"),
            mvp_enriched_at=item.get("mvp_enriched_at"),
        )

    @classmethod
    def from_parse_payload(cls, data: dict[str, Any], match: dict[str, Any]) -> MatchResult | None:
        if not data.get("found"):
            return None
        status = str(data.get("status", "FT")).upper()
        if status not in ("FT", "AET", "PEN"):
            status = "FT"
        return cls(
            home_goals=int(data["home_goals"]),
            away_goals=int(data["away_goals"]),
            phase=match.get("phase", "GROUP"),
            playoff_via=_resolve_via(status),
            playoff_winner=data.get("playoff_winner"),
            scorers=dict(data.get("scorers") or {}),
            red_cards=int(data.get("red_cards", 0)),
            mvp_name=data.get("mvp_name"),
            status=status,  # type: ignore[arg-type]
            source="web_search",
        )
