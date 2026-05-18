"""USER#<uuid>/PROFILE — lookups y alta de usuarios (SPEC-018 / SPEC-020)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from src.dao.dynamo.table import get_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _platform_lookup_key(platform: str, platform_id_hash: str) -> dict[str, str]:
    return {
        "partition_key": f"PLATFORM#{platform}#{platform_id_hash}",
        "sort_key": "USER",
    }


class UserDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def _write_platform_lookup(
        self, platform: str, platform_id_hash: str, user_id: str
    ) -> None:
        """GetItem consistente — evita fallos del GSI eventual justo después del /start."""
        self._table.put_item(
            Item={
                **_platform_lookup_key(platform, platform_id_hash),
                "user_id": user_id,
                "platform": platform,
                "platform_id_hash": platform_id_hash,
            }
        )

    def get_by_platform_hash(self, platform: str, platform_id_hash: str) -> dict[str, Any] | None:
        lookup = self._table.get_item(
            Key=_platform_lookup_key(platform, platform_id_hash),
            ConsistentRead=True,
        )
        if lookup.get("Item", {}).get("user_id"):
            return self.get_profile(lookup["Item"]["user_id"])

        for attempt in range(4):
            resp = self._table.query(
                IndexName="GSI-1-platform",
                KeyConditionExpression=(
                    Key("platform").eq(platform)
                    & Key("platform_id_hash").eq(platform_id_hash)
                ),
                Limit=1,
            )
            items = resp.get("Items", [])
            if items:
                hit = items[0]
                if hit.get("user_id"):
                    self._write_platform_lookup(platform, platform_id_hash, hit["user_id"])
                if "status" not in hit and hit.get("user_id"):
                    return self.get_profile(hit["user_id"])
                return hit
            if attempt < 3:
                time.sleep(0.12 * (attempt + 1))
        return None

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
        self._write_platform_lookup("TELEGRAM", platform_id_hash, user_id)
        return item
