"""IA_PURCHASE# — auditoría de acreditaciones Ask IA (SPEC-2026-043)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.dao.dynamo.table import get_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IaPurchaseDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def record_proof_submission(
        self,
        *,
        user_id: str,
        alias: str,
        credits_requested: int,
        amount_ars: int,
        telegram_file_id: str,
        payment_alias: str,
        file_kind: str,
    ) -> str:
        purchase_id = str(uuid.uuid4())
        self._table.put_item(
            Item={
                "partition_key": f"IA_PURCHASE#{purchase_id}",
                "sort_key": "DETAILS",
                "purchase_id": purchase_id,
                "user_id": user_id,
                "alias": alias,
                "credits_granted": 0,
                "credits_requested": int(credits_requested),
                "amount_ars": int(amount_ars),
                "telegram_file_id": telegram_file_id,
                "file_kind": file_kind,
                "payment_alias": payment_alias,
                "source": "PROOF_SUBMITTED",
                "status": "PENDING_ADMIN",
                "created_at": _now_iso(),
            }
        )
        return purchase_id

    def record_auto_purchase(
        self,
        *,
        user_id: str,
        alias: str,
        credits_granted: int,
        amount_ars: int,
        telegram_file_id: str,
        payment_alias: str,
    ) -> str:
        purchase_id = str(uuid.uuid4())
        self._table.put_item(
            Item={
                "partition_key": f"IA_PURCHASE#{purchase_id}",
                "sort_key": "DETAILS",
                "purchase_id": purchase_id,
                "user_id": user_id,
                "alias": alias,
                "credits_granted": int(credits_granted),
                "amount_ars": int(amount_ars),
                "telegram_file_id": telegram_file_id,
                "payment_alias": payment_alias,
                "source": "AUTO",
                "created_at": _now_iso(),
            }
        )
        return purchase_id
