"""Cuadro eliminatorio FIFA 2026 — cruces según slots 1A/2J/W86 (fixture oficial)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.fixtures.mundial2026_groups import GROUP_TEAMS
from src.services.match_service import normalize_team_code

_PHASE_ORDER = (
    ("round_of_32", "Dieciseisavos de final (16 equipos en llave)"),
    ("round_of_16", "Octavos de final"),
    ("quarterfinals", "Cuartos de final"),
    ("semifinals", "Semifinal"),
)

_PLACEMENT_LABELS = {
    1: "1° del grupo",
    2: "2° del grupo",
}


@dataclass(frozen=True)
class KnockoutRow:
    match_number: int
    phase_key: str
    phase_label: str
    home: str
    away: str
    date: str
    time_et: str
    venue: str


@lru_cache(maxsize=1)
def _load_knockout_rows() -> list[KnockoutRow]:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "fwc2026_bracket.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[KnockoutRow] = []
    for phase_key, phase_label in _PHASE_ORDER:
        for item in data.get(phase_key) or []:
            rows.append(
                KnockoutRow(
                    match_number=int(item["match"]),
                    phase_key=phase_key,
                    phase_label=phase_label,
                    home=str(item["home"]),
                    away=str(item["away"]),
                    date=str(item.get("date", "")),
                    time_et=str(item.get("time_et", "")),
                    venue=str(item.get("venue", "")),
                )
            )
    return rows


def _group_teams_label(group: str) -> str:
    teams = GROUP_TEAMS.get(group.upper(), [])
    return ", ".join(teams) if teams else "?"


def decode_slot(slot: str) -> str:
    s = (slot or "").strip()
    if not s:
        return "?"
    if re.fullmatch(r"W\d+", s, re.IGNORECASE):
        num = s[1:]
        return f"ganador del partido #{num}"
    m = re.fullmatch(r"([12])([A-L])", s, re.IGNORECASE)
    if m:
        place, grp = m.group(1), m.group(2).upper()
        label = _PLACEMENT_LABELS.get(int(place), f"{place}°")
        return f"{label} Grupo {grp} ({_group_teams_label(grp)})"
    if s.lower().startswith("3rd_"):
        pools = s.split("_", 1)[-1].upper()
        return f"mejor 3° entre grupos {', '.join(pools)}"
    if re.fullmatch(r"[A-Z]{3}", s):
        return s
    return s


def _slot_for_placement(group: str, placement: int) -> str:
    return f"{placement}{group.upper()[:1]}"


def _third_slots_for_group(group: str) -> list[str]:
    g = group.upper()
    out: list[str] = []
    for row in _load_knockout_rows():
        for side in (row.home, row.away):
            if side.lower().startswith("3rd_") and g in side.upper().split("_", 1)[-1]:
                out.append(side)
    return sorted(set(out))


def _find_entry_match(slot: str) -> KnockoutRow | None:
    for row in _load_knockout_rows():
        if row.home == slot or row.away == slot:
            return row
    return None


def _trace_bracket_path(start_slot: str) -> list[tuple[KnockoutRow, str, str]]:
    """Lista (partido, slot del equipo, rival en ese cruce)."""
    steps: list[tuple[KnockoutRow, str, str]] = []
    current = start_slot
    seen: set[int] = set()
    while True:
        row = _find_entry_match(current)
        if row is None or row.match_number in seen:
            break
        seen.add(row.match_number)
        rival = row.away if row.home == current else row.home
        steps.append((row, current, rival))
        current = f"W{row.match_number}"
    return steps


def infer_group_for_team(team_code: str) -> str | None:
    code = (team_code or "").upper()
    for letter, teams in GROUP_TEAMS.items():
        if code in teams:
            return letter
    return None


def extract_group_letter_from_query(text: str) -> str | None:
    m = re.search(r"\bgrupo\s+([a-l])\b", text or "", re.IGNORECASE)
    return m.group(1).upper() if m else None


class BracketService:
    def format_bracket_scenarios(
        self,
        team: str,
        *,
        group_letter: str | None = None,
        for_agent: bool = False,
    ) -> str:
        code = normalize_team_code(team) or (team or "").upper()[:3]
        group = (group_letter or infer_group_for_team(code) or "?").upper()[:1]
        if group == "?" or group not in GROUP_TEAMS:
            return (
                f"No pude ubicar el grupo de {code}. "
                "Indicá el grupo (A–L) o preguntá por un seleccionado del fixture oficial."
            )

        teams = GROUP_TEAMS.get(group, [])
        lines = [
            f"📊 Cruces posibles — {code} (Grupo {group})",
            "Fuente: cuadro eliminatorio FIFA FWC26 (slots 1A/2J/W86).",
            "Nota: en Argentina «16avos» = dieciseisavos (32 equipos); «octavos» = round of 16.",
            f"Grupo {group}: {', '.join(teams)}.",
            "",
            "## Eliminatorias según cómo clasifique",
        ]

        for placement in (1, 2):
            slot = _slot_for_placement(group, placement)
            steps = _trace_bracket_path(slot)
            if not steps:
                continue
            lines.append(f"\n### Si queda {_PLACEMENT_LABELS[placement]} {group} (slot {slot})")
            for row, _slot, rival in steps:
                lines.append(
                    f"- **{row.phase_label}** · partido **#{row.match_number}** "
                    f"({row.date} {row.time_et} ET, {row.venue}): "
                    f"vs **{decode_slot(rival)}**"
                )
            last = steps[-1][0]
            lines.append(
                f"  → Si gana, avanza como **W{last.match_number}** hacia la siguiente ronda del cuadro."
            )

        thirds = _third_slots_for_group(group)
        if thirds:
            lines.append(f"\n### Si queda entre los mejores 3° (grupo {group})")
            lines.append(
                "Podría entrar como mejor tercero solo en estos cruces del cuadro (según ranking de 3°):"
            )
            for slot in thirds:
                row = _find_entry_match(slot)
                if not row:
                    continue
                other = row.away if row.home == slot else row.home
                lines.append(
                    f"- Slot **{slot}** en #{row.match_number} ({row.phase_label}): "
                    f"**{decode_slot(row.home)}** vs **{decode_slot(row.away)}**"
                )

        if for_agent:
            lines.append(
                "\n[Instrucción: explicá los escenarios en prosa clara; "
                "no inventes rivales fuera de estos slots.]"
            )
        return "\n".join(lines)
