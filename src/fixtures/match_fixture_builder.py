"""Genera fixture JSON de fase de grupos (72 partidos)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from src.fixtures.mundial2026_groups import GROUP_TEAMS, ROUND_ROBIN_PAIRINGS

NS_MATCH = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def match_uuid(match_number: int) -> str:
    return str(uuid.uuid5(NS_MATCH, f"prode-mundial-2026-match-{match_number}"))


def build_group_stage_matches(
    *,
    start_utc: datetime | None = None,
    hours_between: int = 3,
) -> list[dict]:
    """
    72 partidos de fase de grupos con kickoffs escalonados.
    Sedes son placeholders editables en el JSON antes de ingest.
    """
    start = start_utc or datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)
    matches: list[dict] = []
    match_number = 1
    slot = 0

    for letter in sorted(GROUP_TEAMS.keys()):
        teams = GROUP_TEAMS[letter]
        for hi, ai in ROUND_ROBIN_PAIRINGS:
            kickoff = start + timedelta(hours=slot * hours_between)
            slot += 1
            matches.append(
                {
                    "match_id": match_uuid(match_number),
                    "match_number": match_number,
                    "home_team": teams[hi],
                    "away_team": teams[ai],
                    "phase": "GROUP",
                    "group_letter": letter,
                    "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                    "venue": "Por confirmar",
                    "city": "Por confirmar",
                    "country": "USA",
                    "status": "SCHEDULED",
                    "veda_active": False,
                    "result_processed": False,
                }
            )
            match_number += 1

    return matches
