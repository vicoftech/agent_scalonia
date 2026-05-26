#!/usr/bin/env python3
"""
Prueba local del scoring (FINISH_MATCH) sin depender de SQS.

Ejemplos:
  python scripts/run_scoring_local.py --teams MEX RSA --profile asap_dev --env dev
  python scripts/run_scoring_local.py --match-id <uuid> --profile asap_dev --force
  python scripts/run_scoring_local.py --teams MEX RSA --reset --profile asap_dev
  python scripts/run_scoring_local.py --teams MEX RSA --telegram-direct --profile asap_dev
  # Si ya estaba puntuado, --telegram-direct reenvía desglose; para re-puntuar: --reset
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


def _json_default(obj: object) -> object:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _configure_runtime(env: str, *, profile: str | None, region: str | None) -> None:
    os.environ["DYNAMODB_TABLE"] = os.environ.get(
        "DYNAMODB_TABLE", f"ProdeTable-{env}"
    )
    from src.dao.dynamo.table import configure_aws

    configure_aws(profile=profile, region=region)


def main() -> int:
    p = argparse.ArgumentParser(description="Local scoring (SPEC-022)")
    p.add_argument("--env", default="dev")
    p.add_argument("--profile", "-p", default=os.environ.get("AWS_PROFILE"))
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--match-id")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-puntúa aunque result_processed=true",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Quita SCORED del partido y result_processed=false",
    )
    p.add_argument(
        "--telegram-direct",
        action="store_true",
        help="Envía desglose de puntos por Telegram a cada usuario puntuado",
    )
    args = p.parse_args()

    _configure_runtime(args.env, profile=args.profile, region=args.region)

    from src.dao.dynamo.match_dao import MatchDAO
    from src.services.scoring_service import ScoringService

    dao = MatchDAO()
    if args.match_id:
        match_id = args.match_id
    elif args.teams:
        m = dao.find_by_teams(args.teams[0], args.teams[1])
        if not m:
            logger.error("Partido no encontrado")
            return 1
        match_id = m["match_id"]
    else:
        p.error("--match-id o --teams requerido")

    svc = ScoringService()
    if args.reset:
        n = svc.reset_match_scoring(match_id)
        logger.info("Reset scoring: %s predicciones", n)

    outcome = svc.process_finish_match(match_id, force=args.force or args.reset)
    match = dao.get_match(match_id) or {}
    result_raw = dao.get_result(match_id)

    summary = {
        "match_id": match_id,
        "match_number": int(match["match_number"])
        if match.get("match_number") is not None
        else None,
        "already_processed": outcome.already_processed,
        "scored": outcome.scored,
        "skipped": outcome.skipped,
        "rows": [
            {
                "user_id": r.user_id[:8],
                "group_id": r.group_id[:8] if r.group_id else None,
                "points": r.points,
                "base": r.base_points,
                "extended": r.extended_points,
                "ko": r.ko_points,
                "reason": r.reason,
            }
            for r in outcome.rows
        ],
    }
    print(json.dumps(summary, indent=2, default=_json_default))

    if args.telegram_direct:
        if outcome.scored:
            sent = _send_breakdowns(match_id, match, result_raw, outcome.rows)
        elif outcome.already_processed:
            logger.info(
                "Scoring ya procesado — reenviando desglose desde predicciones SCORED"
            )
            sent = _send_breakdowns_from_db(match_id, match, result_raw)
        else:
            sent = 0
            logger.warning(
                "Sin predicciones puntuadas — usá --reset para volver a puntuar"
            )
        if sent == 0:
            logger.warning(
                "No se envió ningún Telegram (¿tg_chat_id o sin predicciones SCORED?)"
            )

    return 0 if outcome.scored or outcome.already_processed else 1


def _send_breakdowns(
    match_id: str,
    match: dict,
    result_raw: dict | None,
    rows: list,
) -> int:
    targets = [
        (r.user_id, r.group_id)
        for r in rows
        if not getattr(r, "skipped", False)
    ]
    return _send_breakdowns_to_users(match_id, match, result_raw, targets)


def _send_breakdowns_from_db(
    match_id: str,
    match: dict,
    result_raw: dict | None,
) -> int:
    from src.dao.dynamo.prediction_dao import PredictionDAO, STATUS_SCORED

    preds = PredictionDAO().list_predictions_for_match(
        match_id, statuses=(STATUS_SCORED,)
    )
    targets = [(p["user_id"], p["group_id"]) for p in preds if p.get("user_id")]
    if not targets:
        logger.warning("No hay predicciones SCORED para este partido")
    return _send_breakdowns_to_users(match_id, match, result_raw, targets)


def _send_breakdowns_to_users(
    match_id: str,
    match: dict,
    result_raw: dict | None,
    targets: list[tuple[str, str]],
) -> int:
    from src.clients.telegram_client import get_bot_token, send_telegram_message
    from src.dao.dynamo.group_dao import GroupDAO
    from src.dao.dynamo.prediction_dao import PredictionDAO
    from src.dao.dynamo.user_dao import UserDAO
    from src.services.prediction_result_report import format_finished_match_report

    groups = GroupDAO()
    users = UserDAO()
    preds = PredictionDAO()
    token = get_bot_token()
    sent = 0
    skipped = 0

    for user_id, group_id in targets:
        pred = preds.get_for_group(user_id, match_id, group_id)
        if not pred:
            logger.warning(
                "Sin predicción user=%s group=%s",
                user_id[:8],
                (group_id or "")[:8],
            )
            skipped += 1
            continue
        profile = users.get_profile(user_id) or {}
        chat_id = profile.get("tg_chat_id")
        if not chat_id:
            logger.warning("Usuario %s sin tg_chat_id", user_id[:8])
            skipped += 1
            continue
        g = groups.get_group(group_id) or {}
        text = format_finished_match_report(
            match,
            group_name=g.get("name") or group_id[:8],
            result=result_raw,
            prediction=pred,
        )
        try:
            send_telegram_message(int(chat_id), text, token)
            sent += 1
            logger.info(
                "Desglose enviado user=%s group=%s pts=%s",
                user_id[:8],
                (group_id or "")[:8],
                pred.get("points_earned"),
            )
        except Exception:
            logger.exception("Telegram desglose falló user=%s", user_id[:8])
            skipped += 1

    logger.info("Desglose Telegram: sent=%s skipped=%s", sent, skipped)
    return sent


if __name__ == "__main__":
    raise SystemExit(main())
