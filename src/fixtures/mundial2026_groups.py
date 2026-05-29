"""Equipos por grupo — Mundial 2026 (knowledge-base/mundiales/2026/grupos.md)."""

from __future__ import annotations

# Código FIFA 3 letras por grupo
GROUP_TEAMS: dict[str, list[str]] = {
    "A": ["MEX", "CAN", "RSA", "KOR"],
    "B": ["BIH", "QAT", "SUI", "CZE"],
    "C": ["BRA", "MAR", "HAI", "SCO"],
    "D": ["USA", "PAR", "AUS", "TUR"],
    "E": ["GER", "CUW", "CIV", "ECU"],
    "F": ["NED", "JPN", "SWE", "TUN"],
    "G": ["BEL", "EGY", "IRN", "NZL"],
    "H": ["ESP", "CPV", "KSA", "URU"],
    "I": ["FRA", "SEN", "IRQ", "NOR"],
    "J": ["ARG", "ALG", "AUT", "JOR"],
    "K": ["POR", "COD", "UZB", "COL"],
    "L": ["ENG", "CRO", "GHA", "PAN"],
}

# Round-robin doble partido (4 equipos → 6 fechas)
def all_world_cup_team_codes() -> list[str]:
    """48 selecciones del Mundial 2026 (ISO3 únicos, orden alfabético)."""
    seen: set[str] = set()
    for teams in GROUP_TEAMS.values():
        for code in teams:
            seen.add(code.strip().upper())
    return sorted(seen)


ROUND_ROBIN_PAIRINGS: list[tuple[int, int]] = [
    (0, 1),
    (2, 3),
    (0, 2),
    (1, 3),
    (0, 3),
    (1, 2),
]
