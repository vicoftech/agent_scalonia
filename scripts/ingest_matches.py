#!/usr/bin/env python3
"""
Carga el fixture en DynamoDB (MATCH#/DETAILS). Aurora se actualiza vía sync_dynamo_to_aurora.

Uso:
  python scripts/ingest_matches.py --env dev --generate-group-stage
  python scripts/ingest_matches.py --env dev --from-json data/worldcup2026_matches.json --replace
  python scripts/ingest_matches.py --env dev --from-json data/fixtures/fwc2026_fixture.json --replace
  python scripts/ingest_matches.py --env dev --from-json data/fixtures/mundial2026_matches.json
  python scripts/ingest_matches.py --generate-group-stage --write-json data/fixtures/mundial2026_matches.json --dry-run

Requiere: AWS credentials con PutItem en ProdeTable-{env}.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dao.dynamo.match_dao import MatchDAO
from src.fixtures.match_fixture_builder import build_group_stage_matches, match_uuid

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _load_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "matches" in data:
        return data["matches"]
    raise ValueError('JSON debe ser lista de partidos o { "matches": [...] }')


def _ensure_ids(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        rec = dict(r)
        mn = int(rec["match_number"])
        rec.setdefault("match_id", match_uuid(mn))
        rec.setdefault("status", "SCHEDULED")
        rec.setdefault("veda_active", False)
        rec.setdefault("result_processed", False)
        out.append(rec)
    return out


def ingest(records: list[dict], *, table: str, dry_run: bool, replace: bool = False) -> int:
    dao = MatchDAO(table)
    if replace and not dry_run:
        removed = dao.delete_all_matches()
        logger.info("Eliminados %s partidos previos en %s", removed, table)
    for rec in records:
        if dry_run:
            logger.info(
                "dry-run #%s %s vs %s %s",
                rec["match_number"],
                rec["home_team"],
                rec["away_team"],
                rec.get("kickoff_utc"),
            )
        else:
            dao.put_match(rec)
    return len(records)


def main() -> None:
    p = argparse.ArgumentParser(description="Ingesta fixture → DynamoDB MATCH#")
    p.add_argument("--env", default="dev", help="Sufijo tabla ProdeTable-{env}")
    p.add_argument("--table", default="", help="Override nombre tabla DynamoDB")
    p.add_argument("--from-json", type=Path, help="Archivo JSON de partidos")
    p.add_argument(
        "--generate-group-stage",
        action="store_true",
        help="Generar 72 partidos fase de grupos",
    )
    p.add_argument("--write-json", type=Path, help="Guardar JSON generado")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--replace",
        action="store_true",
        help="Borra todos los MATCH#/DETAILS antes de cargar el JSON",
    )
    args = p.parse_args()

    table = args.table or f"ProdeTable-{args.env}"
    records: list[dict] | None = None

    if args.generate_group_stage:
        records = build_group_stage_matches()
        if args.write_json:
            args.write_json.parent.mkdir(parents=True, exist_ok=True)
            args.write_json.write_text(
                json.dumps({"matches": records}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            logger.info("JSON escrito: %s (%s partidos)", args.write_json, len(records))

    if args.from_json:
        records = _ensure_ids(_load_json(args.from_json))

    if not records:
        p.error("Indicá --generate-group-stage y/o --from-json")

    records = _ensure_ids(records)
    n = ingest(records, table=table, dry_run=args.dry_run, replace=args.replace)
    if args.dry_run:
        logger.info("Dry-run: %s partidos (tabla %s)", n, table)
    else:
        logger.info("Ingestados %s partidos en %s", n, table)
        logger.info("Aurora: sync vía DynamoDB Stream → sync_dynamo_to_aurora")


if __name__ == "__main__":
    main()
