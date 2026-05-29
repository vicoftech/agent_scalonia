#!/usr/bin/env python3
"""Dry-run / dev — briefs diarios SPEC-2026-045.

  python3 scripts/run_daily_briefs.py --profile asap_dev --env dev
  python3 scripts/run_daily_briefs.py --team MEX --match 7ec4c6ec-f11b-5a24-8fd8-7ba47082508b --force
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_TG = os.path.join(_REPO, "infrastructure", "lambdas", "telegram_webhook")
if _TG not in sys.path:
    sys.path.insert(0, _TG)


def main() -> None:
    p = argparse.ArgumentParser(description="Generar briefs de selección y partido")
    p.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "asap_dev"))
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--env", default="dev")
    p.add_argument("--team", default="", help="ISO3 (ej. MEX)")
    p.add_argument("--match", default="", help="match_uuid")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    from src.dao.dynamo.table import configure_aws
    from src.services.brief_orchestrator import run_daily_brief_job

    configure_aws(profile=args.profile, region=args.region)
    os.environ.setdefault("ENV", args.env)
    os.environ.setdefault("DYNAMODB_TABLE", f"ProdeTable-{args.env}")
    os.environ.setdefault("BRIEF_TABLE", f"ProdeBriefTable-{args.env}")
    os.environ.setdefault("ENABLE_DAILY_BRIEFS", "true")

    arn = os.environ.get("AGENTCORE_RUNTIME_ARN", "").strip()
    if not arn:
        try:
            import boto3

            ssm = boto3.Session(profile_name=args.profile, region_name=args.region).client(
                "ssm"
            )
            # fallback: leer de terraform output manual
        except Exception:
            pass
        print(
            "Tip: export AGENTCORE_RUNTIME_ARN=$(terraform output -raw agent_runtime_arn)",
            file=sys.stderr,
        )

    result = run_daily_brief_job(
        team=args.team.upper() if args.team else None,
        match_id=args.match or None,
        force=args.force,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
