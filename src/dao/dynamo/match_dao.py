"""MATCH#<uuid>/DETAILS — fixture Mundial 2026 (lectura/escritura DynamoDB)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from boto3.dynamodb.conditions import Attr, Key

from src.dao.dynamo.table import get_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MatchDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def put_match(
        self, record: dict[str, Any], *, provision_schedules: bool | None = None
    ) -> dict[str, Any]:
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
            "sandbox_mode": record.get("sandbox_mode", "NONE"),
            "updated_at": _now_iso(),
        }
        if record.get("sandbox_started_at"):
            item["sandbox_started_at"] = record["sandbox_started_at"]
        if record.get("created_at"):
            item["created_at"] = record["created_at"]
        else:
            item["created_at"] = item["updated_at"]

        self._table.put_item(Item=item)

        if provision_schedules is None:
            provision_schedules = os.environ.get("ENABLE_MATCH_SCHEDULES", "").lower() in (
                "1",
                "true",
                "yes",
            )
        if provision_schedules:
            from src.services.scheduler_manager import maybe_provision_after_put

            maybe_provision_after_put(item)

        return item

    def get_match(self, match_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "DETAILS"},
        )
        return resp.get("Item")

    def get_result(self, match_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
        )
        return resp.get("Item")

    def get_by_match_number(self, match_number: int) -> dict[str, Any] | None:
        for m in self.list_matches():
            if int(m.get("match_number", -1)) == match_number:
                return m
        return None

    def delete_all_matches(self, *, deprovision_schedules: bool = True) -> int:
        """Elimina todos los MATCH#/DETAILS (reemplazo de fixture)."""
        items = self.list_matches()
        if deprovision_schedules and os.environ.get("ENABLE_MATCH_SCHEDULES", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            from src.services.scheduler_manager import MatchScheduleManager

            mgr = MatchScheduleManager()
            if mgr.is_enabled():
                for it in items:
                    mid = it.get("match_id")
                    if mid:
                        mgr.deprovision_match(str(mid))
        for it in items:
            self._table.delete_item(
                Key={
                    "partition_key": it["partition_key"],
                    "sort_key": it["sort_key"],
                }
            )
        return len(items)

    def set_sandbox_state(
        self,
        match_id: str,
        *,
        mode: str,
        started_at: datetime | None = None,
    ) -> None:
        started = started_at or datetime.now(timezone.utc)
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "DETAILS"},
            UpdateExpression=(
                "SET sandbox_mode = :m, sandbox_started_at = :s, updated_at = :now"
            ),
            ExpressionAttributeValues={
                ":m": mode,
                ":s": started.isoformat(),
                ":now": _now_iso(),
            },
        )

    def clear_sandbox_state(self, match_id: str) -> None:
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "DETAILS"},
            UpdateExpression=(
                "SET sandbox_mode = :m, updated_at = :now REMOVE sandbox_started_at"
            ),
            ExpressionAttributeValues={":m": "NONE", ":now": _now_iso()},
        )

    def set_veda_active(self, match_id: str, *, active: bool) -> None:
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "DETAILS"},
            UpdateExpression="SET veda_active = :v, updated_at = :now",
            ExpressionAttributeValues={
                ":v": active,
                ":now": _now_iso(),
            },
        )

    def update_status(self, match_id: str, status: str) -> None:
        """Actualiza status en DETAILS (SCHEDULED, LIVE, FINISHED, …)."""
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "DETAILS"},
            UpdateExpression="SET #st = :s, updated_at = :now",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":s": status, ":now": _now_iso()},
        )

    def list_matches_estimated_finished(self) -> list[dict[str, Any]]:
        """Partidos cuyo kickoff + 110 min ya pasó (candidatos a resultado)."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        out: list[dict[str, Any]] = []
        for m in self.list_matches():
            kickoff_raw = m.get("kickoff_utc") or ""
            if not kickoff_raw:
                continue
            kickoff = datetime.fromisoformat(
                kickoff_raw.replace("Z", "+00:00")
            )
            if kickoff + timedelta(minutes=110) >= now:
                continue
            out.append(m)
        return out

    def find_by_teams(self, home_code: str, away_code: str) -> dict[str, Any] | None:
        home = home_code.strip().upper()
        away = away_code.strip().upper()
        for m in self.list_matches():
            if m.get("home_team") == home and m.get("away_team") == away:
                return m
        return None

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
