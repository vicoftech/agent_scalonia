#!/usr/bin/env python3
"""
CLI manual — SPEC-2026-031 recolectar resultados.

Uso:
  python scripts/collect_result.py --match-id <uuid> --env dev
  python scripts/collect_result.py --teams ARG ALG --env dev
  python scripts/collect_result.py --date 2026-06-12 --env dev
  python scripts/collect_result.py --enrich-mvp-only --match-id <uuid> --env dev
  python scripts/collect_result.py --teams MEX RSA --inject 2-0 --env dev
  python scripts/collect_result.py --match-id <uuid> --inject 2-0 --profile prode-dev
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _configure_runtime(
    env: str,
    *,
    profile: str | None,
    region: str | None,
) -> None:
    os.environ["DYNAMODB_TABLE"] = os.environ.get(
        "DYNAMODB_TABLE", f"ProdeTable-{env}"
    )
    from src.dao.dynamo.table import configure_aws

    configure_aws(profile=profile, region=region)
    if profile:
        logger.info("AWS profile=%s table=%s", profile, os.environ["DYNAMODB_TABLE"])
    else:
        logger.info(
            "AWS profile=%s table=%s",
            os.environ.get("AWS_PROFILE", "(default)"),
            os.environ["DYNAMODB_TABLE"],
        )


def _match_on_date(match: dict, day: date) -> bool:
    kick = match.get("kickoff_utc") or ""
    if not kick:
        return False
    dt = datetime.fromisoformat(kick.replace("Z", "+00:00"))
    return dt.date() == day


def main() -> int:
    p = argparse.ArgumentParser(description="Collect match results (SPEC-031)")
    p.add_argument("--env", default="dev", help="ProdeTable-{env}")
    p.add_argument(
        "--profile",
        "-p",
        default=os.environ.get("AWS_PROFILE"),
        help="Perfil en ~/.aws/credentials (evita usar el [default] de CI/CD)",
    )
    p.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="Región AWS (default: us-east-1)",
    )
    p.add_argument("--match-id", help="UUID del partido")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"), help="Códigos FIFA")
    p.add_argument("--date", help="YYYY-MM-DD — todos los incompletos ese día")
    p.add_argument(
        "--enrich-mvp-only",
        action="store_true",
        help="Solo enriquecer MVP en RESULT existente",
    )
    p.add_argument("--dry-run", action="store_true", help="Listar candidatos sin ejecutar")
    p.add_argument(
        "--inject",
        metavar="SCORE",
        help="Marcador manual HOME-AWAY (ej. 2-0). Omite web_search.",
    )
    p.add_argument("--mvp", default=None, help="MVP opcional con --inject")
    p.add_argument(
        "--no-notify",
        action="store_true",
        help="Con --inject: guardar sin SQS notify/scoring",
    )
    p.add_argument(
        "--telegram-direct",
        action="store_true",
        help="Enviar Telegram sin SQS (recomendado en local si no hay cola)",
    )
    p.add_argument(
        "--no-resolve-queues",
        action="store_true",
        help="No buscar prode-match-notify-{env} / prode-scoring-{env} en AWS",
    )
    args = p.parse_args()

    _configure_runtime(args.env, profile=args.profile, region=args.region)

    if not args.no_resolve_queues and not args.no_notify:
        from src.services.result_queues import ensure_queue_urls

        ensure_queue_urls(env=args.env)

    from src.dao.dynamo.match_dao import MatchDAO
    from src.services.result_service import ResultService

    dao = MatchDAO()
    svc = ResultService()
    match_ids: list[str] = []

    if args.inject:
        if not args.teams and not args.match_id:
            p.error("--inject requiere --teams HOME AWAY o --match-id")
        try:
            h, a = args.inject.replace(":", "-").split("-", 1)
            home_goals, away_goals = int(h.strip()), int(a.strip())
        except ValueError:
            p.error("--inject debe ser HOME-AWAY, ej. 2-0")

    if args.match_id:
        match_ids = [args.match_id]
    elif args.teams:
        m = dao.find_by_teams(args.teams[0], args.teams[1])
        if not m:
            logger.error("No se encontró partido %s vs %s", args.teams[0], args.teams[1])
            return 1
        match_ids = [m["match_id"]]
    elif args.date:
        day = date.fromisoformat(args.date)
        for m in dao.list_matches_estimated_finished():
            if _match_on_date(m, day):
                match_ids.append(m["match_id"])
    else:
        match_ids = svc.find_incomplete_match_ids()

    if args.enrich_mvp_only:
        from src.dao.dynamo.result_dao import ResultDAO

        rdao = ResultDAO()
        filtered: list[str] = []
        for mid in match_ids:
            raw = rdao.get_raw(mid)
            if raw and rdao.has_scores(mid) and not (raw.get("mvp_name") or "").strip():
                filtered.append(mid)
        match_ids = filtered

    if not match_ids:
        logger.info("Sin candidatos.")
        return 0

    logger.info("Candidatos: %s", len(match_ids))
    if args.dry_run:
        for mid in match_ids:
            m = dao.get_match(mid) or {}
            logger.info(
                "  #%s %s vs %s %s",
                m.get("match_number"),
                m.get("home_team"),
                m.get("away_team"),
                mid[:8],
            )
        return 0

    inj_home = inj_away = None
    if args.inject:
        h, a = args.inject.replace(":", "-").split("-", 1)
        inj_home, inj_away = int(h.strip()), int(a.strip())

    ok = 0
    for mid in match_ids:
        if args.inject and inj_home is not None and inj_away is not None:
            result = svc.apply_manual_result(
                mid,
                inj_home,
                inj_away,
                mvp_name=args.mvp,
                notify=not args.no_notify,
                telegram_direct=args.telegram_direct,
            )
        else:
            result = svc.collect_result(mid)
        if result:
            ok += 1
            logger.info("OK %s → %s-%s MVP=%s", mid[:8], result.home_goals, result.away_goals, result.mvp_name)
        else:
            logger.warning("Sin resultado %s", mid[:8])

    print(json.dumps({"processed": ok, "total": len(match_ids)}, indent=2))
    return 0 if ok > 0 or len(match_ids) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
