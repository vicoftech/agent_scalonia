#!/usr/bin/env python3
"""
Bootstrap del admin global — SPEC-020 (un solo uso, idempotente).

Uso:
  python scripts/bootstrap_admin.py --chat-id 123456789 --env dev

NUNCA almacena chat_id en texto plano — solo SHA-256 en DynamoDB y SSM.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def bootstrap(chat_id: int, env: str, table_name: str | None = None) -> None:
    table_id = table_name or os.environ.get("DYNAMODB_TABLE") or f"ProdeTable-{env}"
    dynamodb = boto3.resource("dynamodb")
    ssm = boto3.client("ssm")
    table = dynamodb.Table(table_id)

    platform_id_hash = hashlib.sha256(str(chat_id).encode()).hexdigest()

    existing = table.query(
        IndexName="GSI-1-platform",
        KeyConditionExpression=(
            Key("platform").eq("TELEGRAM") & Key("platform_id_hash").eq(platform_id_hash)
        ),
        Limit=1,
    )
    if existing.get("Items"):
        admin_user_id = existing["Items"][0]["user_id"]
        logger.info("Admin ya existe user_id=%s — promoviendo is_admin + SSM", admin_user_id[:8])
        now = _now_iso()
        table.update_item(
            Key={"partition_key": f"USER#{admin_user_id}", "sort_key": "PROFILE"},
            UpdateExpression=(
                "SET is_admin = :t, #st = :active, onboarding_stage = :m3, updated_at = :now"
            ),
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":t": True,
                ":active": "ACTIVE",
                ":m3": "M3_COMPLETE",
                ":now": now,
            },
        )
        try:
            table.put_item(
                Item={
                    "partition_key": "GROUP#GLOBAL",
                    "sort_key": f"MEMBER#{admin_user_id}",
                    "group_id": "GLOBAL",
                    "user_id": admin_user_id,
                    "joined_at": now,
                },
                ConditionExpression="attribute_not_exists(partition_key)",
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            pass
    else:
        admin_user_id = str(uuid4())
        now = _now_iso()
        table.put_item(
            Item={
                "partition_key": f"USER#{admin_user_id}",
                "sort_key": "PROFILE",
                "user_id": admin_user_id,
                "alias": "Admin",
                "platform": "TELEGRAM",
                "platform_id_hash": platform_id_hash,
                "status": "ACTIVE",
                "tier": "FREE",
                "is_admin": True,
                "groups_owned": 0,
                "invites_sent": 0,
                "onboarding_stage": "M3_COMPLETE",
                "notifications_enabled": True,
                "total_points": 0,
                "match_points": 0,
                "trivia_points": 0,
                "created_at": now,
                "updated_at": now,
            }
        )
        table.put_item(
            Item={
                "partition_key": "GROUP#GLOBAL",
                "sort_key": f"MEMBER#{admin_user_id}",
                "group_id": "GLOBAL",
                "user_id": admin_user_id,
                "joined_at": now,
            }
        )
        logger.info("Admin creado user_id=%s", admin_user_id[:8])

    prefix = f"/prode-mundial/{env}"
    for name, value in [
        (f"{prefix}/admin_user_id", admin_user_id),
        (f"{prefix}/admin_platform_id_hash", platform_id_hash),
    ]:
        ssm.put_parameter(Name=name, Value=value, Type="String", Overwrite=True)
        logger.info("SSM actualizado: %s", name)

    logger.info("Bootstrap completado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", type=int, required=True)
    parser.add_argument("--env", default="dev", choices=["dev", "staging", "prod"])
    parser.add_argument("--table", default="", help="Override DYNAMODB_TABLE")
    args = parser.parse_args()
    bootstrap(args.chat_id, args.env, args.table or None)
