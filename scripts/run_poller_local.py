#!/usr/bin/env python3
"""
Prueba local del result poller + collector sin Tavily ni API-Football real.

Modos:
  api     — mock API-Football → RESULT en Dynamo → collect_result (fake web_search opcional)
  collector — solo scheduled/manual del result_collector con fake web_search

Ejemplos:
  # Poller mock API (dry-run)
  python scripts/run_poller_local.py --mode api --api-match-id 2 --dry-run

  # Poller + fake web_search contra dev
  python scripts/run_poller_local.py --mode api --api-match-id 2 --profile asap_dev \\
    --mock-web-search --skip-kickoff-check --telegram-direct

  # Con colas SQS en AWS (sin Telegram directo):
  python scripts/run_poller_local.py --mode api --api-match-id 2 --profile asap_dev \\
    --mock-web-search --skip-kickoff-check

  # Collector scheduled con fake web_search (sin API)
  python scripts/run_poller_local.py --mode collector --teams MEX RSA --profile asap_dev \\
    --mock-web-search --skip-kickoff-check
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


def _configure_runtime(env: str, *, profile: str | None, region: str | None) -> None:
    os.environ["DYNAMODB_TABLE"] = os.environ.get(
        "DYNAMODB_TABLE", f"ProdeTable-{env}"
    )
    from src.dao.dynamo.table import configure_aws

    configure_aws(profile=profile, region=region)


def _install_mocks(args: argparse.Namespace) -> None:
    if args.mock_web_search:
        from src.testing.fake_web_search import install_fake_web_search

        install_fake_web_search(fixture_path=args.mock_web_search_path)
        logger.info("web_search → fixture %s", args.mock_web_search_path or "(default)")
    if args.skip_kickoff_check:
        os.environ["RESULT_SKIP_KICKOFF_CHECK"] = "1"
        logger.info("RESULT_SKIP_KICKOFF_CHECK=1")


def main() -> int:
    p = argparse.ArgumentParser(description="Local poller/collector test harness")
    p.add_argument("--mode", choices=("api", "collector"), default="api")
    p.add_argument("--env", default="dev")
    p.add_argument("--profile", "-p", default=os.environ.get("AWS_PROFILE"))
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--mock-web-search",
        action="store_true",
        help="Usar data/fixtures/mock_web_search_results.json",
    )
    p.add_argument(
        "--mock-web-search-path",
        default=None,
        help="JSON alternativo para fake web_search",
    )
    p.add_argument(
        "--mock-api-path",
        default=None,
        help="JSON mock API-Football (default: mock_api_football_fixtures.json)",
    )
    p.add_argument(
        "--skip-kickoff-check",
        action="store_true",
        help="Permite collect_result aunque kickoff+110min no haya pasado",
    )
    p.add_argument("--api-match-id", type=int, help="Solo en mode=api")
    p.add_argument("--match-id", help="Solo en mode=collector (trigger manual)")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument(
        "--telegram-direct",
        action="store_true",
        help="Enviar Telegram sin SQS (recomendado en local)",
    )
    p.add_argument(
        "--no-resolve-queues",
        action="store_true",
        help="No buscar prode-match-notify-{env} en AWS",
    )
    p.add_argument(
        "--replace-result",
        action="store_true",
        help="Borrar MATCH#/RESULT antes de pollear (re-dispara notify)",
    )
    p.add_argument(
        "--with-scoring",
        action="store_true",
        help="Tras el poller, ejecutar scoring local (FINISH_MATCH)",
    )
    args = p.parse_args()

    _configure_runtime(args.env, profile=args.profile, region=args.region)
    _install_mocks(args)

    if not args.no_resolve_queues and not args.telegram_direct:
        from src.services.result_queues import ensure_queue_urls

        queues = ensure_queue_urls(env=args.env)
        if not queues.get("notification"):
            logger.warning(
                "Sin cola de notificaciones. Usá --telegram-direct o desplegá "
                "prode-match-notify-%s",
                args.env,
            )

    if args.mode == "api":
        from src.clients.api_football_mock import MockApiFootballClient
        from src.dao.dynamo.match_dao import MatchDAO
        from src.dao.dynamo.result_dao import ResultDAO
        from src.services.result_poller_service import ResultPollerService

        if args.replace_result and args.api_match_id is not None:
            from src.clients.api_football_mock import MockApiFootballClient as _Mock

            fx = _Mock(args.mock_api_path).get_fixture(int(args.api_match_id))
            if fx:
                m = MatchDAO().find_by_teams(fx.home_team, fx.away_team)
                if m and ResultDAO().get_raw(m["match_id"]):
                    ResultDAO().delete_result(m["match_id"])
                    logger.info("RESULT borrado %s", m["match_id"][:8])

        client = MockApiFootballClient(args.mock_api_path)
        svc = ResultPollerService(api_client=client)
        ids = [args.api_match_id] if args.api_match_id is not None else None
        out = svc.poll_once(
            api_match_ids=ids,
            dry_run=args.dry_run,
            telegram_direct=args.telegram_direct,
        )
        print(json.dumps(out, indent=2))
        if args.with_scoring and not args.dry_run and out.get("processed"):
            from src.services.scoring_service import ScoringService

            for mid in out["processed"]:
                if len(mid) < 20:
                    continue
                scoring_out = ScoringService().process_finish_match(
                    mid, force=args.replace_result
                )
                logger.info(
                    "Scoring %s: scored=%s",
                    mid[:8],
                    scoring_out.scored,
                )
        return 0

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
            logger.error("Partido no encontrado %s vs %s", args.teams[0], args.teams[1])
            return 1
        match_ids = [m["match_id"]]
    else:
        match_ids = svc.find_incomplete_match_ids()

    if args.dry_run:
        print(json.dumps({"candidates": match_ids}, indent=2))
        return 0

    results = []
    for mid in match_ids:
        r = svc.collect_result(mid, telegram_direct=args.telegram_direct)
        results.append(
            {
                "match_id": mid,
                "collected": r.to_dict() if r else None,
            }
        )
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
