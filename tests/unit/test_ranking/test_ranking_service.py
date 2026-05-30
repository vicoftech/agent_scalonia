"""RankingService — SPEC-2026-042."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.services.ranking_service import RankingService


def _service(
    *,
    groups: MagicMock,
    users: MagicMock,
    preds: MagicMock,
) -> RankingService:
    return RankingService(group_dao=groups, user_dao=users, prediction_dao=preds)


def test_build_group_ranking_orders_by_points_and_joined_at():
    groups = MagicMock()
    users = MagicMock()
    preds = MagicMock()
    groups.get_group.return_value = {"name": "Scaloneta", "status": "ACTIVE"}
    groups.list_member_user_ids.return_value = ["u1", "u2", "u3"]
    groups.get_member.side_effect = lambda gid, uid: {
        "u1": {"joined_at": "2026-01-03"},
        "u2": {"joined_at": "2026-01-01"},
        "u3": {"joined_at": "2026-01-02"},
    }[uid]
    users.get_profile.side_effect = lambda uid: {"alias": {"u1": "Ana", "u2": "Luis", "u3": "Pedro"}[uid]}

    def list_preds(user_id, *, group_id=None, status=None):
        pts = {"u1": 19, "u2": 23, "u3": 8}
        return [{"points_earned": pts[user_id]}]

    preds.list_user_predictions.side_effect = list_preds

    ranking = _service(groups=groups, users=users, preds=preds).build_group_ranking(
        "g1", viewer_user_id="u3"
    )
    assert ranking is not None
    assert ranking["group_name"] == "Scaloneta"
    assert [r["position"] for r in ranking["rows"]] == [1, 2, 3]
    assert ranking["rows"][0]["alias"] == "Luis"
    assert ranking["rows"][0]["points"] == 23
    viewer = next(r for r in ranking["rows"] if r["is_viewer"])
    assert viewer["alias"] == "Pedro"
    assert viewer["points"] == 8


def test_build_group_ranking_tie_breaks_by_joined_at():
    groups = MagicMock()
    users = MagicMock()
    preds = MagicMock()
    groups.get_group.return_value = {"name": "Empate", "status": "ACTIVE"}
    groups.list_member_user_ids.return_value = ["u1", "u2"]
    groups.get_member.side_effect = lambda gid, uid: {
        "u1": {"joined_at": "2026-01-02"},
        "u2": {"joined_at": "2026-01-01"},
    }[uid]
    users.get_profile.side_effect = lambda uid: {"alias": uid.upper()}
    preds.list_user_predictions.return_value = [{"points_earned": 5}]

    ranking = _service(groups=groups, users=users, preds=preds).build_group_ranking(
        "g1", viewer_user_id="u1"
    )
    assert ranking["rows"][0]["user_id"] == "u2"
    assert ranking["rows"][1]["user_id"] == "u1"


def test_list_user_groups_excludes_global_and_deleted():
    groups = MagicMock()
    groups.list_group_ids_for_user.return_value = ["GLOBAL", "g1", "g2"]
    groups.get_group.side_effect = lambda gid: {
        "GLOBAL": {"is_global": True, "name": "Global"},
        "g1": {"name": "Scaloneta", "status": "ACTIVE"},
        "g2": {"status": "DELETED", "name": "Old"},
    }.get(gid)

    out = RankingService(group_dao=groups).list_user_groups_for_ranking("u1")
    assert len(out) == 1
    assert out[0]["group_id"] == "g1"
