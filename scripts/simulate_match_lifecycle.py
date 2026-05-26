#!/usr/bin/env python3
"""
Simula los 7 eventos de SPEC-2026-032 sin EventBridge Scheduler (desarrollo local).

Cada paso invoca el mismo código que usaría la Lambda programada.
Todos los pasos invocan Lambdas/servicios locales; usar --telegram-direct para envíos reales.

Uso:
  # Un paso
  python scripts/simulate_match_lifecycle.py --teams MEX RSA --step result \\
    --profile asap_dev --mock-web-search --telegram-direct

  # Secuencia completa (lo que esté implementado; incluye scoring)
  python scripts/simulate_match_lifecycle.py --teams MEX RSA --step all \\
    --profile asap_dev --replace-result --mock-web-search --telegram-direct --reset-scoring

  # Listar pasos
  python scripts/simulate_match_lifecycle.py --list-steps

Requiere: AWS profile con DynamoDB dev, TELEGRAM_BOT_TOKEN o secret, opcional TELEGRAM_SSL_VERIFY=0.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

STEPS = (
    "trivia",
    "remind-1",
    "remind-2",
    "remind-3",
    "veda",
    "result",
    "scoring",
    "all",
)


def _json_default(obj: object) -> object:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(type(obj).__name__)


def _configure(env: str, profile: str | None, region: str | None) -> None:
    os.environ["DYNAMODB_TABLE"] = os.environ.get("DYNAMODB_TABLE", f"ProdeTable-{env}")
    from src.dao.dynamo.table import configure_aws

    configure_aws(profile=profile, region=region)


def _resolve_match_id(args, dao) -> str:
    if args.match_id:
        return args.match_id
    m = dao.find_by_teams(args.teams[0], args.teams[1])
    if not m:
        raise SystemExit(f"Partido no encontrado: {args.teams[0]} vs {args.teams[1]}")
    return m["match_id"]


def _step_trivia(match_id: str, *, dry_run: bool) -> dict:
    if dry_run:
        return {"status": "DRY_RUN", "step": "trivia"}
    from infrastructure.lambdas.trivia_pre_match_dispatcher import handler as h

    return h.handler({"match_id": match_id}, None)


def _step_reminder(
    match_id: str, tier: int, *, dry_run: bool, telegram_direct: bool
) -> dict:
    if dry_run:
        return {"status": "DRY_RUN", "step": f"remind-{tier}"}
    from infrastructure.lambdas.match_reminder_dispatcher import handler as h

    return h.handler(
        {
            "match_id": match_id,
            "reminder_tier": tier,
            "telegram_direct": telegram_direct,
        },
        None,
    )


def _step_veda(
    match_id: str, *, dry_run: bool, telegram_direct: bool, force: bool
) -> dict:
    if dry_run:
        return {"status": "DRY_RUN", "step": "veda"}
    from infrastructure.lambdas.veda_activator import handler as h

    return h.handler(
        {
            "match_id": match_id,
            "telegram_direct": telegram_direct,
            "force": force,
        },
        None,
    )


def _step_trivia_force(match_id: str) -> dict:
    """Trivia aunque el partido no esté SCHEDULED (solo simulación local)."""
    from datetime import datetime, timedelta, timezone

    from src.dao.dynamo.match_dao import MatchDAO
    from src.services.trivia_service import TriviaService

    m = MatchDAO().get_match(match_id)
    if not m:
        return {"status": "NOT_FOUND"}
    svc = TriviaService()
    q = svc.generate_pre_match_trivia(m)
    trivia_id = str(q.get("match_id", match_id))[:8] or m.get("match_number")
    now = datetime.now(timezone.utc)
    svc._trivia.put_broadcast_trivia(
        {
            "trivia_id": str(trivia_id)[:8],
            "type": "PRE_MATCH",
            "level": "EXPERT",
            "points": 5,
            "match_id": match_id,
            "group_id": "GLOBAL",
            "status": "SENT",
            "sent_at": now.isoformat(),
            "closes_at": (now + timedelta(hours=2)).isoformat(),
            **q,
        }
    )
    return {"status": "OK", "sent": 1, "forced": True}


def _step_result(
    match_id: str,
    *,
    dry_run: bool,
    replace: bool,
    mock_web: bool,
    telegram_direct: bool,
) -> dict:
    if dry_run:
        return {"status": "DRY_RUN", "step": "result"}
    os.environ["RESULT_SKIP_KICKOFF_CHECK"] = "1"
    if mock_web:
        from src.testing.fake_web_search import install_fake_web_search

        install_fake_web_search()
    if replace:
        from src.dao.dynamo.result_dao import ResultDAO

        if ResultDAO().get_raw(match_id):
            ResultDAO().delete_result(match_id)
            logger.info("RESULT borrado para re-disparar notify")

    from src.services.result_service import ResultService

    r = ResultService().collect_result(
        match_id, telegram_direct=telegram_direct, force_notify=telegram_direct
    )
    return {"status": "OK", "collected": r is not None}


def _step_scoring(
    match_id: str,
    *,
    dry_run: bool,
    reset: bool,
    telegram_direct: bool,
) -> dict:
    if dry_run:
        return {"status": "DRY_RUN", "step": "scoring"}
    from src.services.scoring_service import ScoringService

    svc = ScoringService()
    if reset:
        svc.reset_match_scoring(match_id)
    outcome = svc.process_finish_match(match_id, force=reset)
    result = {
        "status": "OK",
        "scored": outcome.scored,
        "already_processed": outcome.already_processed,
        "rows": [
            {
                "user": r.user_id[:8],
                "group": (r.group_id or "")[:8],
                "points": r.points,
            }
            for r in outcome.rows
        ],
    }
    if telegram_direct and (outcome.scored or outcome.already_processed):
        from scripts.run_scoring_local import _send_breakdowns_from_db
        from src.dao.dynamo.match_dao import MatchDAO

        match = MatchDAO().get_match(match_id) or {}
        sent = _send_breakdowns_from_db(match_id, match, MatchDAO().get_result(match_id))
        result["telegram_sent"] = sent
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description="Simula eventos SPEC-032 por partido (sin Scheduler)"
    )
    p.add_argument("--env", default="dev")
    p.add_argument("--profile", "-p", default=os.environ.get("AWS_PROFILE"))
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--match-id")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument(
        "--step",
        choices=STEPS,
        default="all",
        help="Paso a simular (all = orden 1→7)",
    )
    p.add_argument("--list-steps", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--telegram-direct", action="store_true")
    p.add_argument("--mock-web-search", action="store_true")
    p.add_argument("--replace-result", action="store_true")
    p.add_argument("--reset-scoring", action="store_true", help="Antes de scoring")
    p.add_argument(
        "--reset-veda",
        action="store_true",
        help="Re-activa veda (force) aunque ya esté activa",
    )
    p.add_argument(
        "--force-trivia",
        action="store_true",
        help="Genera trivia aunque status != SCHEDULED",
    )
    args = p.parse_args()

    if args.list_steps:
        print(
            """
