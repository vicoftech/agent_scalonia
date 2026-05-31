"""Scoring de predicciones globales post-M104 — SPEC-2026-048."""
from __future__ import annotations

import re
from typing import Any

from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.tournament_prediction_dao import (
    STATUS_SCORED,
    TournamentPredictionDAO,
)
from src.dao.dynamo.user_dao import UserDAO
from src.services.tournament_prediction_service import POINTS_TABLE, WIZARD_FIELDS

MATCH_FINAL_NUMBER = 104

AWARD_PLAYER_FIELDS = {
    "best_player_name": ("best_player_name", "best_player_id"),
    "top_scorer_name": ("top_scorer_name", "top_scorer_id"),
    "best_goalkeeper_name": ("best_goalkeeper_name", "best_goalkeeper_id"),
    "best_young_player_name": ("best_young_player_name", "best_young_player_id"),
}


def _norm_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


class TournamentScoringService:
    def __init__(
        self,
        *,
        prediction_dao: TournamentPredictionDAO | None = None,
        user_dao: UserDAO | None = None,
        match_dao: MatchDAO | None = None,
    ):
        self._preds = prediction_dao or TournamentPredictionDAO()
        self._users = user_dao or UserDAO()
        self._matches = match_dao or MatchDAO()

    def can_process(self) -> tuple[bool, str]:
        m104 = self._matches.get_by_match_number(MATCH_FINAL_NUMBER)
        if not m104 or m104.get("status") != "FINISHED":
            return False, "Partido #104 aún no finalizado."
        awards = self._preds.get_awards()
        if not awards:
            return False, "Faltan premios oficiales (TOURNAMENT#2026/AWARDS)."
        if awards.get("awards_processed"):
            return False, "Scoring de torneo ya procesado."
        return True, ""

    def _resolve_champion_finalist(self, awards: dict[str, Any]) -> tuple[str | None, str | None]:
        champion = awards.get("champion_team")
        finalist = awards.get("finalist_team")
        if champion and finalist:
            return str(champion).upper(), str(finalist).upper()
        m104 = self._matches.get_by_match_number(MATCH_FINAL_NUMBER)
        result = self._matches.get_result(m104["match_id"]) if m104 else None
        if not result:
            return champion, finalist
        home = int(result.get("result_90min_home", result.get("result_final_home", 0)))
        away = int(result.get("result_90min_away", result.get("result_final_away", 0)))
        if home == away:
            return champion, finalist
        if home > away:
            winner = (m104 or {}).get("home_team")
            loser = (m104 or {}).get("away_team")
        else:
            winner = (m104 or {}).get("away_team")
            loser = (m104 or {}).get("home_team")
        return (str(winner or champion or "").upper() or None), (
            str(loser or finalist or "").upper() or None
        )

    def _player_match(self, predicted: str | None, awards: dict[str, Any], field: str) -> bool:
        name_key, id_key = AWARD_PLAYER_FIELDS[field]
        official_name = awards.get(name_key)
        official_id = awards.get(id_key)
        pred_norm = _norm_name(predicted)
        if not pred_norm:
            return False
        if official_name and _norm_name(str(official_name)) == pred_norm:
            return True
        if official_id and _norm_name(str(official_id)) == pred_norm:
            return True
        co_scorers = awards.get("top_scorer_names") or []
        if field == "top_scorer_name" and co_scorers:
            return any(_norm_name(str(n)) == pred_norm for n in co_scorers)
        return False

    def score_user(self, user_id: str, item: dict[str, Any], awards: dict[str, Any]) -> dict[str, Any]:
        if item.get("status") == STATUS_SCORED:
            return {"user_id": user_id, "skipped": True, "points": int(item.get("points_earned") or 0)}

        champion, finalist = self._resolve_champion_finalist(awards)
        breakdown: dict[str, int] = {}

        if champion and item.get("champion_team") == champion:
            breakdown["champion_team"] = POINTS_TABLE["champion_team"]
        else:
            breakdown["champion_team"] = 0

        if finalist and item.get("finalist_team") == finalist:
            breakdown["finalist_team"] = POINTS_TABLE["finalist_team"]
        else:
            breakdown["finalist_team"] = 0

        for field in (
            "best_player_name",
            "top_scorer_name",
            "best_goalkeeper_name",
            "best_young_player_name",
        ):
            breakdown[field] = (
                POINTS_TABLE[field]
                if self._player_match(item.get(field), awards, field)
                else 0
            )

        revelation = str(awards.get("revelation_team") or "").upper()
        breakdown["revelation_team"] = (
            POINTS_TABLE["revelation_team"]
            if revelation and item.get("revelation_team") == revelation
            else 0
        )

        total = sum(breakdown.values())
        self._preds.mark_scored(user_id, points_earned=total, points_breakdown=breakdown)
        if total:
            self._users.add_tournament_points(user_id, total)
        self._users.update_profile(user_id, tournament_predictions_status=STATUS_SCORED)
        return {"user_id": user_id, "points": total, "breakdown": breakdown}

    def process_tournament_awards(self) -> dict[str, Any]:
        ok, reason = self.can_process()
        if not ok:
            return {"ok": False, "reason": reason}

        if not self._preds.try_mark_awards_processed():
            return {"ok": False, "reason": "Scoring de torneo ya procesado."}

        awards = self._preds.get_awards() or {}
        items = self._preds.list_all_for_scoring()
        results: list[dict[str, Any]] = []
        for item in items:
            uid = item.get("user_id") or item.get("partition_key", "").replace("USER#", "")
            if not uid:
                continue
            results.append(self.score_user(uid, item, awards))

        return {
            "ok": True,
            "processed": len(results),
            "total_points": sum(int(r.get("points") or 0) for r in results),
            "results": results,
        }
