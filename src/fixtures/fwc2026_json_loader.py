"""Convierte data/fixtures/FWC2026.json → registros MATCH#/DETAILS para DynamoDB."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.fixtures.match_fixture_builder import match_uuid

ET = ZoneInfo("America/New_York")

# venue (etiqueta FWC2026) → (estadio, ciudad, país ISO3)
VENUE_MAP: dict[str, tuple[str, str, str]] = {
    "Ciudad de México": ("Estadio Azteca", "Ciudad de México", "MEX"),
    "Guadalajara": ("Estadio Akron", "Guadalajara", "MEX"),
    "Monterrey": ("Estadio BBVA", "Monterrey", "MEX"),
    "Toronto": ("BMO Field", "Toronto", "CAN"),
    "Vancouver": ("BC Place", "Vancouver", "CAN"),
    "Los Ángeles": ("SoFi Stadium", "Inglewood", "USA"),
    "Nueva York/Nueva Jersey": ("MetLife Stadium", "East Rutherford", "USA"),
    "Boston": ("Gillette Stadium", "Foxborough", "USA"),
    "Bahía de San Francisco": ("Levi's Stadium", "Santa Clara", "USA"),
    "Atlanta": ("Mercedes-Benz Stadium", "Atlanta", "USA"),
    "Houston": ("NRG Stadium", "Houston", "USA"),
    "Dallas": ("AT&T Stadium", "Arlington", "USA"),
    "Seattle": ("Lumen Field", "Seattle", "USA"),
    "Filadelfia": ("Lincoln Financial Field", "Philadelphia", "USA"),
    "Kansas City": ("Arrowhead Stadium", "Kansas City", "USA"),
    "Miami": ("Hard Rock Stadium", "Miami Gardens", "USA"),
}

PHASE_BY_SECTION = {
    "group_stage": "GROUP",
    "round_of_32": "R16",
    "round_of_16": "QF",
    "quarterfinals": "SF",
    "semifinals": "SF",
    "third_place": "THIRD_PLACE",
    "final": "FINAL",
}


def _kickoff_utc(date: str, time_et: str) -> str:
    h, m = time_et.split(":")
    local = datetime(
        int(date[:4]),
        int(date[5:7]),
        int(date[8:10]),
        int(h),
        int(m),
        tzinfo=ET,
    )
    return local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _venue_fields(venue_label: str) -> tuple[str, str, str]:
    if venue_label in VENUE_MAP:
        return VENUE_MAP[venue_label]
    return (venue_label, venue_label, "USA")


def load_fwc2026_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    matches_block = data.get("matches")
    if not isinstance(matches_block, dict):
        raise ValueError("FWC2026.json: falta objeto matches")

    records: list[dict] = []
    for section, phase in PHASE_BY_SECTION.items():
        rows = matches_block.get(section) or []
        for row in rows:
            mn = int(row["match"])
            stadium, city, country = _venue_fields(row["venue"])
            rec: dict = {
                "match_id": match_uuid(mn),
                "match_number": mn,
                "home_team": row["home"],
                "away_team": row["away"],
                "phase": phase,
                "kickoff_utc": _kickoff_utc(row["date"], row["time_et"]),
                "venue": stadium,
                "city": city,
                "country": country,
                "status": "SCHEDULED",
                "veda_active": False,
                "result_processed": False,
            }
            if phase == "GROUP":
                rec["group_letter"] = row.get("group")
            else:
                rec["group_letter"] = None
            records.append(rec)

    records.sort(key=lambda r: r["match_number"])
    if len(records) != 104:
        raise ValueError(f"Se esperaban 104 partidos, hay {len(records)}")
    return records
