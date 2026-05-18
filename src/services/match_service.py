"""Consultas de partidos — DynamoDB (agente) / Aurora espejo vía sync."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from src.dao.dynamo.match_dao import MatchDAO
from src.fixtures.mundial2026_groups import GROUP_TEAMS

# Alias → código FIFA (consultas en lenguaje natural)
TEAM_ALIASES: dict[str, str] = {
    "mexico": "MEX",
    "méxico": "MEX",
    "canada": "CAN",
    "canadá": "CAN",
    "usa": "USA",
    "estados unidos": "USA",
    "argentina": "ARG",
    "brasil": "BRA",
    "brazil": "BRA",
    "francia": "FRA",
    "france": "FRA",
    "alemania": "GER",
    "germany": "GER",
    "españa": "ESP",
    "spain": "ESP",
    "inglaterra": "ENG",
    "england": "ENG",
    "portugal": "POR",
    "holanda": "NED",
    "netherlands": "NED",
    "uruguay": "URU",
    "colombia": "COL",
    "ecuador": "ECU",
    "chile": "CHI",
    "corea": "KOR",
    "korea": "KOR",
    "japon": "JPN",
    "japón": "JPN",
    "japan": "JPN",
    "marruecos": "MAR",
    "senegal": "SEN",
    "croacia": "CRO",
    "croatia": "CRO",
}


def _parse_dt(value: str) -> datetime:
    v = value.replace("Z", "+00:00")
    return datetime.fromisoformat(v)


def normalize_team_code(name: str) -> str | None:
    """Código FIFA o None si no se reconoce."""
    raw = (name or "").strip()
    if not raw:
        return None
    up = raw.upper()
    if re.fullmatch(r"[A-Z]{3}", up):
        return up
    low = raw.lower()
    if low in TEAM_ALIASES:
        return TEAM_ALIASES[low]
    for alias, code in TEAM_ALIASES.items():
        if alias in low:
            return code
    return None


class MatchService:
    def __init__(self, dao: MatchDAO | None = None):
        self._dao = dao or MatchDAO()

    def list_all(self) -> list[dict[str, Any]]:
        return self._dao.list_matches()

    def get(self, *, match_id: str | None = None, match_number: int | None = None) -> dict | None:
        if match_id:
            return self._dao.get_match(match_id)
        if match_number is not None:
            return self._dao.get_by_match_number(match_number)
        return None

    def search(
        self,
        *,
        team: str | None = None,
        city: str | None = None,
        group_letter: str | None = None,
        phase: str | None = None,
        status: str | None = None,
        on_date: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = self.list_all()
        code = normalize_team_code(team) if team else None
        gl = group_letter.upper()[:1] if group_letter else None
        ph = phase.upper() if phase else None
        st = status.upper() if status else None

        def _match_row(m: dict) -> bool:
            if code and code not in (m.get("home_team"), m.get("away_team")):
                return False
            if gl and (m.get("group_letter") or "").upper() != gl:
                return False
            if ph and (m.get("phase") or "").upper() != ph:
                return False
            if st and (m.get("status") or "").upper() != st:
                return False
            if city and city.lower() not in (m.get("city") or "").lower():
                return False
            try:
                kick = _parse_dt(m["kickoff_utc"])
            except (KeyError, ValueError):
                return False
            if on_date:
                target = datetime.fromisoformat(on_date).date()
                if kick.date() != target:
                    return False
            if from_date:
                if kick.date() < datetime.fromisoformat(from_date).date():
                    return False
            if to_date:
                if kick.date() > datetime.fromisoformat(to_date).date():
                    return False
            return True

        filtered = [m for m in rows if _match_row(m)]
        filtered.sort(key=lambda m: m.get("kickoff_utc", ""))
        return filtered[: max(1, min(limit, 50))]

    def next_matches(self, limit: int = 10) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        upcoming = []
        for m in self.list_all():
            if (m.get("status") or "").upper() != "SCHEDULED":
                continue
            try:
                if _parse_dt(m["kickoff_utc"]) >= now:
                    upcoming.append(m)
            except (KeyError, ValueError):
                continue
        upcoming.sort(key=lambda m: m["kickoff_utc"])
        return upcoming[: max(1, min(limit, 30))]

    def group_fixture(self, group_letter: str) -> list[dict[str, Any]]:
        gl = group_letter.upper()[:1]
        return self.search(group_letter=gl, limit=50)

    def teams_in_group(self, group_letter: str) -> list[str]:
        return list(GROUP_TEAMS.get(group_letter.upper()[:1], []))

    @staticmethod
    def format_match(m: dict[str, Any], *, include_id: bool = False) -> str:
        grp = f" Grupo {m['group_letter']}" if m.get("group_letter") else ""
        phase = m.get("phase", "?")
        line = (
            f"#{m.get('match_number')} {m.get('home_team')} vs {m.get('away_team')} "
            f"({phase}{grp}) — {m.get('kickoff_utc')} UTC"
        )
        if m.get("city") and m.get("city") != "Por confirmar":
            line += f" · {m.get('city')}"
        if m.get("venue") and m.get("venue") != "Por confirmar":
            line += f", {m.get('venue')}"
        if m.get("status"):
            line += f" [{m.get('status')}]"
        if include_id:
            line += f" id={m.get('match_id')}"
        return line

    def format_list(self, matches: list[dict[str, Any]], *, header: str = "") -> str:
        if not matches:
            return header + "No hay partidos que coincidan con esa consulta."
        lines = [header] if header else []
        for m in matches:
            lines.append(f"- {self.format_match(m)}")
        return "\n".join(lines).strip()
