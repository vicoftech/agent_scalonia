"""USER#<uuid>/PROFILE — lookups y alta de usuarios (SPEC-018 / SPEC-020)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

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
        m1_step: str = "awaiting_alias",
        tg_chat_id: int | None = None,
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
            "m1_step": m1_step,
            "notifications_enabled": True,
            "total_points": 0,
            "match_points": 0,
            "trivia_points": 0,
            "created_at": now,
            "updated_at": now,
        }
        if tg_chat_id is not None:
            item["tg_chat_id"] = int(tg_chat_id)
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(partition_key)",
        )
        self._write_platform_lookup("TELEGRAM", platform_id_hash, user_id)
        return item

    def set_pending_first_agent_turn(self, user_id: str, *, pending: bool = True) -> None:
        """Tras /start con invitación: primer mensaje al agente sin repetir bienvenida."""
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
            UpdateExpression="SET pending_first_agent_turn = :p, updated_at = :now",
            ExpressionAttributeValues={":p": pending, ":now": _now_iso()},
        )

    def update_profile(self, user_id: str, **fields: Any) -> None:
        """Actualiza campos del PROFILE (onboarding, preferencias)."""
        if not fields:
            return
        names: dict[str, str] = {"#updated": "updated_at"}
        values: dict[str, Any] = {":now": _now_iso()}
        sets: list[str] = ["#updated = :now"]
        i = 0
        for key, val in fields.items():
            attr = f"#f{i}"
            val_attr = f":v{i}"
            names[attr] = key
            if val is None:
                sets.append(f"REMOVE {attr}")
                i += 1
                continue
            values[val_attr] = val
            sets.append(f"{attr} = {val_attr}")
            i += 1
        remove_parts = [s for s in sets if s.startswith("REMOVE")]
        set_parts = [s for s in sets if not s.startswith("REMOVE")]
        expr_parts = []
        if set_parts:
            expr_parts.append("SET " + ", ".join(set_parts))
        if remove_parts:
            # DynamoDB: una sola cláusula REMOVE attr1, attr2, ...
            remove_attrs = [part.split(" ", 1)[1] for part in remove_parts]
            expr_parts.append("REMOVE " + ", ".join(remove_attrs))
        if not expr_parts:
            return
        update_expr = " ".join(expr_parts)
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    def find_by_alias(self, alias: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Usuarios ACTIVE con alias (comparación case-insensitive, scan MVP)."""
        needle = (alias or "").strip().lower()
        if not needle:
            return []
        matches: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("sort_key").eq("PROFILE") & Attr("alias").exists(),
            "ProjectionExpression": "user_id, alias, #st, is_admin",
            "ExpressionAttributeNames": {"#st": "status"},
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                if (item.get("alias") or "").strip().lower() == needle:
                    if item.get("status") == "ACTIVE":
                        matches.append(item)
            if len(matches) >= limit or not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return matches[:limit]

    def resolve_alias(self, alias: str) -> dict[str, Any] | None:
        """Un único perfil ACTIVE; None si no existe."""
        hits = self.find_by_alias(alias, limit=2)
        if len(hits) == 1:
            return self.get_profile(hits[0]["user_id"]) or hits[0]
        return None

    def find_alias_suggestions(self, alias: str, *, limit: int = 3) -> list[str]:
        """Coincidencias parciales para mensajes de error."""
        needle = (alias or "").strip().lower()
        if len(needle) < 2:
            return []
        seen: list[str] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("sort_key").eq("PROFILE") & Attr("alias").exists(),
            "ProjectionExpression": "alias, #st",
            "ExpressionAttributeNames": {"#st": "status"},
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                if item.get("status") != "ACTIVE":
                    continue
                a = (item.get("alias") or "").strip()
                if needle in a.lower() and a not in seen:
                    seen.append(a)
            if len(seen) >= limit or not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return seen[:limit]

    def alias_taken(self, alias: str, *, exclude_user_id: str | None = None) -> bool:
        """Unicidad de alias (scan MVP — pocos usuarios en dev)."""
        target = (alias or "").strip()
        if not target:
            return False
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("sort_key").eq("PROFILE") & Attr("alias").eq(target),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                if exclude_user_id and item.get("user_id") == exclude_user_id:
                    continue
                return True
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return False

    def set_telegram_chat_id(self, user_id: str, chat_id: int) -> None:
        """
        ID de chat de Telegram para envíos proactivos (trivias, recordatorios).
        Solo DynamoDB — no se replica a Aurora. No loguear este valor.
        """
        if not user_id or chat_id is None:
            return
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
            UpdateExpression="SET tg_chat_id = :cid, updated_at = :now",
            ExpressionAttributeValues={":cid": int(chat_id), ":now": _now_iso()},
        )

    def list_telegram_delivery_targets(self, member_user_ids: list[str]) -> list[dict[str, Any]]:
        """Usuarios con notificaciones activas y tg_chat_id conocido."""
        targets: list[dict[str, Any]] = []
        for uid in member_user_ids:
            profile = self.get_profile(uid) or {}
            if profile.get("notifications_enabled") is False:
                continue
            chat_id = profile.get("tg_chat_id")
            if chat_id is None:
                continue
            targets.append({"user_id": uid, "tg_chat_id": int(chat_id)})
        return targets

    def get_answered_question_fingerprints(self, user_id: str) -> set[str]:
        profile = self.get_profile(user_id) or {}
        raw = profile.get("trivia_answered_fps") or []
        return {str(x) for x in raw if x}

    def mark_answered_question_fingerprint(self, user_id: str, fingerprint: str) -> None:
        """Evita sumar puntos dos veces por la misma pregunta (distintos trivia_id)."""
        if not fingerprint:
            return
        profile = self.get_profile(user_id) or {}
        existing = list(profile.get("trivia_answered_fps") or [])
        if fingerprint not in existing:
            existing.append(fingerprint)
        existing = existing[-50:]
        self.update_profile(user_id, trivia_answered_fps=existing)

    def add_match_points(self, user_id: str, points: int) -> None:
        """Suma (o resta) puntos de partidos en PROFILE."""
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
            UpdateExpression="SET updated_at = :now ADD match_points :p, total_points :p",
            ExpressionAttributeValues={":p": int(points), ":now": _now_iso()},
        )

    def add_trivia_round(self, user_id: str, *, points: int, count_round: bool = True) -> None:
        """Suma puntos de trivia y opcionalmente incrementa rondas del día."""
        vals: dict[str, Any] = {":p": points, ":now": _now_iso()}
        add_expr = "trivia_points :p, total_points :p"
        if count_round:
            add_expr += ", trivia_rounds_today :one"
            vals[":one"] = 1
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
            UpdateExpression=f"SET updated_at = :now ADD {add_expr}",
            ExpressionAttributeValues=vals,
        )

    def consume_pending_first_agent_turn(self, user_id: str) -> bool:
        """Lee y limpia el flag (un solo turno post-/start)."""
        profile = self.get_profile(user_id)
        if not profile or not profile.get("pending_first_agent_turn"):
            return False
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": "PROFILE"},
            UpdateExpression="REMOVE pending_first_agent_turn SET updated_at = :now",
            ExpressionAttributeValues={":now": _now_iso()},
        )
        return True
