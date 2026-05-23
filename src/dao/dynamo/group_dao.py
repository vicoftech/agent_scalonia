"""GROUP#<id>/DETAILS y membresías GROUP#<id>/MEMBER#<user> — SPEC-026."""
from __future__ import annotations

import os
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from src.dao.dynamo.table import get_table

GLOBAL_GROUP_ID = "GLOBAL"
_GROUP_CODE_ALPHABET = string.ascii_uppercase + string.digits
_GROUP_STATUS_ACTIVE = "ACTIVE"
_GROUP_STATUS_SUSPENDED = "SUSPENDED"
_GROUP_STATUS_DELETED = "DELETED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_invite_code() -> str:
    return "".join(secrets.choice(_GROUP_CODE_ALPHABET) for _ in range(6))


class GroupDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def get_group(self, group_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"GROUP#{group_id}", "sort_key": "DETAILS"},
        )
        return resp.get("Item")

    def count_members(self, group_id: str) -> int:
        group = self.get_group(group_id)
        if group and group.get("member_count") is not None:
            return int(group["member_count"])
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

    def list_member_user_ids(self, group_id: str) -> list[str]:
        resp = self._table.query(
            IndexName="GSI-3-group-members",
            KeyConditionExpression=Key("group_id").eq(group_id),
            ProjectionExpression="user_id",
        )
        return [i["user_id"] for i in resp.get("Items", []) if i.get("user_id")]

    def add_member(self, group_id: str, user_id: str, *, increment_count: bool = True) -> None:
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
        if increment_count:
            self._adjust_member_count(group_id, 1)

    def remove_member(self, group_id: str, user_id: str) -> bool:
        if not self.is_member(group_id, user_id):
            return False
        self._table.delete_item(
            Key={
                "partition_key": f"GROUP#{group_id}",
                "sort_key": f"MEMBER#{user_id}",
            },
        )
        self._adjust_member_count(group_id, -1)
        return True

    def _adjust_member_count(self, group_id: str, delta: int) -> None:
        self._table.update_item(
            Key={"partition_key": f"GROUP#{group_id}", "sort_key": "DETAILS"},
            UpdateExpression="ADD member_count :d SET updated_at = :now",
            ExpressionAttributeValues={":d": delta, ":now": _now_iso()},
        )

    def get_owner_group_id(self, owner_user_id: str) -> str | None:
        """Primer grupo privado cuyo owner_id coincide (FREE tiene como máximo uno)."""
        resp = self._table.scan(
            FilterExpression=(
                Attr("sort_key").eq("DETAILS")
                & Attr("owner_id").eq(owner_user_id)
                & Attr("is_global").ne(True)
                & Attr("status").ne(_GROUP_STATUS_DELETED)
            ),
            ProjectionExpression="group_id",
        )
        items = resp.get("Items", [])
        return items[0]["group_id"] if items else None

    def list_group_ids_for_user(self, user_id: str) -> list[str]:
        """Grupos donde el usuario es miembro (incluye GLOBAL)."""
        ids: list[str] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": (
                Attr("sort_key").begins_with("MEMBER#") & Attr("user_id").eq(user_id)
            ),
            "ProjectionExpression": "group_id",
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                gid = item.get("group_id")
                if gid and gid not in ids:
                    ids.append(gid)
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return ids

    def create_group(
        self,
        *,
        owner_id: str,
        name: str,
        avatar: str = "⚽",
        max_members: int = 5,
    ) -> dict[str, Any]:
        group_id = str(uuid.uuid4())
        now = _now_iso()
        invite_code = generate_invite_code()
        item = {
            "partition_key": f"GROUP#{group_id}",
            "sort_key": "DETAILS",
            "group_id": group_id,
            "name": name,
            "owner_id": owner_id,
            "invite_code": invite_code,
            "max_members": max_members,
            "is_global": False,
            "avatar": avatar,
            "status": _GROUP_STATUS_ACTIVE,
            "member_count": 0,
            "suspended_at": None,
            "suspended_by": None,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(Item=item)
        self.add_member(group_id, owner_id)
        return self.get_group(group_id) or item

    def update_group(self, group_id: str, **fields: Any) -> None:
        if not fields:
            return
        names: dict[str, str] = {"#updated": "updated_at"}
        values: dict[str, Any] = {":now": _now_iso()}
        sets = ["#updated = :now"]
        i = 0
        for key, val in fields.items():
            attr = f"#f{i}"
            val_attr = f":v{i}"
            names[attr] = key
            values[val_attr] = val
            sets.append(f"{attr} = {val_attr}")
            i += 1
        self._table.update_item(
            Key={"partition_key": f"GROUP#{group_id}", "sort_key": "DETAILS"},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    def mark_deleted(self, group_id: str) -> None:
        now = _now_iso()
        self.update_group(group_id, status=_GROUP_STATUS_DELETED, deleted_at=now)

    def mark_suspended(self, group_id: str, *, suspended_by: str) -> None:
        now = _now_iso()
        self.update_group(
            group_id,
            status=_GROUP_STATUS_SUSPENDED,
            suspended_at=now,
            suspended_by=suspended_by,
        )

    def mark_active(self, group_id: str) -> None:
        self.update_group(
            group_id,
            status=_GROUP_STATUS_ACTIVE,
            suspended_at=None,
            suspended_by=None,
        )

    def delete_all_memberships(self, group_id: str) -> None:
        for uid in self.list_member_user_ids(group_id):
            self._table.delete_item(
                Key={
                    "partition_key": f"GROUP#{group_id}",
                    "sort_key": f"MEMBER#{uid}",
                },
            )
        self.update_group(group_id, member_count=0)

    def list_active_groups(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Admin: todos los grupos no eliminados (scan completo, luego recorta)."""
        items: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": (
                Attr("sort_key").eq("DETAILS") & Attr("status").ne(_GROUP_STATUS_DELETED)
            ),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        items.sort(key=lambda g: (not g.get("is_global"), (g.get("name") or "").lower()))
        return items[:limit]
