"""ProdeBriefTable — TEAM_BRIEF y MATCH_BRIEF (SPEC-2026-045)."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from src.dao.dynamo.table import get_table

BRIEF_TTL_SECONDS = 172800  # 48 h


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brief_table_name() -> str:
    return os.environ.get("BRIEF_TABLE", f"ProdeBriefTable-{os.environ.get('ENV', 'dev')}")


class TeamBriefDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name or _brief_table_name())

    def get_current(self, team_code: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={
                "partition_key": f"TEAM_BRIEF#{team_code.strip().upper()}",
                "sort_key": "CURRENT",
            }
        )
        return resp.get("Item")

    def put_current(self, team_code: str, data: dict[str, Any]) -> dict[str, Any]:
        code = team_code.strip().upper()
        now = _now_iso()
        item = {
            "partition_key": f"TEAM_BRIEF#{code}",
            "sort_key": "CURRENT",
            "team_code": code,
            "generated_at": data.get("generated_at") or now,
            "generation_mode": "DAILY",
            "brief_markdown": data.get("brief_markdown") or "",
            "ttl_expiry": int(time.time()) + BRIEF_TTL_SECONDS,
        }
        for key in (
            "team_name",
            "brief_sections",
            "roster",
            "recent_record",
            "kb_chunks_used",
            "web_queries_used",
            "roster_completeness",
        ):
            if key in data and data[key] is not None:
                item[key] = data[key]
        self._table.put_item(Item=item)
        return item


class MatchBriefDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name or _brief_table_name())

    def get_current(self, match_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={
                "partition_key": f"MATCH_BRIEF#{match_id}",
                "sort_key": "CURRENT",
            }
        )
        return resp.get("Item")

    def put_current(self, match_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        frozen = bool(data.get("brief_frozen"))
        item: dict[str, Any] = {
            "partition_key": f"MATCH_BRIEF#{match_id}",
            "sort_key": "CURRENT",
            "match_id": match_id,
            "generated_at": data.get("generated_at") or now,
            "brief_markdown": data.get("brief_markdown") or "",
            "home_team": data.get("home_team"),
            "away_team": data.get("away_team"),
            "kickoff_utc": data.get("kickoff_utc"),
            "home_strengths": data.get("home_strengths") or [],
            "home_weaknesses": data.get("home_weaknesses") or [],
            "away_strengths": data.get("away_strengths") or [],
            "away_weaknesses": data.get("away_weaknesses") or [],
            "ia_prediction_line": data.get("ia_prediction_line") or "",
            "ia_prediction_rationale": data.get("ia_prediction_rationale") or "",
            "team_brief_refs": data.get("team_brief_refs") or {},
            "match_status_at_generation": data.get("match_status_at_generation"),
            "brief_frozen": frozen,
        }
        if not frozen:
            item["ttl_expiry"] = int(time.time()) + BRIEF_TTL_SECONDS
        if data.get("frozen_at"):
            item["frozen_at"] = data["frozen_at"]
        self._table.put_item(Item=item)
        return item

    def freeze(self, match_id: str) -> None:
        existing = self.get_current(match_id)
        if not existing:
            return
        existing["brief_frozen"] = True
        existing["frozen_at"] = _now_iso()
        existing.pop("ttl_expiry", None)
        self.put_current(match_id, existing)
