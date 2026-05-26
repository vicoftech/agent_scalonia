"""
EventBridge Scheduler — modo DEV_FAST (~4.5 min) — SPEC-2026-041.

No usa offsets de kickoff; usa sandbox_started_at y prefijos devfast-*.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from src.dao.dynamo.match_dao import MatchDAO
from src.services.scheduler_manager import (
    MatchScheduleManager,
    ProvisionResult,
    SchedulePlan,
    _lambda_arns_from_env,
    _scheduler_client,
    _upsert_schedule,
    sandbox_schedule_name,
)

logger = logging.getLogger(__name__)

SANDBOX_MODE_NONE = "NONE"
SANDBOX_MODE_DEV_FAST = "DEV_FAST"

# EventBridge Scheduler exige expresión at() en el futuro cercano
_MIN_SCHEDULE_LEAD_SEC = 5

# (suffix, offset_seconds desde sandbox_started_at, event_type, arn env key, extra payload)
SANDBOX_SCHEDULE_SPECS: tuple[tuple[str, int, str, str, dict[str, Any]], ...] = (
    ("devfast-trivia", 0, "MATCH_TRIVIA", "LAMBDA_ARN_TRIVIA_PRE_MATCH", {"sandbox": True}),
    (
        "devfast-remind1",
        60,
        "MATCH_REMINDER",
        "LAMBDA_ARN_MATCH_REMINDER",
        {"reminder_tier": 1, "sandbox": True},
    ),
    (
        "devfast-remind2",
        120,
        "MATCH_REMINDER",
        "LAMBDA_ARN_MATCH_REMINDER",
        {"reminder_tier": 2, "sandbox": True},
    ),
    (
        "devfast-remind3",
        150,
        "MATCH_REMINDER",
        "LAMBDA_ARN_MATCH_REMINDER",
        {"reminder_tier": 3, "sandbox": True},
    ),
    (
        "devfast-veda",
        180,
        "MATCH_VEDA",
        "LAMBDA_ARN_VEDA_ACTIVATOR",
        {"sandbox": True, "force": True},
    ),
    (
        "devfast-result",
        240,
        "MATCH_RESULT",
        "LAMBDA_ARN_RESULT_COLLECTOR",
        {"trigger": "sandbox_devfast", "sandbox": True},
    ),
    (
        "devfast-scoring",
        270,
        "MATCH_SCORING_CATCHUP",
        "LAMBDA_ARN_SCORING_PROCESSOR",
        {"sandbox": True},
    ),
)


class MatchScheduleSandboxManager:
    """Provisiona schedules devfast-* sin tocar los de SPEC-032."""

    def __init__(
        self,
        *,
        matches: MatchDAO | None = None,
        schedule_mgr: MatchScheduleManager | None = None,
    ) -> None:
        self._matches = matches or MatchDAO()
        self._schedules = schedule_mgr or MatchScheduleManager()

    def is_enabled(self) -> bool:
        return _sandbox_allowed() and self._schedules.is_enabled()

    def provision_sandbox_schedules(
        self, match_id: str, *, mode: str = SANDBOX_MODE_DEV_FAST
    ) -> dict[str, Any]:
        if not _sandbox_allowed():
            return {
                "status": "FORBIDDEN",
                "error": "sandbox solo permitido en entornos no-prod",
            }
        if mode != SANDBOX_MODE_DEV_FAST:
            return {"status": "ERROR", "error": f"mode unsupported: {mode}"}

        match = self._matches.get_match(match_id)
        if not match:
            return {"status": "NOT_FOUND", "match_id": match_id}

        env = os.environ.get("ENV") or os.environ.get("PRODE_ENV") or "dev"
        profile = os.environ.get("AWS_PROFILE") or None
        region = os.environ.get("AWS_REGION", "us-east-1")
        from src.services.scheduler_manager import (
            MatchScheduleManager,
            auto_configure_scheduler_env,
            normalize_scheduler_env,
        )

        normalize_scheduler_env(env)
        if not auto_configure_scheduler_env(env, profile=profile, region=region):
            return {
                "status": "ERROR",
                "error": "Scheduler no configurado (ARNs Lambda o rol invoke)",
            }
        self._schedules = MatchScheduleManager()

        started_at = datetime.now(timezone.utc)
        self._matches.set_sandbox_state(
            match_id, mode=SANDBOX_MODE_DEV_FAST, started_at=started_at
        )

        plans = _build_sandbox_plans(
            match_id, started_at, started_at, self._schedules._lambda_arns
        )
        client = _scheduler_client()
        group = self._schedules._group
        invoke_role = self._schedules._invoke_role

        created: list[str] = []
        updated: list[str] = []
        errors: list[str] = []
        schedule_rows: list[dict[str, str]] = []

        for plan in plans:
            try:
                action = _upsert_schedule(
                    client,
                    group=group,
                    plan=plan,
                    invoke_role_arn=invoke_role,
                )
                schedule_rows.append(
                    {"name": plan.name, "at": plan.fire_at.isoformat(), "action": action}
                )
                if action == "created":
                    created.append(plan.name)
                else:
                    updated.append(plan.name)
            except Exception as exc:
                logger.exception("sandbox schedule failed name=%s", plan.name)
                errors.append(f"{plan.name}:{exc}")

        logger.info(
            "sandbox provision match=%s created=%s updated=%s",
            match_id[:8],
            len(created),
            len(updated),
        )
        return {
            "status": "OK" if not errors else "PARTIAL",
            "match_id": match_id,
            "sandbox_mode": SANDBOX_MODE_DEV_FAST,
            "sandbox_started_at": started_at.isoformat(),
            "schedules": schedule_rows,
            "created": created,
            "updated": updated,
            "errors": errors,
        }

    def cancel_sandbox_schedules(self, match_id: str) -> dict[str, Any]:
        env = os.environ.get("ENV") or os.environ.get("PRODE_ENV") or "dev"
        from src.services.scheduler_manager import (
            MatchScheduleManager,
            auto_configure_scheduler_env,
            normalize_scheduler_env,
        )

        normalize_scheduler_env(env)
        profile = os.environ.get("AWS_PROFILE") or None
        auto_configure_scheduler_env(
            env, profile=profile, region=os.environ.get("AWS_REGION", "us-east-1")
        )
        self._schedules = MatchScheduleManager()
        if not self._schedules.is_enabled():
            return {"match_id": match_id, "deleted": [], "disabled": True}

        client = _scheduler_client()
        group = self._schedules._group
        deleted: list[str] = []
        not_found: list[str] = []

        for suffix, *_ in SANDBOX_SCHEDULE_SPECS:
            name = sandbox_schedule_name(suffix, match_id)
            try:
                client.delete_schedule(Name=name, GroupName=group)
                deleted.append(name)
            except client.exceptions.ResourceNotFoundException:
                not_found.append(name)
            except Exception:
                logger.exception("sandbox delete_schedule failed name=%s", name)

        self._matches.clear_sandbox_state(match_id)

        return {
            "status": "OK",
            "match_id": match_id,
            "deleted": deleted,
            "not_found": not_found,
        }


def _sandbox_allowed() -> bool:
    if os.environ.get("ENABLE_MATCH_LIFECYCLE_SANDBOX", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return False
    env = (os.environ.get("ENV") or os.environ.get("PRODE_ENV") or "").lower()
    if env in ("prod", "production"):
        return False
    table = os.environ.get("DYNAMODB_TABLE", "").lower()
    if "prod" in table and "dev" not in table:
        return False
    return True


def _build_sandbox_plans(
    match_id: str,
    started_at: datetime,
    now: datetime,
    lambda_arns: dict[str, str],
) -> list[SchedulePlan]:
    plans: list[SchedulePlan] = []
    next_slot = now + timedelta(seconds=_MIN_SCHEDULE_LEAD_SEC)
    for suffix, offset_sec, event_type, arn_key, extra in SANDBOX_SCHEDULE_SPECS:
        fire_at = started_at + timedelta(seconds=offset_sec)
        if fire_at <= now:
            fire_at = next_slot
            next_slot = next_slot + timedelta(seconds=_MIN_SCHEDULE_LEAD_SEC)
        target_arn = lambda_arns.get(arn_key, "")
        if not target_arn:
            logger.warning("sandbox missing %s for %s", arn_key, suffix)
            continue
        payload: dict[str, Any] = {
            "event_type": event_type,
            "match_id": match_id,
            "schedule_name": sandbox_schedule_name(suffix, match_id),
            **extra,
        }
        if event_type == "MATCH_RESULT":
            payload.setdefault("trigger", "sandbox_devfast")
        plans.append(
            SchedulePlan(
                suffix=suffix,
                name=sandbox_schedule_name(suffix, match_id),
                fire_at=fire_at,
                event_type=event_type,
                payload=payload,
                target_arn=target_arn,
            )
        )
    return plans


def build_sandbox_plans_for_dry_run(match_id: str, started_at: datetime | None = None) -> list[dict[str, str]]:
    """Helper para CLI --dry-run sin AWS (lista los 7 eventos sin filtrar pasados)."""
    started = started_at or datetime.now(timezone.utc)
    arns = _lambda_arns_from_env() or {k: "arn:stub" for k in {s[3] for s in SANDBOX_SCHEDULE_SPECS}}
    plans = _build_sandbox_plans(
        match_id, started, started - timedelta(seconds=1), arns
    )
    return [{"name": p.name, "at": p.fire_at.isoformat()} for p in plans]
