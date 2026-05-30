"""RankingService — SPEC-2026-042."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID
from src.services.ranking_service import RankingService


def _service(
    *,
    groups: MagicMock,
    users: MagicMock,
    preds: MagicMock,
) -> RankingService:
    return RankingService(group_dao=groups, user_dao=users, prediction_dao=preds)


def test_build_group_ranking_orders_by_points_and_alias():
    groups = MagicMock()
    users = MagicMock()
    preds = MagicMock()
    groups.get_group.return_value = {"name": "Scaloneta", "status": "ACTIVE"}
    groups.list_member_user_ids.return_value = ["u1", "u2", "u3"]
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


def test_build_group_ranking_tie_breaks_by_alias():
    groups = MagicMock()
    users = MagicMock()
    preds = MagicMock()
    groups.get_group.return_value = {"name": "Empate", "status": "ACTIVE"}
    groups.list_member_user_ids.return_value = ["u1", "u2"]
    users.get_profile.side_effect = lambda uid: {
        "u1": {"alias": "Zoe"},
        "u2": {"alias": "Ana"},
    }[uid]
    preds.list_user_predictions.return_value = [{"points_earned": 5}]

    ranking = _service(groups=groups, users=users, preds=preds).build_group_ranking(
        "g1", viewer_user_id="u1"
    )
    assert ranking["rows"][0]["alias"] == "Ana"
    assert ranking["rows"][1]["alias"] == "Zoe"


def test_build_group_ranking_shows_zero_points():
    groups = MagicMock()
    users = MagicMock()
    preds = MagicMock()
    groups.get_group.return_value = {"name": "Vacío", "status": "ACTIVE"}
    groups.list_member_user_ids.return_value = ["u1"]
    users.get_profile.return_value = {"alias": "toti"}
    preds.list_user_predictions.return_value = []

    ranking = _service(groups=groups, users=users, preds=preds).build_group_ranking(
        "g1", viewer_user_id="u1"
    )
    assert ranking["rows"] == [
        {
            "user_id": "u1",
            "alias": "toti",
            "points": 0,
            "position": 1,
            "is_viewer": True,
        }
    ]


def test_list_user_groups_includes_global_first():
    groups = MagicMock()
    groups.list_group_ids_for_user.return_value = [GLOBAL_GROUP_ID, "g1"]
    groups.is_member.return_value = True
    groups.get_group.side_effect = lambda gid: {
        GLOBAL_GROUP_ID: {"is_global": True, "name": "Global", "status": "ACTIVE"},
        "g1": {"name": "Scaloneta", "status": "ACTIVE"},
    }.get(gid)

    out = RankingService(group_dao=groups).list_user_groups_for_ranking("u1")
    assert len(out) == 2
    assert out[0]["group_id"] == GLOBAL_GROUP_ID
    assert out[1]["group_id"] == "g1"


def test_resolve_group_short_includes_global():
    groups = MagicMock()
    groups.is_member.return_value = True
    groups.list_group_ids_for_user.return_value = [GLOBAL_GROUP_ID]
    groups.get_group.return_value = {
        "is_global": True,
        "name": "Global",
        "status": "ACTIVE",
    }

    gid = RankingService(group_dao=groups).resolve_group_short("u1", "GLOBAL")
    assert gid == GLOBAL_GROUP_ID
