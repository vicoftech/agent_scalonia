"""MATCH#<uuid>/RESULT — SPEC-2026-031; RESULT_CANDIDATE — SPEC-2026-051."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from src.dao.dynamo.table import get_table
from src.models.match_result import MatchResult

CANDIDATE_SK = "RESULT_CANDIDATE"
APPROVAL_PENDING = "PENDING_REVIEW"
APPROVAL_REJECTED = "REJECTED"
APPROVAL_SUPERSEDED = "SUPERSEDED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResultDAO:
    def __init__(self, table_name: str | None = None):
        self._table = get_table(table_name)

    def get_raw(self, match_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
        )
        return resp.get("Item")

    def get_result(self, match_id: str) -> MatchResult | None:
        item = self.get_raw(match_id)
        if not item:
            return None
        return MatchResult.from_dynamo(item)

    def has_scores(self, match_id: str) -> bool:
        item = self.get_raw(match_id)
        if not item:
            return False
        return (
            item.get("result_90min_home") is not None
            or item.get("home_goals_ft") is not None
        )

    def is_complete(self, match_id: str) -> bool:
        """Completo para el collector: tiene marcador y MVP (best-effort MVP)."""
        item = self.get_raw(match_id)
        if not item or not self.has_scores(match_id):
            return False
        return bool((item.get("mvp_name") or "").strip())

    def is_scoring_done(self, match_id: str) -> bool:
        item = self.get_raw(match_id)
        return bool(item and item.get("result_processed"))

    def save_result(
        self,
        match_id: str,
        result: MatchResult,
        *,
        allow_overwrite: bool = False,
    ) -> bool:
        """
        Crea MATCH#/RESULT. Retorna True si guardó, False si ya existía (idempotente).
        """
        now = _now_iso()
        final_home = result.home_goals_aet if result.home_goals_aet is not None else result.home_goals
        final_away = result.away_goals_aet if result.away_goals_aet is not None else result.away_goals
        went_et = result.playoff_via == "ET" or result.status == "AET"
        went_pen = result.playoff_via == "PENALTIES" or result.status == "PEN"

        item: dict[str, Any] = {
            "partition_key": f"MATCH#{match_id}",
            "sort_key": "RESULT",
            "match_id": match_id,
            "result_90min_home": int(result.home_goals),
            "result_90min_away": int(result.away_goals),
            "result_final_home": int(final_home),
            "result_final_away": int(final_away),
            "went_to_et": went_et,
            "went_to_penalties": went_pen,
            "home_goals_ft": int(result.home_goals),
            "away_goals_ft": int(result.away_goals),
            "home_goals_aet": result.home_goals_aet,
            "away_goals_aet": result.away_goals_aet,
            "playoff_via": result.playoff_via,
            "playoff_winner": result.playoff_winner,
            "phase": result.phase,
            "scorers": result.scorers,
            "red_cards": int(result.red_cards),
            "goal_before_5min": result.goal_before_5min,
            "var_used": result.var_used,
            "free_kick_goal": result.free_kick_goal,
            "penalty_saved": result.penalty_saved,
            "penalty_scored": result.penalty_scored,
            "mvp_name": result.mvp_name,
            "status": result.status,
            "result_processed": bool(result.result_processed),
            "source": result.source,
            "recorded_at": result.recorded_at or now,
            "mvp_enriched_at": result.mvp_enriched_at,
            "updated_at": now,
        }
        if result.mvp_name:
            item["mvp_enriched_at"] = result.mvp_enriched_at or now

        kwargs: dict[str, Any] = {"Item": item}
        if not allow_overwrite:
            kwargs["ConditionExpression"] = "attribute_not_exists(sort_key)"

        try:
            self._table.put_item(**kwargs)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def update_mvp(self, match_id: str, mvp_name: str) -> bool:
        if not mvp_name.strip():
            return False
        now = _now_iso()
        try:
            self._table.update_item(
                Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
                UpdateExpression=(
                    "SET mvp_name = :m, mvp_enriched_at = :t, updated_at = :t"
                ),
                ConditionExpression="attribute_exists(sort_key)",
                ExpressionAttributeValues={":m": mvp_name.strip(), ":t": now},
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def delete_result(self, match_id: str) -> bool:
        try:
            self._table.delete_item(
                Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
            )
            return True
        except ClientError:
            return False

    def mark_result_processed(self, match_id: str) -> None:
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
            UpdateExpression="SET result_processed = :t, updated_at = :now",
            ExpressionAttributeValues={":t": True, ":now": _now_iso()},
        )

    def clear_result_processed(self, match_id: str) -> None:
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
            UpdateExpression="SET result_processed = :f, updated_at = :now",
            ExpressionAttributeValues={":f": False, ":now": _now_iso()},
        )

    def clear_scoring_state(self, match_id: str) -> None:
        """Permite re-puntuar y reenviar desglose (ISSUE-2026-050)."""
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
            UpdateExpression=(
                "SET result_processed = :f, updated_at = :now "
                "REMOVE scoring_breakdown_notified"
            ),
            ExpressionAttributeValues={":f": False, ":now": _now_iso()},
        )

    def is_breakdown_notified(self, match_id: str) -> bool:
        item = self.get_raw(match_id)
        return bool(item and item.get("scoring_breakdown_notified"))

    def mark_breakdown_notified(self, match_id: str) -> None:
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": "RESULT"},
            UpdateExpression=(
                "SET scoring_breakdown_notified = :t, updated_at = :now"
            ),
            ExpressionAttributeValues={":t": True, ":now": _now_iso()},
        )

    # --- SPEC-2026-051 RESULT_CANDIDATE ---

    def get_candidate_raw(self, match_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": CANDIDATE_SK},
        )
        return resp.get("Item")

    def get_candidate(self, match_id: str) -> dict[str, Any] | None:
        return self.get_candidate_raw(match_id)

    def save_candidate(
        self,
        match_id: str,
        *,
        proposed: MatchResult,
        consensus_score: float,
        source_snapshots: list[dict[str, Any]],
        warnings: list[str],
        approval_status: str = APPROVAL_PENDING,
    ) -> None:
        now = _now_iso()
        item: dict[str, Any] = {
            "partition_key": f"MATCH#{match_id}",
            "sort_key": CANDIDATE_SK,
            "match_id": match_id,
            "approval_status": approval_status,
            "proposed_result": proposed.to_dict(),
            "consensus_score": float(consensus_score),
            "source_snapshots": source_snapshots[:5],
            "warnings": warnings,
            "proposed_at": now,
            "updated_at": now,
        }
        self._table.put_item(Item=item)

    def update_candidate_draft(
        self,
        match_id: str,
        proposed: MatchResult,
        *,
        edited_by_user_id: str,
    ) -> None:
        now = _now_iso()
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": CANDIDATE_SK},
            UpdateExpression=(
                "SET proposed_result = :r, updated_at = :now, "
                "edited_by_user_id = :uid, edited_at = :now"
            ),
            ExpressionAttributeValues={
                ":r": proposed.to_dict(),
                ":now": now,
                ":uid": edited_by_user_id,
            },
        )

    def mark_candidate_status(
        self,
        match_id: str,
        status: str,
        *,
        reviewed_by_user_id: str | None = None,
    ) -> None:
        now = _now_iso()
        expr = "SET approval_status = :s, updated_at = :now, reviewed_at = :now"
        values: dict[str, Any] = {":s": status, ":now": now}
        if reviewed_by_user_id:
            expr += ", reviewed_by_user_id = :uid"
            values[":uid"] = reviewed_by_user_id
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": CANDIDATE_SK},
            UpdateExpression=expr,
            ExpressionAttributeValues=values,
        )

    def mark_candidate_notified(
        self,
        match_id: str,
        *,
        admin_chat_id: int,
        admin_message_id: int,
    ) -> None:
        self._table.update_item(
            Key={"partition_key": f"MATCH#{match_id}", "sort_key": CANDIDATE_SK},
            UpdateExpression=(
                "SET notified_at = :now, admin_chat_id = :cid, "
                "admin_message_id = :mid, updated_at = :now"
            ),
            ExpressionAttributeValues={
                ":now": _now_iso(),
                ":cid": int(admin_chat_id),
                ":mid": int(admin_message_id),
            },
        )

    def list_pending_candidates(self, *, limit: int = 20) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Attr

        out: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": (
                Attr("sort_key").eq(CANDIDATE_SK)
                & Attr("approval_status").eq(APPROVAL_PENDING)
            ),
        }
        while True:
            resp = self._table.scan(**scan_kwargs)
            out.extend(resp.get("Items", []))
            if len(out) >= limit or not resp.get("LastEvaluatedKey"):
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return out[:limit]

    def save_published_result(
        self,
        match_id: str,
        result: MatchResult,
        *,
        published_by_user_id: str,
        collection_source_summary: str,
        publish_version: int = 1,
        supersedes_version: int | None = None,
    ) -> bool:
        """Guarda RESULT oficial con metadata de publicación."""
        now = _now_iso()
        final_home = result.home_goals_aet if result.home_goals_aet is not None else result.home_goals
        final_away = result.away_goals_aet if result.away_goals_aet is not None else result.away_goals
        went_et = result.playoff_via == "ET" or result.status == "AET"
        went_pen = result.playoff_via == "PENALTIES" or result.status == "PEN"

        item: dict[str, Any] = {
            "partition_key": f"MATCH#{match_id}",
            "sort_key": "RESULT",
            "match_id": match_id,
            "result_90min_home": int(result.home_goals),
            "result_90min_away": int(result.away_goals),
            "result_final_home": int(final_home),
            "result_final_away": int(final_away),
            "went_to_et": went_et,
            "went_to_penalties": went_pen,
            "home_goals_ft": int(result.home_goals),
            "away_goals_ft": int(result.away_goals),
            "home_goals_aet": result.home_goals_aet,
            "away_goals_aet": result.away_goals_aet,
            "playoff_via": result.playoff_via,
            "playoff_winner": result.playoff_winner,
            "phase": result.phase,
            "scorers": result.scorers,
            "red_cards": int(result.red_cards),
            "goal_before_5min": result.goal_before_5min,
            "var_used": result.var_used,
            "free_kick_goal": result.free_kick_goal,
            "penalty_saved": result.penalty_saved,
            "penalty_scored": result.penalty_scored,
            "mvp_name": result.mvp_name,
            "status": result.status,
            "result_processed": False,
            "source": result.source,
            "recorded_at": result.recorded_at or now,
            "mvp_enriched_at": result.mvp_enriched_at,
            "published_at": now,
            "published_by_user_id": published_by_user_id,
            "publish_version": int(publish_version),
            "collection_source_summary": collection_source_summary,
            "updated_at": now,
        }
        if supersedes_version is not None:
            item["supersedes_version"] = int(supersedes_version)
        if result.mvp_name:
            item["mvp_enriched_at"] = result.mvp_enriched_at or now

        self._table.put_item(Item=item)
        return True

    def get_publish_version(self, match_id: str) -> int:
        item = self.get_raw(match_id)
        if not item:
            return 0
        return int(item.get("publish_version") or 0)

    @staticmethod
    def snapshots_to_dynamo(snapshots: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for snap in snapshots:
            parsed = None
            if getattr(snap, "parsed", None):
                parsed = snap.parsed.to_dict()
            out.append(
                {
                    "source_id": snap.source_id,
                    "fetched_at": snap.fetched_at,
                    "raw_excerpt": snap.raw_excerpt[:500],
                    "parsed": parsed,
                    "parse_confidence": snap.parse_confidence,
                    "in_play_signals": snap.in_play_signals,
                }
            )
        return out

    @staticmethod
    def candidate_proposed_result(item: dict[str, Any]) -> MatchResult | None:
        raw = item.get("proposed_result")
        if not raw:
            return None
        if isinstance(raw, str):
            raw = json.loads(raw)
        return MatchResult.from_dynamo({**raw, "match_id": item.get("match_id")})
