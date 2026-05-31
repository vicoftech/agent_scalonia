"""Predicciones globales del torneo USER#/TORNEO#2026 — SPEC-2026-048."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from src.dao.dynamo.table import get_table

TOURNAMENT_ID = "2026"
SK_TORNEO = f"TORNEO#{TOURNAMENT_ID}"
SK_AWARDS = "AWARDS"
PK_TOURNAMENT = f"TOURNAMENT#{TOURNAMENT_ID}"

STATUS_DRAFT = "DRAFT"
STATUS_LOCKED = "LOCKED"
STATUS_SCORED = "SCORED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TournamentPredictionDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def get_by_user(self, user_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": SK_TORNEO},
        )
        return resp.get("Item")

    def put(self, user_id: str, data: dict[str, Any], *, allow_locked: bool = False) -> None:
        existing = self.get_by_user(user_id) or {}
        status = existing.get("status")
        if status == STATUS_SCORED:
            raise ValueError("Las predicciones del torneo ya fueron puntuadas.")
        if status == STATUS_LOCKED and not allow_locked:
            raise ValueError("La veda de predicciones del torneo está cerrada.")

        now = _now_iso()
        item = {
            "partition_key": f"USER#{user_id}",
            "sort_key": SK_TORNEO,
            "user_id": user_id,
            "tournament_id": TOURNAMENT_ID,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            **data,
        }
        if status == STATUS_LOCKED:
            item["status"] = STATUS_LOCKED
        self._table.put_item(Item=item)

    def lock_user(self, user_id: str) -> None:
        existing = self.get_by_user(user_id)
        if not existing or existing.get("status") == STATUS_SCORED:
            return
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": SK_TORNEO},
            UpdateExpression="SET #st = :locked, locked_at = :now, updated_at = :now",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":locked": STATUS_LOCKED,
                ":now": _now_iso(),
            },
        )

    def mark_scored(
        self,
        user_id: str,
        *,
        points_earned: int,
        points_breakdown: dict[str, int],
    ) -> None:
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": SK_TORNEO},
            UpdateExpression=(
                "SET #st = :scored, points_earned = :pts, points_breakdown = :bd, "
                "updated_at = :now"
            ),
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":scored": STATUS_SCORED,
                ":pts": int(points_earned),
                ":bd": points_breakdown,
                ":now": _now_iso(),
            },
        )

    def list_all_for_scoring(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": "sort_key = :sk",
            "ExpressionAttributeValues": {":sk": SK_TORNEO},
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return items

    def get_awards(self) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": PK_TOURNAMENT, "sort_key": SK_AWARDS},
        )
        return resp.get("Item")

    def put_awards(self, data: dict[str, Any]) -> None:
        now = _now_iso()
        item = {
            "partition_key": PK_TOURNAMENT,
            "sort_key": SK_AWARDS,
            "tournament_id": TOURNAMENT_ID,
            "awards_processed": False,
            "updated_at": now,
            **data,
        }
        self._table.put_item(Item=item)

    def mark_awards_processed(self) -> None:
        self._table.update_item(
            Key={"partition_key": PK_TOURNAMENT, "sort_key": SK_AWARDS},
            UpdateExpression="SET awards_processed = :t, updated_at = :now",
            ExpressionAttributeValues={":t": True, ":now": _now_iso()},
        )

    def try_mark_awards_processed(self) -> bool:
        """Idempotencia: True si este proceso ganó el lock de scoring."""
        try:
            self._table.update_item(
                Key={"partition_key": PK_TOURNAMENT, "sort_key": SK_AWARDS},
                UpdateExpression="SET awards_processed = :t, updated_at = :now",
                ConditionExpression="attribute_not_exists(awards_processed) OR awards_processed = :f",
                ExpressionAttributeValues={
                    ":t": True,
                    ":f": False,
                    ":now": _now_iso(),
                },
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
