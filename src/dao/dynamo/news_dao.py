"""NEWS# / NEWS_DEDUP# / NEWS_ENG# — SPEC-2026-046."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from src.dao.dynamo.table import get_table

NEWS_DEDUP_TTL_SECONDS = 30 * 86400


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def url_hash(url: str) -> str:
    return hashlib.sha256((url or "").strip().encode()).hexdigest()


class NewsDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def get_details(self, news_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"NEWS#{news_id}", "sort_key": "DETAILS"},
        )
        return resp.get("Item")

    def put_details(self, news_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        item = {
            "partition_key": f"NEWS#{news_id}",
            "sort_key": "DETAILS",
            "news_id": news_id,
            "published_at": data.get("published_at") or now,
            "like_count": int(data.get("like_count") or 0),
            "read_count": int(data.get("read_count") or 0),
            "broadcast_sent": int(data.get("broadcast_sent") or 0),
        }
        for key in (
            "source_type",
            "automated_slot",
            "run_date",
            "headline",
            "summary",
            "article_url",
            "url_hash",
            "image_url",
            "category",
            "subcategory",
            "source_label",
            "relevance_score",
            "published_by",
            "telegram_file_id",
        ):
            if key in data and data[key] is not None:
                item[key] = data[key]
        self._table.put_item(Item=item)
        return item

    def increment_like_count(self, news_id: str, delta: int = 1) -> int:
        resp = self._table.update_item(
            Key={"partition_key": f"NEWS#{news_id}", "sort_key": "DETAILS"},
            UpdateExpression="ADD like_count :d SET updated_at = :now",
            ExpressionAttributeValues={":d": delta, ":now": _now_iso()},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp.get("Attributes", {}).get("like_count") or 0)

    def increment_read_count(self, news_id: str, delta: int = 1) -> int:
        resp = self._table.update_item(
            Key={"partition_key": f"NEWS#{news_id}", "sort_key": "DETAILS"},
            UpdateExpression="ADD read_count :d SET updated_at = :now",
            ExpressionAttributeValues={":d": delta, ":now": _now_iso()},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp.get("Attributes", {}).get("read_count") or 0)

    def set_telegram_file_id(self, news_id: str, file_id: str) -> None:
        self._table.update_item(
            Key={"partition_key": f"NEWS#{news_id}", "sort_key": "DETAILS"},
            UpdateExpression="SET telegram_file_id = :f, updated_at = :now",
            ExpressionAttributeValues={":f": file_id, ":now": _now_iso()},
        )

    def set_broadcast_sent(self, news_id: str, count: int) -> None:
        self._table.update_item(
            Key={"partition_key": f"NEWS#{news_id}", "sort_key": "DETAILS"},
            UpdateExpression="SET broadcast_sent = :n, updated_at = :now",
            ExpressionAttributeValues={":n": int(count), ":now": _now_iso()},
        )

    def is_url_published(self, article_url: str) -> bool:
        h = url_hash(article_url)
        resp = self._table.get_item(
            Key={"partition_key": f"NEWS_DEDUP#{h}", "sort_key": "META"},
        )
        return "Item" in resp

    def mark_url_published(self, article_url: str, news_id: str) -> None:
        h = url_hash(article_url)
        self._table.put_item(
            Item={
                "partition_key": f"NEWS_DEDUP#{h}",
                "sort_key": "META",
                "news_id": news_id,
                "article_url": article_url,
                "ttl_expiry": int(time.time()) + NEWS_DEDUP_TTL_SECONDS,
            }
        )

    def put_like(self, news_id: str, user_id: str) -> bool:
        try:
            self._table.put_item(
                Item={
                    "partition_key": f"NEWS_ENG#{news_id}",
                    "sort_key": f"LIKE#{user_id}",
                    "news_id": news_id,
                    "user_id": user_id,
                    "created_at": _now_iso(),
                },
                ConditionExpression="attribute_not_exists(partition_key)",
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def has_like(self, news_id: str, user_id: str) -> bool:
        resp = self._table.get_item(
            Key={
                "partition_key": f"NEWS_ENG#{news_id}",
                "sort_key": f"LIKE#{user_id}",
            },
        )
        return "Item" in resp

    def put_read(self, news_id: str, user_id: str) -> bool:
        try:
            self._table.put_item(
                Item={
                    "partition_key": f"NEWS_ENG#{news_id}",
                    "sort_key": f"READ#{user_id}",
                    "news_id": news_id,
                    "user_id": user_id,
                    "created_at": _now_iso(),
                },
                ConditionExpression="attribute_not_exists(partition_key)",
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def list_published_on_date(self, run_date: str) -> list[dict[str, Any]]:
        """Noticias con run_date ART (admin + automated)."""
        items: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("sort_key").eq("DETAILS") & Attr("run_date").eq(run_date),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return items
