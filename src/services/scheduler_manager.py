"""
EventBridge Scheduler — 7 schedules one-time por partido (SPEC-2026-032).

Variables de entorno:
  ENABLE_MATCH_SCHEDULES=true
  SCHEDULER_GROUP_NAME=prode-match-{env}
  SCHEDULER_INVOKE_ROLE_ARN=arn:aws:iam::...
  LAMBDA_ARN_TRIVIA_PRE_MATCH, LAMBDA_ARN_MATCH_REMINDER,
  LAMBDA_ARN_VEDA_ACTIVATOR, LAMBDA_ARN_RESULT_COLLECTOR,
  LAMBDA_ARN_SCORING_PROCESSOR
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# (suffix, offset_minutos vs kickoff, event_type, env ARN key, extra payload)
SCHEDULE_SPECS: tuple[tuple[str, int, str, str, dict[str, Any]], ...] = (
    ("trivia-pre", -120, "MATCH_TRIVIA", "LAMBDA_ARN_TRIVIA_PRE_MATCH", {}),
    ("remind-60", -60, "MATCH_REMINDER", "LAMBDA_ARN_MATCH_REMINDER", {"reminder_tier": 1}),
    ("remind-30", -30, "MATCH_REMINDER", "LAMBDA_ARN_MATCH_REMINDER", {"reminder_tier": 2}),
    ("remind-15", -15, "MATCH_REMINDER", "LAMBDA_ARN_MATCH_REMINDER", {"reminder_tier": 3}),
    ("veda", -30, "MATCH_VEDA", "LAMBDA_ARN_VEDA_ACTIVATOR", {}),
    ("result", 110, "MATCH_RESULT", "LAMBDA_ARN_RESULT_COLLECTOR", {"trigger": "match_ended"}),
    (
        "scoring-catchup",
        120,
        "MATCH_SCORING_CATCHUP",
        "LAMBDA_ARN_SCORING_PROCESSOR",
        {},
    ),
)

AWS_SCHEDULE_NAME_MAX = 64
_SCHEDULER_GROUP_RE = re.compile(r"^[0-9a-zA-Z-_.]{1,64}$")


@dataclass
class SchedulePlan:
    suffix: str
    name: str
    fire_at: datetime
    event_type: str
    payload: dict[str, Any]
    target_arn: str


@dataclass
class ProvisionResult:
    match_id: str
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class MatchScheduleManager:
    def __init__(
        self,
        *,
        group_name: str | None = None,
        invoke_role_arn: str | None = None,
        lambda_arns: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._group = group_name or os.environ.get("SCHEDULER_GROUP_NAME", "").strip()
        self._invoke_role = invoke_role_arn or os.environ.get(
            "SCHEDULER_INVOKE_ROLE_ARN", ""
        ).strip()
        self._lambda_arns = lambda_arns or _lambda_arns_from_env()
        self._enabled = (
            enabled
            if enabled is not None
            else os.environ.get("ENABLE_MATCH_SCHEDULES", "").lower()
            in ("1", "true", "yes")
        )

    def is_enabled(self) -> bool:
        return bool(
            self._enabled
            and self._group
            and self._invoke_role
            and self._lambda_arns
        )

    def provision_match(self, match: dict[str, Any]) -> ProvisionResult:
        match_id = str(match.get("match_id") or "")
        result = ProvisionResult(match_id=match_id)
        if not match_id:
            result.errors.append("match_id missing")
            return result
        if not self.is_enabled():
            result.skipped.append("_all:schedules_disabled")
            logger.info("Match schedules disabled; skip provision match=%s", match_id[:8])
            return result

        kickoff = _parse_kickoff(match.get("kickoff_utc"))
        if kickoff is None:
            result.errors.append("kickoff_utc invalid or missing")
            return result

        now = datetime.now(timezone.utc)
        plans = self._build_plans(match_id, kickoff, now)
        client = _scheduler_client()

        for plan in plans:
            try:
                action = _upsert_schedule(
                    client,
                    group=self._group,
                    plan=plan,
                    invoke_role_arn=self._invoke_role,
                )
                if action == "created":
                    result.created.append(plan.name)
                elif action == "updated":
                    result.updated.append(plan.name)
                else:
                    result.skipped.append(plan.name)
            except Exception as exc:
                logger.exception("schedule upsert failed name=%s", plan.name)
                result.errors.append(f"{plan.name}:{exc}")

        return result

    def deprovision_match(self, match_id: str) -> dict[str, Any]:
        deleted: list[str] = []
        not_found: list[str] = []
        if not self.is_enabled():
            return {"match_id": match_id, "deleted": [], "disabled": True}

        client = _scheduler_client()
        for suffix, *_ in SCHEDULE_SPECS:
            name = schedule_name(suffix, match_id)
            try:
                client.delete_schedule(Name=name, GroupName=self._group)
                deleted.append(name)
            except client.exceptions.ResourceNotFoundException:
                not_found.append(name)
            except Exception:
                logger.exception("delete_schedule failed name=%s", name)

        return {"match_id": match_id, "deleted": deleted, "not_found": not_found}

    def update_kickoff(
        self,
        match_id: str,
        match: dict[str, Any],
        *,
        old_kickoff: datetime | None = None,
        new_kickoff: datetime | None = None,
    ) -> ProvisionResult:
        _ = old_kickoff, new_kickoff
        self.deprovision_match(match_id)
        return self.provision_match(match)

    def _build_plans(
        self, match_id: str, kickoff: datetime, now: datetime
    ) -> list[SchedulePlan]:
        plans: list[SchedulePlan] = []

        for suffix, offset_min, event_type, arn_key, extra in SCHEDULE_SPECS:
            fire_at = kickoff + timedelta(minutes=offset_min)
            if fire_at <= now:
                continue

            target_arn = self._lambda_arns.get(arn_key, "")
            if not target_arn:
                logger.warning("Missing %s for schedule %s", arn_key, suffix)
                continue

            payload: dict[str, Any] = {
                "event_type": event_type,
                "match_id": match_id,
                "schedule_name": schedule_name(suffix, match_id),
                **extra,
            }
            if event_type == "MATCH_RESULT":
                payload.setdefault("trigger", "match_ended")

            plans.append(
                SchedulePlan(
                    suffix=suffix,
                    name=schedule_name(suffix, match_id),
                    fire_at=fire_at,
                    event_type=event_type,
                    payload=payload,
                    target_arn=target_arn,
                )
            )
        return plans


def schedule_name(suffix: str, match_id: str) -> str:
    """Nombres SPEC-032 (trivia-pre-, remind-60-, …)."""
    return _schedule_name_for_prefix(suffix, match_id)


def sandbox_schedule_name(suffix: str, match_id: str) -> str:
    """Nombres SPEC-041 (devfast-*)."""
    return _schedule_name_for_prefix(suffix, match_id)


def _schedule_name_for_prefix(suffix: str, match_id: str) -> str:
    base = f"{suffix}-{match_id}"
    if len(base) <= AWS_SCHEDULE_NAME_MAX:
        return base
    digest = hashlib.sha256(match_id.encode()).hexdigest()[:16]
    short = f"{suffix}-{digest}"
    return short[:AWS_SCHEDULE_NAME_MAX]


def schedule_expression_at(fire_at: datetime) -> str:
    """EventBridge Scheduler one-time at() en UTC."""
    if fire_at.tzinfo is None:
        fire_at = fire_at.replace(tzinfo=timezone.utc)
    else:
        fire_at = fire_at.astimezone(timezone.utc)
    return f"at({fire_at.strftime('%Y-%m-%dT%H:%M:%S')})"


def _parse_kickoff(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _lambda_arns_from_env() -> dict[str, str]:
    keys = {spec[3] for spec in SCHEDULE_SPECS}
    return {k: os.environ.get(k, "").strip() for k in keys if os.environ.get(k, "").strip()}


_LAMBDA_FUNCTION_NAMES: dict[str, str] = {
    "LAMBDA_ARN_TRIVIA_PRE_MATCH": "prode-trivia-pre-match-{env}",
    "LAMBDA_ARN_MATCH_REMINDER": "prode-match-reminder-{env}",
    "LAMBDA_ARN_VEDA_ACTIVATOR": "prode-veda-activator-{env}",
    "LAMBDA_ARN_RESULT_COLLECTOR": "prode-result-collector-{env}",
    "LAMBDA_ARN_SCORING_PROCESSOR": "prode-scoring-processor-{env}",
}


def normalize_scheduler_env(env: str) -> str:
    """
    Fija SCHEDULER_GROUP_NAME válido (prode-match-{env}).
    Ignora valores basura (p. ej. stderr de terraform output en el shell).
    """
    expected = f"prode-match-{env}"
    current = os.environ.get("SCHEDULER_GROUP_NAME", "").strip()
    if not current or not _SCHEDULER_GROUP_RE.match(current):
        if current:
            logger.warning(
                "SCHEDULER_GROUP_NAME inválido (%s chars); usando %s",
                len(current),
                expected,
            )
        os.environ["SCHEDULER_GROUP_NAME"] = expected
    os.environ.setdefault("ENABLE_MATCH_SCHEDULES", "true")
    return os.environ["SCHEDULER_GROUP_NAME"]


def _lambda_arns_configured_count() -> int:
    return sum(1 for k in _LAMBDA_FUNCTION_NAMES if os.environ.get(k, "").strip())


def auto_configure_scheduler_env(
    env: str, *, profile: str | None = None, region: str = "us-east-1"
) -> bool:
    """Resuelve ARNs de Lambdas y rol Scheduler por nombre (CLI local / scripts)."""
    from src.dao.dynamo.table import configure_aws, get_session

    normalize_scheduler_env(env)
    if _lambda_arns_configured_count() >= 4 and os.environ.get(
        "SCHEDULER_INVOKE_ROLE_ARN", ""
    ).strip():
        return True

    configure_aws(profile=profile, region=region)
    lam = get_session().client("lambda")
    iam = get_session().client("iam")

    resolved = 0
    for env_key, name_tpl in _LAMBDA_FUNCTION_NAMES.items():
        if os.environ.get(env_key, "").strip():
            continue
        fn = name_tpl.format(env=env)
        try:
            arn = lam.get_function(FunctionName=fn)["Configuration"]["FunctionArn"]
            os.environ[env_key] = arn
            resolved += 1
            logger.info("ARN %s ← %s", env_key, fn)
        except lam.exceptions.ResourceNotFoundException:
            logger.warning("Lambda no encontrada: %s", fn)
        except Exception:
            logger.exception("get_function failed: %s", fn)

    if not os.environ.get("SCHEDULER_INVOKE_ROLE_ARN", "").strip():
        role_name = f"prode-scheduler-invoke-{env}"
        try:
            os.environ["SCHEDULER_INVOKE_ROLE_ARN"] = iam.get_role(RoleName=role_name)["Role"]["Arn"]
            logger.info("SCHEDULER_INVOKE_ROLE_ARN ← %s", role_name)
        except iam.exceptions.NoSuchEntityException:
            logger.warning("Rol IAM no encontrado: %s", role_name)

    total_arns = _lambda_arns_configured_count()
    ok = bool(os.environ.get("SCHEDULER_INVOKE_ROLE_ARN")) and total_arns >= 4
    if not ok:
        logger.error(
            "Auto-config scheduler incompleta (%s/5 lambdas configuradas, rol=%s)",
            total_arns,
            "ok" if os.environ.get("SCHEDULER_INVOKE_ROLE_ARN") else "falta",
        )
    return ok


def _scheduler_client():
    from src.dao.dynamo.table import get_session

    return get_session().client("scheduler")


def _upsert_schedule(
    client: Any,
    *,
    group: str,
    plan: SchedulePlan,
    invoke_role_arn: str,
) -> str:
    expr = schedule_expression_at(plan.fire_at)
    target = {
        "Arn": plan.target_arn,
        "RoleArn": invoke_role_arn,
        "Input": json.dumps(plan.payload),
        "RetryPolicy": {"MaximumEventAgeInSeconds": 3600, "MaximumRetryAttempts": 2},
    }
    common = {
        "ScheduleExpression": expr,
        "ScheduleExpressionTimezone": "UTC",
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "Target": target,
        "ActionAfterCompletion": "DELETE",
    }
    try:
        client.get_schedule(Name=plan.name, GroupName=group)
        client.update_schedule(Name=plan.name, GroupName=group, **common)
        return "updated"
    except client.exceptions.ResourceNotFoundException:
        client.create_schedule(Name=plan.name, GroupName=group, **common)
        return "created"


def maybe_provision_after_put(match_item: dict[str, Any]) -> ProvisionResult | None:
    """Hook post put_match — no lanza excepción hacia arriba."""
    mgr = MatchScheduleManager()
    if not mgr.is_enabled():
        return None
    try:
        return mgr.provision_match(match_item)
    except Exception:
        logger.exception("provision_match schedules failed match=%s", match_item.get("match_id", "")[:8])
        return None
