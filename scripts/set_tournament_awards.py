#!/usr/bin/env python3
"""Carga premios oficiales TOURNAMENT#2026/AWARDS — SPEC-2026-048."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dao.dynamo.tournament_prediction_dao import TournamentPredictionDAO
from src.services.tournament_scoring_service import TournamentScoringService


def main() -> None:
    p = argparse.ArgumentParser(description="Set tournament awards and optionally score")
    p.add_argument("--file", required=True, help="JSON con campos AWARDS")
    p.add_argument("--score", action="store_true", help="Ejecutar process_tournament_awards")
    p.add_argument("--table", default=os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))
    args = p.parse_args()

    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)

    dao = TournamentPredictionDAO(table_name=args.table)
    dao.put_awards(data)
    print("AWARDS cargados en TOURNAMENT#2026/AWARDS")

    if args.score:
        result = TournamentScoringService(prediction_dao=dao).process_tournament_awards()
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
