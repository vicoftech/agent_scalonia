"""GROUP#<id>/DETAILS y membresías GROUP#<id>/MEMBER#<user>."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from src.dao.dynamo.table import get_table
GLOBAL_GROUP_ID = "GLOBAL"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GroupDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def get_group(self, group_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"GROUP#{group_id}", "sort_key": "DETAILS"},
        )
        return resp.get("Item")

    def count_members(self, group_id: str) -> int:
        resp = self._table.query(
            IndexName="GSI-3-group-members",
            KeyConditionExpression=Key("group_id").eq(group_id),
            Select="COUNT",
        )
        return int(resp.get("Count", 0))

    def is_member(self, group_id: str, user_id: str) -> bool:
        resp = self._table.get_item(
            Key={
                "partition_key": f"GROUP#{group_id}",
                "sort_key": f"MEMBER#{user_id}",
            },
        )
        return "Item" in resp

    def add_member(self, group_id: str, user_id: str) -> None:
        if self.is_member(group_id, user_id):
            return
        now = _now_iso()
        self._table.put_item(
            Item={
                "partition_key": f"GROUP#{group_id}",
                "sort_key": f"MEMBER#{user_id}",
                "group_id": group_id,
                "user_id": user_id,
                "joined_at": now,
            },
        )

    def get_owner_group_id(self, owner_user_id: str) -> str | None:
        """Primer grupo cuyo owner_id coincide (FREE tiene como máximo uno)."""
        resp = self._table.scan(
            FilterExpression=Attr("sort_key").eq("DETAILS") & Attr("owner_id").eq(owner_user_id),
            ProjectionExpression="group_id",
        )
        items = resp.get("Items", [])
        return items[0]["group_id"] if items else None
