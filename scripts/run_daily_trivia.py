#!/usr/bin/env python3
"""Publica la trivia diaria general (historias de mundiales) en DynamoDB."""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publicar trivia diaria general")
    parser.add_argument("--env", default="dev", help="Entorno (dev|prod)")
    parser.add_argument("--table", default="", help="Override DYNAMODB_TABLE")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Publicar ya (ignora horario 10:00 ART / 2h antes del partido y JOB_CTRL)",
    )
    parser.add_argument("--created-by", default="SYSTEM", help="user_id auditoría")
    args = parser.parse_args()

    table = args.table or f"ProdeTable-{args.env}"
    os.environ["DYNAMODB_TABLE"] = table

    from src.services.trivia_service import TriviaService

    result = TriviaService().publish_daily_general(
        created_by=args.created_by,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok_status = {"CREATED", "SKIPPED", "NOT_YET"}
    return 0 if result.get("status") in ok_status else 1


if __name__ == "__main__":
    raise SystemExit(main())
