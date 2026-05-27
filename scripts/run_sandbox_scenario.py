#!/usr/bin/env python3
"""
Escenario sandbox DEV_FAST: predicción + resultado oficial + 7 eventos (0–90 s).

Ejemplo KOR 1-3 CZE con extendidas:
  python scripts/run_sandbox_scenario.py --teams KOR CZE --profile asap_dev \\
    --home-goals 1 --away-goals 3 \\
    --red yes --goal-early no --var yes --free-kick no --pen-saved no --pen-scored yes
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


def _parse_bool(raw: str) -> bool:
    v = (raw or "").strip().lower()
    if v in ("1", "true", "yes", "si", "sí", "s"):
        return True
    if v in ("0", "false", "no", "n"):
        return False
    raise argparse.ArgumentTypeError(f"booleano inválido: {raw!r}")


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


def _resolve_user_id(env: str, profile: str | None, region: str, explicit: str | None) -> str:
    if explicit and explicit != "admin":
        return explicit
    import boto3
    from boto3.dynamodb.conditions import Attr

    session = boto3.Session(profile_name=profile, region_name=region)
    table = session.resource("dynamodb").Table(os.environ["DYNAMODB_TABLE"])
    ssm = session.client("ssm")
    try:
        uid = ssm.get_parameter(Name=f"/prode-mundial/{env}/admin_user_id")["Parameter"]["Value"]
        return uid
    except ssm.exceptions.ParameterNotFound:
        pass
    scan = table.scan(
        FilterExpression=Attr("sort_key").eq("PROFILE") & Attr("is_admin").eq(True),
        ProjectionExpression="user_id",
    )
    items = scan.get("Items", [])
    if not items:
        raise SystemExit("No admin en Dynamo; usá --user-id <uuid>")
    return items[0]["user_id"]


def main() -> int:
    p = argparse.ArgumentParser(description="Sandbox + predicción completa (7 eventos)")
    p.add_argument("--env", default="dev")
    p.add_argument("--profile", "-p", default=os.environ.get("AWS_PROFILE") or "asap_dev")
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--match-id")
    p.add_argument("--teams", nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument("--user-id", default="admin", help="UUID o 'admin' (SSM)")
    p.add_argument("--group-id", help="Grupo; default: prediction_group_id del usuario")
    p.add_argument("--home-goals", type=int, required=True)
    p.add_argument("--away-goals", type=int, required=True)
    p.add_argument("--red", type=_parse_bool, required=True)
    p.add_argument("--goal-early", type=_parse_bool, required=True)
    p.add_argument("--var", type=_parse_bool, required=True)
    p.add_argument("--free-kick", type=_parse_bool, required=True)
    p.add_argument("--pen-saved", type=_parse_bool, required=True)
    p.add_argument("--pen-scored", type=_parse_bool, required=True)
    p.add_argument("--cancel-only", action="store_true")
    p.add_argument("--no-provision", action="store_true", help="Solo reset + predicción")
    args = p.parse_args()

    _configure(args.env, args.profile, args.region)

    from src.dao.dynamo.match_dao import MatchDAO
    from src.dao.dynamo.prediction_dao import PredictionDAO
    from src.dao.dynamo.result_dao import ResultDAO
    from src.dao.dynamo.user_dao import UserDAO
    from src.services.match_schedule_sandbox import MatchScheduleSandboxManager
    from src.services.prediction_rules import format_prediction_brief
    from src.services.prediction_service import PredictionService
    from src.services.scoring_service import ScoringService

    dao = MatchDAO()
    if args.match_id:
        match = dao.get_match(args.match_id)
    elif args.teams:
        match = dao.find_by_teams(args.teams[0], args.teams[1])
    else:
        p.error("--match-id o --teams requerido")
    if not match:
        logger.error("Partido no encontrado")
        return 1
    match_id = match["match_id"]

    if args.cancel_only:
        out = MatchScheduleSandboxManager().cancel_sandbox_schedules(match_id)
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("status") == "OK" else 1

    user_id = _resolve_user_id(args.env, args.profile, args.region, args.user_id)
    users = UserDAO()
    profile = users.get_profile(user_id) or {}
    group_id = args.group_id or profile.get("prediction_group_id")
    if not group_id:
        from src.services.prediction_service import PredictionService

        groups = PredictionService()._predictable_groups(user_id)
        if not groups:
            logger.error("Sin grupo privado; pasá --group-id")
            return 1
        group_id = groups[0]
        logger.info("Grupo activo inferido: %s", group_id[:8])

    dao.set_veda_active(match_id, active=False)
    rdao = ResultDAO()
    if rdao.get_raw(match_id):
        rdao.delete_result(match_id)
        logger.info("RESULT borrado")
    reset_n = ScoringService().reset_match_scoring(match_id)
    logger.info("Scoring reset: %s predicciones", reset_n)

    preds = PredictionDAO()
    preds.save_prediction(
        user_id=user_id,
        match_id=match_id,
        group_id=group_id,
        home_goals=args.home_goals,
        away_goals=args.away_goals,
        has_red_card=args.red,
        pred_goal_before_5min=args.goal_early,
        pred_var_used=args.var,
        pred_free_kick_goal=args.free_kick,
        pred_penalty_saved=args.pen_saved,
        pred_penalty_scored=args.pen_scored,
    )
    logger.info("Predicción guardada user=%s group=%s", user_id[:8], group_id[:8])

    pred_svc = PredictionService()
    gname = (pred_svc._groups.get_group(group_id) or {}).get("name", group_id)
    brief = format_prediction_brief(
        preds.get_active(user_id, match_id, group_id) or {},
        match_title=pred_svc.format_match_title(match),
        group_name=gname,
        minutes_to_veda="(sandbox)",
        change_prompt=False,
    )
    print("\n--- Predicción cargada ---\n")
    print(brief)

    sandbox_result = {
        "home_goals": args.home_goals,
        "away_goals": args.away_goals,
        "red_cards": 1 if args.red else 0,
        "goal_before_5min": args.goal_early,
        "var_used": args.var,
        "free_kick_goal": args.free_kick,
        "penalty_saved": args.pen_saved,
        "penalty_scored": args.pen_scored,
        "mvp_name": "Sandbox KOR-CZE",
    }

    if args.no_provision:
        print(json.dumps({"match_id": match_id, "sandbox_result": sandbox_result}, indent=2))
        return 0

    mgr = MatchScheduleSandboxManager()
    mgr.cancel_sandbox_schedules(match_id)
    out = mgr.provision_sandbox_schedules(match_id, sandbox_result=sandbox_result)
    print("\n--- Sandbox (7 eventos / ~90 s) ---\n")
    print(json.dumps(out, indent=2, default=str))
    print(
        "\nEventos: trivia → remind×3 → veda → resultado 1-3 → scoring.\n"
        "En ~75 s activá veda; en ~90 s resultado y puntos en Telegram.\n"
        "Probá /partidos → KOR vs CZE antes y después de la veda."
    )
    return 0 if out.get("status") in ("OK", "PARTIAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
