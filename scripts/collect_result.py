#!/usr/bin/env python3
"""
CLI manual — SPEC-2026-031 recolectar resultados.

Uso:
  python scripts/collect_result.py --match-id <uuid> --env dev
  python scripts/collect_result.py --teams ARG ALG --env dev
  python scripts/collect_result.py --date 2026-06-12 --env dev
  python scripts/collect_result.py --enrich-mvp-only --match-id <uuid> --env dev
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


def _set_table(env: str) -> None:
    os.environ["DYNAMODB_TABLE"] = os.environ.get(
        "DYNAMODB_TABLE", f"ProdeTable-{env}"
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
    p.add_argument("--match-id", help="UUID del partido")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"), help="Códigos FIFA")
    p.add_argument("--date", help="YYYY-MM-DD — todos los incompletos ese día")
    p.add_argument(
        "--enrich-mvp-only",
        action="store_true",
        help="Solo enriquecer MVP en RESULT existente",
    )
    p.add_argument("--dry-run", action="store_true", help="Listar candidatos sin ejecutar")
    args = p.parse_args()

    _set_table(args.env)

    from src.dao.dynamo.match_dao import MatchDAO
    from src.services.result_service import ResultService

    dao = MatchDAO()
    svc = ResultService()
    match_ids: list[str] = []

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

    ok = 0
    for mid in match_ids:
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
