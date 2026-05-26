#!/usr/bin/env python3
"""
Sandbox DEV_FAST (~90 s, eventos cada 15 s) — SPEC-2026-041.

Ejemplos:
  python scripts/provision_match_sandbox.py --teams MEX RSA --reset --action provision --profile asap_dev
  python scripts/provision_match_sandbox.py --teams MEX RSA --reset --action provision
      # default --profile asap_dev si AWS_PROFILE no está definido
  python scripts/provision_match_sandbox.py --match-id <uuid> --action cancel --profile asap_dev
  python scripts/provision_match_sandbox.py --invoke-lambda --teams MEX RSA --profile asap_dev
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _default_profile() -> str:
    return os.environ.get("AWS_PROFILE") or "asap_dev"


def _configure(env: str, profile: str | None, region: str | None) -> None:
    os.environ["DYNAMODB_TABLE"] = os.environ.get("DYNAMODB_TABLE", f"ProdeTable-{env}")
    os.environ["ENV"] = env
    os.environ.setdefault("ENABLE_MATCH_LIFECYCLE_SANDBOX", "true")
    from src.services.scheduler_manager import normalize_scheduler_env

    normalize_scheduler_env(env)
    if profile:
        os.environ["AWS_PROFILE"] = profile
    from src.dao.dynamo.table import configure_aws

    configure_aws(profile=profile, region=region)


def main() -> int:
    p = argparse.ArgumentParser(description="SPEC-041 sandbox schedules (devfast-*)")
    p.add_argument("--env", default="dev")
    p.add_argument(
        "--profile",
        "-p",
        default=_default_profile(),
        help="Perfil AWS (default: AWS_PROFILE o asap_dev)",
    )
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--match-id")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument("--action", choices=("provision", "cancel"), default="provision")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--invoke-lambda",
        action="store_true",
        help="Invocar prode-match-schedule-manager-{env} en lugar del SDK local",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Antes de provision: quitar veda, RESULT y puntuación (re-test limpio)",
    )
    args = p.parse_args()

    _configure(args.env, args.profile, args.region)

    from src.dao.dynamo.match_dao import MatchDAO

    dao = MatchDAO()
    if args.match_id:
        match_id = args.match_id
    elif args.teams:
        m = dao.find_by_teams(args.teams[0], args.teams[1])
        if not m:
            logger.error("Partido no encontrado: %s vs %s", args.teams[0], args.teams[1])
            return 1
        match_id = m["match_id"]
    else:
        p.error("--match-id o --teams requerido")

    if args.reset and args.action == "provision":
        from src.dao.dynamo.result_dao import ResultDAO
        from src.services.scoring_service import ScoringService

        dao.set_veda_active(match_id, active=False)
        rdao = ResultDAO()
        if rdao.get_raw(match_id):
            rdao.delete_result(match_id)
            logger.info("RESULT borrado match=%s", match_id[:8])
        reset_n = ScoringService().reset_match_scoring(match_id)
        logger.info("Scoring reset: %s predicciones", reset_n)

    if args.dry_run:
        from src.services.match_schedule_sandbox import build_sandbox_plans_for_dry_run

        plans = build_sandbox_plans_for_dry_run(match_id)
        print(json.dumps({"match_id": match_id, "dry_run": True, "plans": plans}, indent=2))
        return 0

    if args.invoke_lambda:
        import boto3

        fn = f"prode-match-schedule-manager-{args.env}"
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        client = session.client("lambda")
        payload = {"action": args.action, "match_id": match_id, "mode": "DEV_FAST"}
        resp = client.invoke(
            FunctionName=fn,
            Payload=json.dumps(payload).encode(),
        )
        body = json.loads(resp["Payload"].read())
        print(json.dumps(body, indent=2, default=str))
        return 0 if body.get("status") in ("OK", "PARTIAL") else 1

    from src.services.match_schedule_sandbox import MatchScheduleSandboxManager

    mgr = MatchScheduleSandboxManager()
    if args.action == "provision":
        out = mgr.provision_sandbox_schedules(match_id)
    else:
        out = mgr.cancel_sandbox_schedules(match_id)

    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("status") in ("OK", "PARTIAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
