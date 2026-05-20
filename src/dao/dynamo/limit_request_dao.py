"""LIMIT_REQ# — pedidos de extensión de límites (SPEC-018 / SPEC-026)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.dao.dynamo.table import get_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LimitRequestDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def create(
        self,
        *,
        requester_user_id: str,
        request_type: str,
        target_group_id: str | None = None,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        now = _now_iso()
        item = {
            "partition_key": f"LIMIT_REQ#{request_id}",
            "sort_key": "DETAILS",
            "request_id": request_id,
            "requester_user_id": requester_user_id,
            "request_type": request_type,
            "target_group_id": target_group_id,
            "status": "PENDING",
            "admin_response": None,
            "created_at": now,
            "resolved_at": None,
        }
        self._table.put_item(Item=item)
        return item