Pasos SPEC-032 (orden cronológico antes del partido → después):

  1. trivia      (−2h)  → trivia_pre_match_dispatcher [parcial: guarda trivia, poco Telegram]
  2. remind-1    (−1h)  → match_reminder_dispatcher (tier 1)
  3. remind-2    (−30m) → match_reminder_dispatcher (tier 2)
  4. remind-3    (−15m) → match_reminder_dispatcher (tier 3)
  5. veda        (−30m) → veda_activator (+ --telegram-direct)
  6. result      (+110m) → ResultService.collect_result (+ --mock-web-search)
  7. scoring     (post)  → ScoringService.process_finish_match

Comando ejemplo:
  python scripts/simulate_match_lifecycle.py --teams MEX RSA --step all \\
    --profile asap_dev --replace-result --mock-web-search \\
    --telegram-direct --reset-scoring
"""
        )
        return 0

    if not args.match_id and not args.teams:
        p.error("--match-id o --teams requerido")

    _configure(args.env, args.profile, args.region)
    from src.dao.dynamo.match_dao import MatchDAO

    dao = MatchDAO()
    match_id = _resolve_match_id(args, dao)
    logger.info("Simulando match_id=%s step=%s", match_id[:8], args.step)

    steps = list(STEPS[:-1]) if args.step == "all" else [args.step]
    results: dict[str, object] = {}

    for step in steps:
        logger.info("=== Paso: %s ===", step)
        if step == "trivia":
            if args.dry_run:
                results[step] = _step_trivia(match_id, dry_run=True)
            elif args.force_trivia:
                results[step] = _step_trivia_force(match_id)
            else:
                results[step] = _step_trivia(match_id, dry_run=False)
        elif step == "remind-1":
            results[step] = _step_reminder(
                match_id, 1, dry_run=args.dry_run, telegram_direct=args.telegram_direct
            )
        elif step == "remind-2":
            results[step] = _step_reminder(
                match_id, 2, dry_run=args.dry_run, telegram_direct=args.telegram_direct
            )
        elif step == "remind-3":
            results[step] = _step_reminder(
                match_id, 3, dry_run=args.dry_run, telegram_direct=args.telegram_direct
            )
        elif step == "veda":
            results[step] = _step_veda(
                match_id,
                dry_run=args.dry_run,
                telegram_direct=args.telegram_direct,
                force=args.reset_veda,
            )
        elif step == "result":
            results[step] = _step_result(
                match_id,
                dry_run=args.dry_run,
                replace=args.replace_result,
                mock_web=args.mock_web_search,
                telegram_direct=args.telegram_direct,
            )
        elif step == "scoring":
            results[step] = _step_scoring(
                match_id,
                dry_run=args.dry_run,
                reset=args.reset_scoring or args.replace_result,
                telegram_direct=args.telegram_direct,
            )

    print(json.dumps(results, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
