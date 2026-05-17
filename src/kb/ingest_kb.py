"""
Pipeline local: stubs + subida a S3 (el embed lo hace Lambda kb_ingest).

  python -m src.kb.ingest_kb --write-stubs
  python -m src.kb.ingest_kb --upload    # KB_S3_BUCKET
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import boto3

MUNDIALES_YEARS = [
    1930, 1934, 1938, 1950, 1954, 1958, 1962, 1966,
    1970, 1974, 1978, 1982, 1986, 1990, 1994, 1998,
    2002, 2006, 2010, 2014, 2018, 2022,
]

SOURCES: dict[str, dict] = {
    "knowledge-base/reglas/laws-of-the-game.md": {
        "url": "https://www.theifab.com/laws-of-the-game-documents/",
        "description": "17 Leyes del Juego IFAB 2024/25",
    },
    "knowledge-base/mundiales/historia-general.md": {
        "url": "https://en.wikipedia.org/wiki/FIFA_World_Cup",
        "description": "Historia completa del Mundial FIFA",
    },
    "knowledge-base/mundiales/records-estadisticas.md": {
        "url": "https://en.wikipedia.org/wiki/FIFA_World_Cup_records_and_statistics",
        "description": "Récords y estadísticas históricas",
    },
    "knowledge-base/mundiales/2026/sedes.md": {
        "url": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup",
        "description": "Sedes y formato Mundial 2026",
    },
    "knowledge-base/mundiales/2026/grupos.md": {
        "url": "https://www.roadtrips.com/world-cup/2026-world-cup-packages/schedule/",
        "description": "Grupos Mundial 2026",
    },
    "knowledge-base/tacticas/evolucion-tacticas.md": {
        "url": "https://escored.com/features/how-football-tactics-are-evolving/",
        "description": "Evolución táctica",
    },
    "knowledge-base/tacticas/tiki-taka.md": {
        "url": "https://the-footballanalyst.com/tiki-taka-football-tactics-explained/",
        "description": "Tiki-Taka",
    },
}

for year in MUNDIALES_YEARS:
    SOURCES[f"knowledge-base/mundiales/ediciones/{year}.md"] = {
        "url": f"https://en.wikipedia.org/wiki/{year}_FIFA_World_Cup",
        "description": f"Mundial FIFA {year}",
    }

REPO_ROOT = Path(__file__).resolve().parents[2]


def _edition_stub(year: int) -> str:
    return f"""# Mundial FIFA {year}

## Datos generales
Documento base para ingesta. Completar con scraper o edición manual.

## Fuente
https://en.wikipedia.org/wiki/{year}_FIFA_World_Cup
"""


def write_stubs() -> int:
    written = 0
    for rel_path, meta in SOURCES.items():
        path = REPO_ROOT / rel_path
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if "/ediciones/" in rel_path:
            year = int(path.stem)
            path.write_text(_edition_stub(year), encoding="utf-8")
        else:
            path.write_text(
                f"# {meta['description']}\n\n"
                f"Contenido pendiente de ingesta.\n\n"
                f"## Fuente\n{meta['url']}\n",
                encoding="utf-8",
            )
        written += 1
    return written


def upload_to_s3(bucket: str) -> int:
    s3 = boto3.client("s3")
    kb_root = REPO_ROOT / "knowledge-base"
    count = 0
    for path in kb_root.rglob("*.md"):
        key = str(path.relative_to(REPO_ROOT))
        s3.upload_file(str(path), bucket, key)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta KB Prode Mundial")
    parser.add_argument("--write-stubs", action="store_true")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    if args.write_stubs:
        print(f"Stubs escritos: {write_stubs()}")
    if args.upload:
        bucket = os.environ.get("KB_S3_BUCKET", "").strip()
        if not bucket:
            raise SystemExit("Definí KB_S3_BUCKET")
        print(f"Archivos subidos: {upload_to_s3(bucket)}")


if __name__ == "__main__":
    main()
