"""TRIVIA# / TRIVIA_ANSWER# / USER# TRIVIA session — SPEC-2026-025."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from src.dao.dynamo.table import get_table

GLOBAL_GROUP_ID = "GLOBAL"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def _difficulty_for_sync(level: str) -> str:
    return {"BASIC": "easy", "MEDIUM": "medium", "EXPERT": "hard"}.get(level.upper(), "medium")


def _strip_null_gsi_keys(item: dict[str, Any]) -> dict[str, Any]:
    """GSI-2 exige match_id tipo S; no enviar NULL en ítems sin partido."""
    mid = item.get("match_id")
    if not mid:
        item.pop("match_id", None)
    return item


class TriviaDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def put_broadcast_trivia(self, record: dict[str, Any]) -> dict[str, Any]:
        trivia_id = record.get("trivia_id") or _short_id()
        now = _now_iso()
        closes = record.get("closes_at") or now
        item = {
            "partition_key": f"TRIVIA#{trivia_id}",
            "sort_key": "DETAILS",
            "trivia_id": trivia_id,
            "type": record.get("type", "GENERAL"),
            "level": record["level"],
            "points": int(record["points"]),
            "question": record["question"],
            "options": record["options"],
            "correct": record["correct"],
            "explanation": record.get("explanation", ""),
            "topic": record.get("topic", "mundiales"),
            "source": record.get("source", "KB"),
            "group_id": record.get("group_id", GLOBAL_GROUP_ID),
            "created_by": record.get("created_by"),
            "status": record.get("status", "SENT"),
            "sent_at": record.get("sent_at", now),
            "closes_at": closes,
            "total_answers": 0,
            "correct_count": 0,
            "group_id_gsi": record.get("group_id", GLOBAL_GROUP_ID),
            "sent_at_gsi": record.get("sent_at", now),
            "ttl_expiry": int(time.time()) + 30 * 24 * 3600,
        }
        mid = record.get("match_id")
        if mid:
            item["match_id"] = mid
        self._table.put_item(Item=_strip_null_gsi_keys(item))
        return item

    def get_trivia(self, trivia_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"TRIVIA#{trivia_id}", "sort_key": "DETAILS"},
        )
        return resp.get("Item")

    def put_answer(self, *, trivia_id: str, user_id: str, answer: str, is_correct: bool, points: int) -> dict:
        now = _now_iso()
        item = {
            "partition_key": f"TRIVIA_ANSWER#{trivia_id}",
            "sort_key": f"USER#{user_id}",
            "trivia_id": trivia_id,
            "user_id": user_id,
            "answer": answer.upper()[:1],
            "is_correct": is_correct,
            "points_earned": points,
            "answered_at": now,
            "user_id_gsi": user_id,
            "answered_at_gsi": now,
            "ttl_expiry": int(time.time()) + 30 * 24 * 3600,
        }
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(partition_key)",
        )
        return item

    def has_answered(self, trivia_id: str, user_id: str) -> bool:
        resp = self._table.get_item(
            Key={
                "partition_key": f"TRIVIA_ANSWER#{trivia_id}",
                "sort_key": f"USER#{user_id}",
            },
        )
        return "Item" in resp

    def increment_trivia_stats(self, trivia_id: str, *, correct: bool) -> None:
        expr = "ADD total_answers :one"
        vals: dict[str, Any] = {":one": 1}
        if correct:
            expr += ", correct_count :one"
        self._table.update_item(
            Key={"partition_key": f"TRIVIA#{trivia_id}", "sort_key": "DETAILS"},
            UpdateExpression=expr,
            ExpressionAttributeValues=vals,
        )

    def put_play_session(self, record: dict[str, Any]) -> dict[str, Any]:
        """Sesión USER#/TRIVIA# — play personal (sync → trivia_sessions)."""
        session_id = record["session_id"]
        user_id = record["user_id"]
        level = record["level"]
        difficulty = _difficulty_for_sync(level)
        ttl = int(time.time()) + 30 * 60
        item = {
            "partition_key": f"USER#{user_id}",
            "sort_key": f"TRIVIA#{session_id}",
            "session_id": session_id,
            "user_id": user_id,
            "question": record["question"],
            "options": list(record["options"].values()) if isinstance(record["options"], dict) else record["options"],
            "options_map": record["options"],
            "correct_answer": record["correct"],
            "correct": record["correct"],
            "explanation": record.get("explanation", ""),
            "difficulty": difficulty,
            "level": level,
            "points": int(record["points"]),
            "topic": record.get("topic", "mundiales"),
            "source": record.get("source", "manual"),
            "state": "PENDING",
            "created_at": _now_iso(),
            "ttl_expiry": ttl,
        }
        mid = record.get("match_id")
        if mid:
            item["match_id"] = mid
        self._table.put_item(Item=_strip_null_gsi_keys(item))
        return item

    def get_play_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": f"TRIVIA#{session_id}"},
        )
        return resp.get("Item")

    def complete_play_session(
        self,
        user_id: str,
        session_id: str,
        *,
        answer: str,
        is_correct: bool,
        points_earned: int,
    ) -> None:
        now = _now_iso()
        self._table.update_item(
            Key={"partition_key": f"USER#{user_id}", "sort_key": f"TRIVIA#{session_id}"},
            UpdateExpression=(
                "SET #st = :answered, user_answer = :ans, is_correct = :ok, "
                "points_earned = :pts, answered_at = :now"
            ),
            ExpressionAttributeNames={"#st": "state"},
            ExpressionAttributeValues={
                ":answered": "ANSWERED",
                ":ans": answer.upper()[:1],
                ":ok": is_correct,
                ":pts": points_earned,
                ":now": now,
            },
        )

    def count_active_group_trivias(self, group_id: str) -> int:
        """Trivias GROUP con status SENT y no cerradas (scan MVP)."""
        now = _now_iso()
        count = 0
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": (
                Attr("sort_key").eq("DETAILS")
                & Attr("partition_key").begins_with("TRIVIA#")
                & Attr("group_id").eq(group_id)
                & Attr("type").eq("GROUP")
                & Attr("status").eq("SENT")
            ),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            for it in resp.get("Items", []):
                if (it.get("closes_at") or now) >= now:
                    count += 1
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return count

    def get_daily_general_for_date(self, run_date: str) -> dict[str, Any] | None:
        """Trivia DAILY_GENERAL del día calendario local (YYYY-MM-DD, ART)."""
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": (
                Attr("sort_key").eq("DETAILS")
                & Attr("partition_key").begins_with("TRIVIA#")
                & Attr("type").eq("DAILY_GENERAL")
                & (Attr("daily_date").eq(run_date) | Attr("sent_at").begins_with(run_date))
            ),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            items = resp.get("Items", [])
            if items:
                return max(items, key=lambda it: it.get("sent_at") or run_date)
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return None

    def list_group_member_user_ids(self, group_id: str) -> list[str]:
        ids: list[str] = []
        kwargs: dict[str, Any] = {
            "IndexName": "GSI-3-group-members",
            "KeyConditionExpression": Key("group_id").eq(group_id),
            "ProjectionExpression": "user_id",
        }
        while True:
            resp = self._table.query(**kwargs)
            ids.extend(r["user_id"] for r in resp.get("Items", []) if r.get("user_id"))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return ids
