"""USER#<uuid>/PROFILE — lookups y alta de usuarios (SPEC-018 / SPEC-020)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "ProdeTable")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserDAO:
    def __init__(self, table_name: str | None = None):
        self._table = boto3.resource("dynamodb").Table(table_name or TABLE_NAME)

    def get_by_platform_hash(self, platform: str, platform_id_hash: str) -> dict[str, Any] | None:
        resp = self._table.query(
            IndexName="GSI-1-platform",
            KeyConditionExpression=(
                Key("platform").eq(platform) & Key("platform_id_hash").eq(platform_id_hash)
            ),
            Limit=1,
        )
        items = resp.get("Items", [])
        if not items:
            return None
        hit = items[0]
        # GSI-1 solo proyecta user_id/alias/notifications — status e is_admin vienen del PROFILE.
        if "status" not in hit and hit.get("user_id"):
            return self.get_profile(hit["user_id"])
        return hit

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
        )
        return resp.get("Item")

    def promote_global_admin(self, user_id: str) -> None:
        """Marca is_admin y onboarding completo (bootstrap / recuperación)."""
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
            UpdateExpression=(
                "SET is_admin = :t, #st = :active, onboarding_stage = :m3, updated_at = :now"
            ),
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":t": True,
                ":active": "ACTIVE",
                ":m3": "M3_COMPLETE",
                ":now": _now_iso(),
            },
        )

    def create_telegram_user(
        self,
        user_id: str,
        platform_id_hash: str,
        *,
        alias: str = "Jugador",
        onboarding_stage: str = "M1_PENDING",
    ) -> dict[str, Any]:
        now = _now_iso()
        item = {
            "partition_key": f"USER#{user_id}",
            "sort_key": "PROFILE",
            "user_id": user_id,
            "alias": alias,
            "platform": "TELEGRAM",
            "platform_id_hash": platform_id_hash,
            "status": "ACTIVE",
            "tier": "FREE",
            "is_admin": False,
            "groups_owned": 0,
            "invites_sent": 0,
            "onboarding_stage": onboarding_stage,
            "notifications_enabled": True,
            "total_points": 0,
            "match_points": 0,
            "trivia_points": 0,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(partition_key)",
        )
        return item
