"""GROUP_UPGRADE# — compras ampliación grupos (SPEC-2026-044)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr

from src.dao.dynamo.table import get_table

STATUS_PENDING_PAYMENT = "PENDING_PAYMENT"
STATUS_PAID = "PAID"
STATUS_ALLOCATED = "ALLOCATED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GroupUpgradeDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def create_purchase(
        self,
        *,
        user_id: str,
        units: int,
        amount_ars: int,
        promo_applied: bool,
        allocation_json: list[dict[str, Any]] | None = None,
    ) -> str:
        purchase_id = str(uuid.uuid4())
        self._table.put_item(
            Item={
                "partition_key": f"GROUP_UPGRADE#{purchase_id}",
                "sort_key": "DETAILS",
                "purchase_id": purchase_id,
                "user_id": user_id,
                "units": int(units),
                "amount_ars": int(amount_ars),
                "promo_applied": bool(promo_applied),
                "allocation_json": allocation_json or [],
                "status": STATUS_PENDING_PAYMENT,
                "telegram_file_id": None,
                "created_at": _now_iso(),
            }
        )
        return purchase_id

    def mark_paid(
        self,
        purchase_id: str,
        *,
        telegram_file_id: str,
    ) -> None:
        self._table.update_item(
            Key={
                "partition_key": f"GROUP_UPGRADE#{purchase_id}",
                "sort_key": "DETAILS",
            },
            UpdateExpression=(
                "SET #st = :paid, telegram_file_id = :fid, paid_at = :now"
            ),
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":paid": STATUS_PAID,
                ":fid": telegram_file_id,
                ":now": _now_iso(),
            },
        )

    def mark_allocated(self, purchase_id: str) -> None:
        self._table.update_item(
            Key={
                "partition_key": f"GROUP_UPGRADE#{purchase_id}",
                "sort_key": "DETAILS",
            },
            UpdateExpression="SET #st = :st, allocated_at = :now",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":st": STATUS_ALLOCATED,
                ":now": _now_iso(),
            },
        )

    def find_by_file_id(self, file_id: str) -> dict[str, Any] | None:
        if not file_id:
            return None
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": (
                Attr("partition_key").begins_with("GROUP_UPGRADE#")
                & Attr("sort_key").eq("DETAILS")
                & Attr("telegram_file_id").eq(file_id)
            ),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            items = resp.get("Items", [])
            if items:
                return items[0]
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return None

    def list_recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": (
                Attr("partition_key").begins_with("GROUP_UPGRADE#")
                & Attr("sort_key").eq("DETAILS")
            ),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items[:limit]
