#!/usr/bin/env python3
"""
Descarga el fixture completo desde wc2026api.com y escribe el JSON canónico en data/.

Fuente de verdad local: data/worldcup2026_matches.json
  - 72 partidos: GET /matches?group=A … group=L
  - 32 eliminatorias: round=R32, R16, QF, SF, 3rd, final

Token (nunca en el repo):
  export WC2026_API_BEARER_TOKEN='wc26_...'

Uso:
  python scripts/sync_fixture_from_api.py
  python scripts/sync_fixture_from_api.py --output data/worldcup2026_matches.json
  python scripts/sync_fixture_from_api.py --ingest --env dev --replace
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

from src.fixtures.wc2026_api import api_bearer_token, build_fixture_document, fetch_full_fixture

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = ROOT / "data" / "worldcup2026_matches.json"


def main() -> None:
    p = argparse.ArgumentParser(description="Sync fixture wc2026api.com → data/*.json")
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"JSON canónico (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    p.add_argument("--ingest", action="store_true", help="Cargar a DynamoDB tras escribir JSON")
    p.add_argument("--env", default="dev", help="Sufijo ProdeTable-{env} para --ingest")
    p.add_argument("--replace", action="store_true", help="Borrar MATCH# previos antes de ingest")
    p.add_argument("--dry-run", action="store_true", help="Solo fetch + log, no escribir")
    args = p.parse_args()

    token = api_bearer_token()
    logger.info("Fetching groups A–L + knockout rounds from wc2026api.com …")
    raw = fetch_full_fixture(token=token)
    doc = build_fixture_document(raw)
    logger.info(
        "Fetched %s API rows → %s matches (group=%s knockout=%s)",
        len(raw),
        doc["match_count"],
        sum(1 for m in doc["matches"] if m.get("phase") == "GROUP"),
        sum(1 for m in doc["matches"] if m.get("phase") != "GROUP"),
    )

    if args.dry_run:
        for m in doc["matches"][:3]:
            logger.info(
                "sample #%s %s vs %s %s %s",
                m["match_number"],
                m["home_team"],
                m["away_team"],
                m.get("kickoff_utc"),
                m.get("city"),
            )
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Wrote %s (%s matches)", args.output, doc["match_count"])

    if args.ingest:
        import subprocess

        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "ingest_matches.py"),
            "--env",
            args.env,
            "--from-json",
            str(args.output),
        ]
        if args.replace:
            cmd.append("--replace")
        subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
