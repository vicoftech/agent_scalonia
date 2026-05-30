"""Ranking por grupo (Dynamo) — SPEC-2026-042."""
from __future__ import annotations

from typing import Any

from src.dao.dynamo.group_dao import GroupDAO
from src.dao.dynamo.prediction_dao import PredictionDAO
from src.dao.dynamo.user_dao import UserDAO

RANKING_TOP_N = 25


class RankingService:
    def __init__(
        self,
        *,
        group_dao: GroupDAO | None = None,
        user_dao: UserDAO | None = None,
        prediction_dao: PredictionDAO | None = None,
    ):
        self._groups = group_dao or GroupDAO()
        self._users = user_dao or UserDAO()
        self._preds = prediction_dao or PredictionDAO()

    def list_user_groups_for_ranking(self, user_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for gid in self._groups.list_group_ids_for_user(user_id):
            g = self._groups.get_group(gid)
            if not g or g.get("is_global") or g.get("status") == "DELETED":
                continue
            out.append(
                {
                    "group_id": gid,
                    "name": g.get("name") or gid[:8],
                    "avatar": g.get("avatar") or "⚽",
                }
            )
        out.sort(key=lambda x: str(x.get("name") or "").lower())
        return out

    def _sum_scored_points(self, user_id: str, group_id: str) -> int:
        preds = self._preds.list_user_predictions(
            user_id, group_id=group_id, status="SCORED"
        )
        return sum(int(p.get("points_earned") or 0) for p in preds)

    def _member_joined_at(self, group_id: str, user_id: str) -> str:
        member = self._groups.get_member(group_id, user_id)
        return str((member or {}).get("joined_at") or "")

    def build_group_ranking(
        self,
        group_id: str,
        *,
        viewer_user_id: str,
    ) -> dict[str, Any] | None:
        g = self._groups.get_group(group_id)
        if not g or g.get("is_global") or g.get("status") == "DELETED":
            return None
        group_name = str(g.get("name") or group_id[:8])
        rows_data: list[dict[str, Any]] = []
        for uid in self._groups.list_member_user_ids(group_id):
            profile = self._users.get_profile(uid) or {}
            alias = str(profile.get("alias") or uid[:8]).strip()
            rows_data.append(
                {
                    "user_id": uid,
                    "alias": alias,
                    "points": self._sum_scored_points(uid, group_id),
                    "joined_at": self._member_joined_at(group_id, uid),
                }
            )
        rows_data.sort(
            key=lambda r: (
                -int(r["points"]),
                str(r["joined_at"]),
                str(r["alias"]).lower(),
            )
        )
        ranked: list[dict[str, Any]] = []
        for pos, row in enumerate(rows_data, start=1):
            ranked.append(
                {
                    **row,
                    "position": pos,
                    "is_viewer": row["user_id"] == viewer_user_id,
                }
            )
        return {
            "group_id": group_id,
            "group_name": group_name,
            "rows": ranked,
        }
