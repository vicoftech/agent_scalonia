#!/usr/bin/env python3
"""
Elimina usuarios y datos ligados en DynamoDB; conserva admin, GROUP#GLOBAL y partidos MATCH#.
También borra todas las trivias (TRIVIA#, TRIVIA_ANSWER#), resetea puntajes del admin
y limpia JOB_CTRL#DAILY_TRIVIA.

Uso:
  python scripts/purge_non_admin_users.py --env dev --profile asap_dev --dry-run
  python scripts/purge_non_admin_users.py --env dev --profile asap_dev --execute
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GLOBAL_GROUP_ID = "GLOBAL"


def _session(profile: str | None, region: str):
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def resolve_admin_user_id(table, ssm, env: str) -> tuple[str, str | None]:
    """Retorna (admin_user_id, platform_id_hash)."""
    try:
        uid = ssm.get_parameter(Name=f"/prode-mundial/{env}/admin_user_id")["Parameter"]["Value"]
        try:
            ph = ssm.get_parameter(Name=f"/prode-mundial/{env}/admin_platform_id_hash")[
                "Parameter"
            ]["Value"]
        except ssm.exceptions.ParameterNotFound:
            ph = None
        profile = table.get_item(
            Key={"partition_key": f"USER#{uid}", "sort_key": "PROFILE"},
        ).get("Item")
        if profile and profile.get("is_admin"):
            return uid, ph or profile.get("platform_id_hash")
        logger.warning("SSM admin_user_id sin is_admin en PROFILE — buscando por scan")
    except ssm.exceptions.ParameterNotFound:
        pass

    scan = table.scan(
        FilterExpression=Attr("sort_key").eq("PROFILE") & Attr("is_admin").eq(True),
        ProjectionExpression="user_id, platform_id_hash",
    )
    items = scan.get("Items", [])
    while "LastEvaluatedKey" in scan:
        scan = table.scan(
            FilterExpression=Attr("sort_key").eq("PROFILE") & Attr("is_admin").eq(True),
            ProjectionExpression="user_id, platform_id_hash",
            ExclusiveStartKey=scan["LastEvaluatedKey"],
        )
        items.extend(scan.get("Items", []))

    if not items:
        raise SystemExit("No se encontró admin (is_admin=True). Ejecutá bootstrap_admin.py primero.")
    if len(items) > 1:
        logger.warning("Varios admins en tabla; usando el primero: %s", items[0]["user_id"][:8])
    admin = items[0]
    return admin["user_id"], admin.get("platform_id_hash")


def _user_id_from_pk(pk: str) -> str | None:
    if pk.startswith("USER#"):
        return pk[5:]
    return None


def _member_user_id(sk: str) -> str | None:
    if sk.startswith("MEMBER#"):
        return sk[7:]
    return None


def should_delete(item: dict[str, Any], admin_id: str, admin_hash: str | None) -> bool:
    pk = item.get("partition_key", "")
    sk = item.get("sort_key", "")

    if pk.startswith("MATCH#"):
        return False
    if pk.startswith("TRIVIA#") or pk.startswith("TRIVIA_ANSWER#"):
        return True
    if pk == "CONFIG#TRIVIA" and sk == "USED_QUESTION_FPS":
        return True
    if pk.startswith("JOB_CTRL#DAILY_TRIVIA"):
        return True
    if pk.startswith("CACHE#"):
        return False
    if pk.startswith("JOB_CTRL#"):
        return False

    if pk == f"GROUP#{GLOBAL_GROUP_ID}" and sk == "DETAILS":
        return False
    if pk == f"GROUP#{GLOBAL_GROUP_ID}" and sk == f"MEMBER#{admin_id}":
        return False

    if pk.startswith("USER#"):
        uid = _user_id_from_pk(pk)
        if uid != admin_id:
            return True
        return sk != "PROFILE"

    if pk.startswith("PLATFORM#"):
        if admin_hash and admin_hash in pk:
            return False
        return True

    if pk.startswith("INVITE#") or pk.startswith("INVITE_USE#"):
        return True

    if sk.startswith("MEMBER#"):
        return _member_user_id(sk) != admin_id

    if pk.startswith("GROUP#"):
        return True

    if pk.startswith("RANKING"):
        if sk.startswith("USER#"):
            return sk != f"USER#{admin_id}"
        return True

    if pk.startswith("WS#") or pk.startswith("LIMIT_REQ#"):
        return True

    return False


def purge(table, admin_id: str, admin_hash: str | None, *, execute: bool) -> int:
    deleted = 0
    scanned = 0
    last_key = None

    while True:
        kwargs: dict[str, Any] = {}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        page = table.scan(**kwargs)
        for item in page.get("Items", []):
            scanned += 1
            if not should_delete(item, admin_id, admin_hash):
                continue
            deleted += 1
            key = {"partition_key": item["partition_key"], "sort_key": item["sort_key"]}
            if execute:
                table.delete_item(Key=key)
            else:
                logger.info("would delete %s / %s", key["partition_key"], key["sort_key"])

        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            break

    logger.info("Scanned %s items; %s to delete (%s)", scanned, deleted, "executed" if execute else "dry-run")
    return deleted


def reset_admin_profile(table, admin_id: str, *, execute: bool) -> None:
    """Puntajes y estado de trivia del admin en cero."""
    if not execute:
        logger.info("would reset admin PROFILE scores and trivia state")
        return
    table.update_item(
        Key={"partition_key": f"USER#{admin_id}", "sort_key": "PROFILE"},
        UpdateExpression=(
            "SET total_points = :z, match_points = :z, trivia_points = :z, "
            "trivia_rounds_today = :z, updated_at = :now "
            "REMOVE trivia_answered_fps, daily_trivia_prompted_id, "
            "trivia_rounds_reset_date"
        ),
        ExpressionAttributeValues={":z": 0, ":now": datetime.now(timezone.utc).isoformat()},
    )
    logger.info("Admin PROFILE: puntajes y trivias reseteados")


def ensure_admin_global_member(table, admin_id: str, *, execute: bool) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "partition_key": f"GROUP#{GLOBAL_GROUP_ID}",
        "sort_key": f"MEMBER#{admin_id}",
        "group_id": GLOBAL_GROUP_ID,
        "user_id": admin_id,
        "joined_at": now,
    }
    if execute:
        table.put_item(Item=item)
        logger.info("Asegurada membresía GROUP#GLOBAL/MEMBER#%s", admin_id[:8])


def main() -> None:
    p = argparse.ArgumentParser(description="Purge DynamoDB users except global admin")
    p.add_argument("--env", default="dev")
    p.add_argument("--table", default="", help="Override table name")
    p.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--dry-run", action="store_true", help="Solo listar borrados")
    p.add_argument("--execute", action="store_true", help="Aplicar borrados")
    args = p.parse_args()

    if args.execute == args.dry_run:
        p.error("Indicá exactamente uno: --dry-run o --execute")

    table_name = args.table or os.environ.get("DYNAMODB_TABLE") or f"ProdeTable-{args.env}"
    sess = _session(args.profile or None, args.region)
    table = sess.resource("dynamodb").Table(table_name)
    ssm = sess.client("ssm")

    admin_id, admin_hash = resolve_admin_user_id(table, ssm, args.env)
    logger.info("Admin conservado: user_id=%s (hash prefix %s)", admin_id[:8], (admin_hash or "?")[:12])

    n = purge(table, admin_id, admin_hash, execute=args.execute)
    reset_admin_profile(table, admin_id, execute=args.execute)
    ensure_admin_global_member(table, admin_id, execute=args.execute)

    if not args.execute:
        logger.info("Dry-run completo. Repetí con --execute para borrar.")
    else:
        logger.info(
            "Listo: solo admin, sin trivias, puntajes en cero. Probá invitaciones y /trivia."
        )


if __name__ == "__main__":
    main()
