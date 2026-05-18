"""MATCH#<uuid>/DETAILS — fixture Mundial 2026 (lectura/escritura DynamoDB)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from src.dao.dynamo.table import get_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MatchDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def put_match(self, record: dict[str, Any]) -> dict[str, Any]:
        """Upsert idempotente de MATCH#/DETAILS."""
        match_id = record["match_id"]
        item = {
            "partition_key": f"MATCH#{match_id}",
            "sort_key": "DETAILS",
            "match_id": match_id,
            "home_team": record["home_team"],
            "away_team": record["away_team"],
            "phase": record["phase"],
            "group_letter": record.get("group_letter"),
            "match_number": int(record["match_number"]),
            "kickoff_utc": record["kickoff_utc"],
            "venue": record.get("venue") or "",
            "city": record.get("city") or "",
            "country": record.get("country") or "",
            "veda_active": bool(record.get("veda_active", False)),
            "status": record.get("status", "SCHEDULED"),
            "result_processed": bool(record.get("result_processed", False)),
            "updated_at": _now_iso(),
        }
        if record.get("created_at"):
            item["created_at"] = record["created_at"]
        else:
            item["created_at"] = item["updated_at"]

        self._table.put_item(Item=item)
        return item

    def get_match(self, match_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "DETAILS"},
        )
        return resp.get("Item")

    def get_by_match_number(self, match_number: int) -> dict[str, Any] | None:
        for m in self.list_matches():
            if int(m.get("match_number", -1)) == match_number:
                return m
        return None

    def delete_all_matches(self) -> int:
        """Elimina todos los MATCH#/DETAILS (reemplazo de fixture)."""
        items = self.list_matches()
        for it in items:
            self._table.delete_item(
                Key={
                    "partition_key": it["partition_key"],
                    "sort_key": it["sort_key"],
                }
            )
        return len(items)

    def list_matches(self) -> list[dict[str, Any]]:
        """Scan de partidos (≤104 ítems — aceptable en MVP)."""
        items: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("sort_key").eq("DETAILS")
            & Attr("partition_key").begins_with("MATCH#"),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        items.sort(key=lambda m: int(m.get("match_number", 0)))
        return items
