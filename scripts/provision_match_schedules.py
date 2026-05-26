#!/usr/bin/env python3
"""
Backfill / reprovisiona schedules EventBridge por partido (SPEC-2026-032).

Requiere ENABLE_MATCH_SCHEDULES y ARNs de Lambdas (o terraform output).

Ejemplos:
  export ENABLE_MATCH_SCHEDULES=true
  export SCHEDULER_GROUP_NAME=prode-match-dev
  export SCHEDULER_INVOKE_ROLE_ARN=arn:aws:iam::...
  # ARNs desde: terraform output -json match_schedule_lambda_arns

  python scripts/provision_match_schedules.py --env dev --profile asap_dev
  python scripts/provision_match_schedules.py --teams MEX RSA --profile asap_dev
  python scripts/provision_match_schedules.py --deprovision --match-id <uuid>
  python scripts/provision_match_schedules.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _configure(env: str, profile: str | None, region: str | None) -> None:
    os.environ["DYNAMODB_TABLE"] = os.environ.get("DYNAMODB_TABLE", f"ProdeTable-{env}")
    os.environ.setdefault("ENABLE_MATCH_SCHEDULES", "true")
    from src.dao.dynamo.table import configure_aws

    configure_aws(profile=profile, region=region)


def _load_arns_from_file(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping = {
        "trivia_pre_match": "LAMBDA_ARN_TRIVIA_PRE_MATCH",
        "match_reminder": "LAMBDA_ARN_MATCH_REMINDER",
        "veda_activator": "LAMBDA_ARN_VEDA_ACTIVATOR",
        "result_collector": "LAMBDA_ARN_RESULT_COLLECTOR",
        "scoring_processor": "LAMBDA_ARN_SCORING_PROCESSOR",
    }
    for key, env_key in mapping.items():
        if key in data and data[key]:
            os.environ[env_key] = data[key]


# Nombres Terraform → variable de entorno (SPEC-032)
_LAMBDA_FUNCTION_NAMES: dict[str, str] = {
    "LAMBDA_ARN_TRIVIA_PRE_MATCH": "prode-trivia-pre-match-{env}",
    "LAMBDA_ARN_MATCH_REMINDER": "prode-match-reminder-{env}",
    "LAMBDA_ARN_VEDA_ACTIVATOR": "prode-veda-activator-{env}",
    "LAMBDA_ARN_RESULT_COLLECTOR": "prode-result-collector-{env}",
    "LAMBDA_ARN_SCORING_PROCESSOR": "prode-scoring-processor-{env}",
}


def _needs_auto_config() -> bool:
    if os.environ.get("SCHEDULER_INVOKE_ROLE_ARN", "").strip():
        return False
    for env_key in _LAMBDA_FUNCTION_NAMES:
        if not os.environ.get(env_key, "").strip():
            return True
    return False


def _auto_configure_from_aws(env: str, *, profile: str | None, region: str) -> bool:
    """
    Resuelve ARNs por nombre de Lambda/rol (sin terraform output).
    Útil si enable_match_schedules se aplicó pero el state local no tiene outputs.
    """
    from src.dao.dynamo.table import configure_aws, get_session

    configure_aws(profile=profile, region=region)
    lam = get_session().client("lambda")
    iam = get_session().client("iam")

    os.environ.setdefault("ENABLE_MATCH_SCHEDULES", "true")
    os.environ.setdefault("SCHEDULER_GROUP_NAME", f"prode-match-{env}")

    resolved = 0
    for env_key, name_tpl in _LAMBDA_FUNCTION_NAMES.items():
        if os.environ.get(env_key, "").strip():
            continue
        fn = name_tpl.format(env=env)
        try:
            resp = lam.get_function(FunctionName=fn)
            arn = resp["Configuration"]["FunctionArn"]
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
            resp = iam.get_role(RoleName=role_name)
            os.environ["SCHEDULER_INVOKE_ROLE_ARN"] = resp["Role"]["Arn"]
            logger.info("SCHEDULER_INVOKE_ROLE_ARN ← %s", role_name)
        except iam.exceptions.NoSuchEntityException:
            logger.warning("Rol IAM no encontrado: %s", role_name)
        except Exception:
            logger.exception("get_role failed: %s", role_name)

    ok = bool(os.environ.get("SCHEDULER_INVOKE_ROLE_ARN")) and resolved >= 4
    if not ok:
        logger.error(
            "Auto-config incompleta (%s/5 Lambdas, rol=%s). "
            "¿Corriste terraform apply con enable_match_schedules=true?",
            resolved,
            "ok" if os.environ.get("SCHEDULER_INVOKE_ROLE_ARN") else "falta",
        )
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description="Provisionar schedules SPEC-032")
    p.add_argument("--env", default="dev")
    p.add_argument("--profile", "-p", default=os.environ.get("AWS_PROFILE"))
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--match-id")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument("--deprovision", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--from-date", help="ISO date — solo partidos con kickoff >= fecha")
    p.add_argument("--lambda-arns-json", type=Path, help="JSON con ARNs de terraform output")
    p.add_argument(
        "--no-auto-config",
        action="store_true",
        help="No resolver ARNs/rol desde AWS por nombre de función",
    )
    args = p.parse_args()

    _configure(args.env, args.profile, args.region)

    if args.lambda_arns_json:
        _load_arns_from_file(args.lambda_arns_json)

    os.environ.setdefault("SCHEDULER_GROUP_NAME", f"prode-match-{args.env}")

    if not args.no_auto_config and _needs_auto_config():
        logger.info("Resolviendo ARNs desde AWS (profile=%s, env=%s)...", args.profile, args.env)
        if not _auto_configure_from_aws(
            args.env, profile=args.profile, region=args.region
        ):
            return 1

    from src.dao.dynamo.match_dao import MatchDAO
    from src.services.scheduler_manager import MatchScheduleManager

    mgr = MatchScheduleManager()
    if not mgr.is_enabled():
        logger.error(
            "Schedules deshabilitados. Set ENABLE_MATCH_SCHEDULES, SCHEDULER_GROUP_NAME, "
            "SCHEDULER_INVOKE_ROLE_ARN y LAMBDA_ARN_*"
        )
        return 1

    dao = MatchDAO()
    if args.match_id:
        matches = [dao.get_match(args.match_id)]
        if not matches[0]:
            logger.error("Partido no encontrado: %s", args.match_id)
            return 1
    elif args.teams:
        m = dao.find_by_teams(args.teams[0], args.teams[1])
        if not m:
            logger.error("Partido no encontrado: %s vs %s", args.teams[0], args.teams[1])
            return 1
        matches = [m]
    else:
        matches = dao.list_matches()

    cutoff = None
    if args.from_date:
        cutoff = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)

    results = []
    for m in matches:
        if not m:
            continue
        if cutoff:
            ko = m.get("kickoff_utc", "")
            if ko and datetime.fromisoformat(ko.replace("Z", "+00:00")) < cutoff:
                continue
        mid = m["match_id"]
        if args.dry_run:
            plans = mgr._build_plans(
                mid,
                datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00")),
                datetime.now(timezone.utc),
            )
            results.append(
                {
                    "match_id": mid,
                    "plans": [
                        {"name": pl.name, "at": pl.fire_at.isoformat()} for pl in plans
                    ],
                }
            )
            continue
        if args.deprovision:
            results.append(mgr.deprovision_match(mid))
        else:
            results.append(mgr.provision_match(m).to_dict())

    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
