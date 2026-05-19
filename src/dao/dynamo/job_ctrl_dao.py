"""JOB_CTRL# — idempotencia de jobs programados."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.dao.dynamo.table import get_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobCtrlDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def is_processed(self, job_name: str, run_date: str) -> bool:
        resp = self._table.get_item(
            Key={
                "partition_key": f"JOB_CTRL#{job_name}",
                "sort_key": run_date,
            },
        )
        return "Item" in resp

    def mark_processed(self, job_name: str, run_date: str, *, meta: dict[str, Any] | None = None) -> None:
        item = {
            "partition_key": f"JOB_CTRL#{job_name}",
            "sort_key": run_date,
            "job_name": job_name,
            "run_date": run_date,
            "processed_at": _now_iso(),
        }
        if meta:
            item.update(meta)
        self._table.put_item(Item=item)
