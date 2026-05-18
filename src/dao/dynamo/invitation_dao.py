"""INVITE#<id>/DETAILS e INVITE_USE#<id>/USER#<user> (SPEC-020)."""
from __future__ import annotations

import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from src.dao.dynamo.table import get_table
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "ProdeTable")
_INVITE_ALPHABET = string.ascii_letters + string.digits
_INVITE_TTL_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def generate_invite_id(dao: InvitationDAO | None = None) -> str:
    """Short UUID 8 chars; verifica unicidad en DynamoDB."""
    checker = dao or InvitationDAO()
    for _ in range(5):
        candidate = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
        if not checker.exists(candidate):
            return candidate
    raise RuntimeError("No se pudo generar invite_id único tras 5 intentos")


class InvitationDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def exists(self, invite_id: str) -> bool:
        resp = self._table.get_item(
            Key={"partition_key": f"INVITE#{invite_id}", "sort_key": "DETAILS"},
            ProjectionExpression="invite_id",
        )
        return "Item" in resp

    def get(self, invite_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"INVITE#{invite_id}", "sort_key": "DETAILS"},
        )
        return resp.get("Item")

    def create(
        self,
        *,
        invite_id: str,
        group_id: str,
        created_by: str,
        max_uses: int,
        group_name: str,
        inviter_alias: str,
        ttl_hours: int = 24,
    ) -> dict[str, Any]:
        now = _now()
        created_at = now.isoformat()
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        ttl_expiry = int((now + timedelta(days=_INVITE_TTL_DAYS)).timestamp())

        item = {
            "partition_key": f"INVITE#{invite_id}",
            "sort_key": "DETAILS",
            "invite_id": invite_id,
            "group_id": group_id,
            "created_by": created_by,
            "created_at": created_at,
            "max_uses": max_uses,
            "uses_count": 0,
            "status": "ACTIVE",
            "expires_at": expires_at,
            "ttl_expiry": ttl_expiry,
            "group_name": group_name,
            "inviter_alias": inviter_alias,
        }
        self._table.put_item(Item=item)
        return item

    def update_status(self, invite_id: str, status: str) -> None:
        self._table.update_item(
            Key={"partition_key": f"INVITE#{invite_id}", "sort_key": "DETAILS"},
            UpdateExpression="SET #s = :status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status},
        )

    def increment_uses(self, invite_id: str) -> dict[str, Any]:
        """
        ADD uses_count atómico. EXHAUSTED si alcanza max_uses.
        ConditionExpression: cupo y ACTIVE.
        """
        now_iso = _now_iso()
        try:
            resp = self._table.update_item(
                Key={"partition_key": f"INVITE#{invite_id}", "sort_key": "DETAILS"},
                UpdateExpression=(
                    "ADD uses_count :one SET updated_at = :now"
                ),
                ConditionExpression=(
                    "#s = :active AND uses_count < max_uses AND expires_at > :now"
                ),
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":one": 1,
                    ":active": "ACTIVE",
                    ":now": now_iso,
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError("INVITATION_NOT_USABLE") from exc
            raise

        item = resp["Attributes"]
        if int(item["uses_count"]) >= int(item["max_uses"]):
            self._table.update_item(
                Key={"partition_key": f"INVITE#{invite_id}", "sort_key": "DETAILS"},
                UpdateExpression="SET #s = :exhausted",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":exhausted": "EXHAUSTED"},
            )
            item["status"] = "EXHAUSTED"
        return item

    def record_use(
        self,
        invite_id: str,
        user_id: str,
        group_joined: str,
        platform: str = "TELEGRAM",
    ) -> None:
        used_at = _now_iso()
        self._table.put_item(
            Item={
                "partition_key": f"INVITE_USE#{invite_id}",
                "sort_key": f"USER#{user_id}",
                "invite_id": invite_id,
                "user_id": user_id,
                "used_at": used_at,
                "group_joined": group_joined,
                "platform": platform,
            },
        )

    def list_by_creator(
        self, created_by: str, *, status_filter: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        resp = self._table.query(
            IndexName="GSI-5-invites-by-creator",
            KeyConditionExpression=Key("created_by").eq(created_by),
            ScanIndexForward=False,
            Limit=limit,
        )
        items = resp.get("Items", [])
        if status_filter:
            items = [i for i in items if i.get("status") == status_filter]
        return items

    def list_uses(self, invite_id: str, limit: int = 50) -> list[dict[str, Any]]:
        resp = self._table.query(
            IndexName="GSI-6-invite-uses-by-invite",
            KeyConditionExpression=Key("invite_id").eq(invite_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])

    def revoke(self, invite_id: str) -> bool:
        try:
            self._table.update_item(
                Key={"partition_key": f"INVITE#{invite_id}", "sort_key": "DETAILS"},
                UpdateExpression="SET #s = :revoked",
                ConditionExpression="#s = :active",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":active": "ACTIVE", ":revoked": "REVOKED"},
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
