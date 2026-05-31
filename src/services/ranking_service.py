"""Ranking por grupo (Dynamo) — SPEC-2026-042."""
from __future__ import annotations

from typing import Any

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
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
        global_group = self._groups.get_group(GLOBAL_GROUP_ID)
        if global_group and global_group.get("status") != "DELETED":
            if self._groups.is_member(GLOBAL_GROUP_ID, user_id):
                out.append(
                    {
                        "group_id": GLOBAL_GROUP_ID,
                        "name": global_group.get("name") or "Global",
                        "avatar": global_group.get("avatar") or "🌍",
                    }
                )
        for gid in self._groups.list_group_ids_for_user(user_id):
            if gid == GLOBAL_GROUP_ID:
                continue
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
        private = sorted(
            [g for g in out if g["group_id"] != GLOBAL_GROUP_ID],
            key=lambda x: str(x.get("name") or "").lower(),
        )
        global_rows = [g for g in out if g["group_id"] == GLOBAL_GROUP_ID]
        return global_rows + private

    def resolve_group_short(self, user_id: str, grp8: str) -> str | None:
        needle = (grp8 or "").strip().lower()
        if not needle:
            return None
        for group in self.list_user_groups_for_ranking(user_id):
            gid = str(group["group_id"])
            compact = gid.replace("-", "").lower()
            if compact.startswith(needle) or gid.lower().startswith(needle):
                return gid
        return None

    def _sum_scored_points(self, user_id: str, group_id: str) -> int:
        preds = self._preds.list_user_predictions(
            user_id, group_id=group_id, status="SCORED"
        )
        match_pts = sum(int(p.get("points_earned") or 0) for p in preds)
        profile = self._users.get_profile(user_id) or {}
        tournament_pts = int(profile.get("tournament_points") or 0)
        return match_pts + tournament_pts

    def build_group_ranking(
        self,
        group_id: str,
        *,
        viewer_user_id: str,
    ) -> dict[str, Any] | None:
        g = self._groups.get_group(group_id)
        if not g or g.get("status") == "DELETED":
            return None
        group_name = str(g.get("name") or group_id[:8])
        if g.get("is_global"):
            group_name = group_name or "Global"
        rows_data: list[dict[str, Any]] = []
        for uid in self._groups.list_member_user_ids(group_id):
            profile = self._users.get_profile(uid) or {}
            alias = str(profile.get("alias") or uid[:8]).strip()
            rows_data.append(
                {
                    "user_id": uid,
                    "alias": alias,
                    "points": self._sum_scored_points(uid, group_id),
                }
            )
        rows_data.sort(
            key=lambda r: (
                -int(r["points"]),
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
            "is_global": bool(g.get("is_global")),
        }
