"""Predicciones USER#/PRED#<match_id>#GROUP#<group_id> — SPEC-2026-021."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from src.dao.dynamo.table import get_table

STATUS_ACTIVE = "ACTIVE"
STATUS_SUPERSEDED = "SUPERSEDED"
STATUS_SCORED = "SCORED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prediction_sk(match_id: str, group_id: str) -> str:
    return f"PRED#{match_id}#GROUP#{group_id}"


class PredictionDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def check_veda_active(self, match_id: str) -> bool:
        resp = self._table.get_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "DETAILS"},
            ProjectionExpression="veda_active",
        )
        item = resp.get("Item") or {}
        return bool(item.get("veda_active"))

    def get_active(
        self, user_id: str, match_id: str, group_id: str
    ) -> dict[str, Any] | None:
        item = self._get_item(user_id, match_id, group_id)
        if item and item.get("status") == STATUS_ACTIVE:
            return item
        return None

    def get_for_group(
        self, user_id: str, match_id: str, group_id: str
    ) -> dict[str, Any] | None:
        """Predicción vigente (ACTIVE o SCORED), no SUPERSEDED."""
        item = self._get_item(user_id, match_id, group_id)
        if item and item.get("status") != STATUS_SUPERSEDED:
            return item
        return None

    def _get_item(
        self, user_id: str, match_id: str, group_id: str
    ) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={
                "partition_key": f"USER#{user_id}",
                "sort_key": prediction_sk(match_id, group_id),
            },
        )
        return resp.get("Item")

    def list_user_predictions(
        self, user_id: str, *, group_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        filt = Attr("sort_key").begins_with("PRED#")
        if group_id:
            filt = filt & Attr("group_id").eq(group_id)
        if status:
            filt = filt & Attr("status").eq(status)
        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("partition_key").eq(f"USER#{user_id}"),
            "FilterExpression": filt,
        }
        while True:
            resp = self._table.query(**kwargs)
            items.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return items

    def save_prediction(
        self,
        *,
        user_id: str,
        match_id: str,
        group_id: str,
        home_goals: int,
        away_goals: int,
        playoff_via: str | None = None,
        playoff_winner: str | None = None,
        has_red_card: bool | None = None,
        pred_goal_before_5min: bool | None = None,
        pred_var_used: bool | None = None,
        pred_free_kick_goal: bool | None = None,
        pred_penalty_saved: bool | None = None,
        pred_penalty_scored: bool | None = None,
        scorer_name: str | None = None,
        scorer_goals: int | None = None,
        mvp_name: str | None = None,
    ) -> dict[str, Any]:
        """Nueva ACTIVE; anterior ACTIVE → SUPERSEDED."""
        sk = prediction_sk(match_id, group_id)
        existing = self.get_active(user_id, match_id, group_id)
        now = _now_iso()
        self._supersede_active(user_id, match_id, group_id, now)

        item = {
            "partition_key": f"USER#{user_id}",
            "sort_key": sk,
            "user_id": user_id,
            "match_id": match_id,
            "group_id": group_id,
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "playoff_via": playoff_via,
            "playoff_winner": playoff_winner,
            "has_red_card": has_red_card,
            "pred_goal_before_5min": pred_goal_before_5min,
            "pred_var_used": pred_var_used,
            "pred_free_kick_goal": pred_free_kick_goal,
            "pred_penalty_saved": pred_penalty_saved,
            "pred_penalty_scored": pred_penalty_scored,
            "scorer_name": scorer_name,
            "scorer_goals": scorer_goals,
            "mvp_name": mvp_name,
            "status": STATUS_ACTIVE,
            "created_at": (existing or {}).get("created_at", now),
            "updated_at": now,
            "points_earned": None,
            "scoring_detail": None,
        }
        self._table.put_item(Item=item)
        return item

    def _supersede_active(
        self, user_id: str, match_id: str, group_id: str, now: str
    ) -> None:
        sk = prediction_sk(match_id, group_id)
        try:
            self._table.update_item(
                Key={"partition_key": f"USER#{user_id}", "sort_key": sk},
                UpdateExpression="SET #st = :sup, updated_at = :now",
                ConditionExpression="#st = :act",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":act": STATUS_ACTIVE,
                    ":sup": STATUS_SUPERSEDED,
                    ":now": now,
                },
            )
        except Exception as exc:
            if exc.__class__.__name__ != "ConditionalCheckFailedException":
                raise

    def update_optional_fields(
        self, user_id: str, match_id: str, group_id: str, **fields: Any
    ) -> dict[str, Any] | None:
        pred = self.get_active(user_id, match_id, group_id)
        if not pred:
            return None
        names: dict[str, str] = {"#u": "updated_at"}
        values: dict[str, Any] = {":now": _now_iso()}
        sets: list[str] = ["#u = :now"]
        i = 0
        for key, val in fields.items():
            if val is None:
                continue
            attr = f"#f{i}"
            val_a = f":v{i}"
            names[attr] = key
            values[val_a] = val
            sets.append(f"{attr} = {val_a}")
            i += 1
        if i == 0:
            return pred
        self._table.update_item(
            Key={
                "partition_key": f"USER#{user_id}",
                "sort_key": prediction_sk(match_id, group_id),
            },
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
        return self.get_active(user_id, match_id, group_id)

    def get_predictions_for_match(self, match_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {
            "IndexName": "GSI-2-match-predictions",
            "KeyConditionExpression": Key("match_id").eq(match_id),
        }
        while True:
            resp = self._table.query(**kwargs)
            items.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return [i for i in items if i.get("status") == STATUS_ACTIVE]

    def get_group_ids_with_predictions(self, match_id: str) -> list[str]:
        """Grupos distintos con al menos una predicción ACTIVE del partido."""
        seen: set[str] = set()
        out: list[str] = []
        for pred in self.get_predictions_for_match(match_id):
            gid = pred.get("group_id")
            if gid and gid not in seen:
                seen.add(gid)
                out.append(gid)
        return out
