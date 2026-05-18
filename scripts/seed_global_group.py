#!/usr/bin/env python3
"""Crea GROUP#GLOBAL/DETAILS si no existe (idempotente)."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


def seed(env: str, table_name: str | None, admin_user_id: str) -> None:
    table_id = table_name or os.environ.get("DYNAMODB_TABLE") or f"ProdeTable-{env}"
    table = boto3.resource("dynamodb").Table(table_id)
    now = datetime.now(timezone.utc).isoformat()
    table.put_item(
        Item={
            "partition_key": "GROUP#GLOBAL",
            "sort_key": "DETAILS",
            "group_id": "GLOBAL",
            "name": "Mundial 2026 — General",
            "invite_code": None,
            "owner_id": admin_user_id,
            "max_members": None,
            "is_global": True,
            "auto_join": True,
            "active": True,
            "created_at": now,
        },
        ConditionExpression="attribute_not_exists(partition_key)",
    )
    print(f"GLOBAL group seeded in {table_id}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--env", default="dev")
    p.add_argument("--table", default="")
    p.add_argument("--admin-user-id", required=True)
    args = p.parse_args()
    try:
        seed(args.env, args.table or None, args.admin_user_id)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            print("GLOBAL group already exists")
        else:
            raise
