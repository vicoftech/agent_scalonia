"""Cliente wc2026api.com → registros de partido Prode (DynamoDB MATCH#/DETAILS)."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from src.fixtures.match_fixture_builder import match_uuid

API_BASE = "https://api.wc2026api.com"
GROUP_LETTERS = [chr(c) for c in range(ord("A"), ord("L") + 1)]
KNOCKOUT_ROUNDS = ("R32", "R16", "QF", "SF", "3rd", "final")

_COUNTRY_TO_CODE = {
    "mexico": "MEX",
    "méxico": "MEX",
    "usa": "USA",
    "united states": "USA",
    "canada": "CAN",
    "canadá": "CAN",
}

_ROUND_TO_PHASE = {
    "group": "GROUP",
    "r32": "ROUND_OF_32",
    "r16": "ROUND_OF_16",
    "qf": "QUARTER_FINAL",
    "sf": "SEMI_FINAL",
    "3rd": "THIRD_PLACE",
    "third": "THIRD_PLACE",
    "final": "FINAL",
}


def api_bearer_token() -> str:
    token = (
        os.environ.get("WC2026_API_BEARER_TOKEN", "").strip()
        or os.environ.get("WC2026_API_TOKEN", "").strip()
    )
    if not token:
        raise RuntimeError(
            "Definí WC2026_API_BEARER_TOKEN (Bearer wc26_...) — no commitear el token."
        )
    return token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "accept": "*/*"}


def fetch_matches(
    *,
    token: str,
    group: str | None = None,
    round_name: str | None = None,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {}
    if group:
        params["group"] = group.upper()[:1]
    if round_name:
        params["round"] = round_name
    url = f"{API_BASE}/matches"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params or None, headers=_headers(token))
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "matches" in data:
        return data["matches"]
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    raise ValueError(f"Respuesta inesperada de {url}: {type(data)}")


def fetch_full_fixture(*, token: str) -> list[dict[str, Any]]:
    """72 partidos de grupos A–L + eliminatorias (R32 … final)."""
    seen_api_ids: set[int] = set()
    raw: list[dict[str, Any]] = []

    for letter in GROUP_LETTERS:
        for row in fetch_matches(token=token, group=letter):
            api_id = row.get("id")
            if api_id is not None and api_id in seen_api_ids:
                continue
            if api_id is not None:
                seen_api_ids.add(api_id)
            raw.append(row)

    for rnd in KNOCKOUT_ROUNDS:
        for row in fetch_matches(token=token, round_name=rnd):
            api_id = row.get("id")
            if api_id is not None and api_id in seen_api_ids:
                continue
            if api_id is not None:
                seen_api_ids.add(api_id)
            raw.append(row)

    return raw


def _normalize_country(value: str | None) -> str:
    if not value:
        return ""
    key = value.strip().lower()
    if key in _COUNTRY_TO_CODE:
        return _COUNTRY_TO_CODE[key]
    up = value.strip().upper()
    if len(up) == 3 and up.isalpha():
        return up
    return value.strip()


def _normalize_kickoff(value: str | None) -> str:
    if not value:
        return ""
    v = value.strip().replace(".000Z", "Z").replace("+00:00", "Z")
    if not v.endswith("Z") and "T" in v:
        v = f"{v}Z"
    return v


def _normalize_status(value: str | None) -> str:
    if not value:
        return "SCHEDULED"
    mapping = {
        "scheduled": "SCHEDULED",
        "live": "LIVE",
        "finished": "FINISHED",
        "completed": "FINISHED",
        "postponed": "POSTPONED",
        "cancelled": "CANCELLED",
    }
    return mapping.get(value.strip().lower(), value.strip().upper())


def _phase_from_api(row: dict[str, Any]) -> str:
    rnd = str(row.get("round") or "").strip().lower()
    return _ROUND_TO_PHASE.get(rnd, rnd.upper() if rnd else "GROUP")


def _team_code(row: dict[str, Any], side: str) -> str:
    code = row.get(f"{side}_team_code") or row.get(f"{side}_team") or ""
    code = str(code).strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code):
        return code
    if len(code) > 3:
        return code[:3]
    return code or "TBD"


def api_row_to_match(row: dict[str, Any]) -> dict[str, Any]:
    """Mapea un ítem de la API al schema de ingest (MATCH#/DETAILS)."""
    match_number = int(row["match_number"])
    phase = _phase_from_api(row)
    group_letter = None
    if phase == "GROUP":
        gn = row.get("group_name") or row.get("group")
        if gn:
            group_letter = str(gn).upper()[:1]

    city = (row.get("stadium_city") or row.get("city") or "").strip()
    if city.endswith(", USA") or city.endswith(", US"):
        city = city.rsplit(",", 1)[0].strip()

    return {
        "match_id": match_uuid(match_number),
        "match_number": match_number,
        "home_team": _team_code(row, "home"),
        "away_team": _team_code(row, "away"),
        "phase": phase,
        "group_letter": group_letter,
        "kickoff_utc": _normalize_kickoff(row.get("kickoff_utc")),
        "venue": (row.get("stadium") or row.get("venue") or "").strip() or "Por confirmar",
        "city": city or "Por confirmar",
        "country": _normalize_country(row.get("stadium_country") or row.get("country")),
        "status": _normalize_status(row.get("status")),
        "veda_active": False,
        "result_processed": False,
        "round": str(row.get("round") or "").lower(),
        "api_match_id": row.get("id"),
        "home_team_name": row.get("home_team"),
        "away_team_name": row.get("away_team"),
    }


def build_fixture_document(
    rows: list[dict[str, Any]],
    *,
    source: str = "wc2026api.com",
) -> dict[str, Any]:
    matches = [api_row_to_match(r) for r in rows]
    matches.sort(key=lambda m: int(m["match_number"]))
    return {
        "schema_version": 1,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "match_count": len(matches),
        "matches": matches,
    }
