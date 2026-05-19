"""Jugadores sugeridos en onboarding M2 según selección favorita."""
from __future__ import annotations

PLAYERS_BY_TEAM: dict[str, list[str]] = {
    "ARG": ["Messi", "Lautaro", "Di María"],
    "BRA": ["Vinícius Jr", "Rodrygo", "Casemiro"],
    "ESP": ["Pedri", "Morata", "Gavi"],
    "FRA": ["Mbappé", "Griezmann", "Dembélé"],
    "ENG": ["Kane", "Bellingham", "Saka"],
    "GER": ["Musiala", "Wirtz", "Havertz"],
    "POR": ["Ronaldo", "B. Silva", "Leão"],
    "URU": ["Suárez", "Valverde", "Núñez"],
    "MEX": ["Lozano", "Jiménez", "Álvarez"],
}

GLOBAL_TOP_PLAYERS = ["Messi", "Mbappé", "Kane", "Vinícius Jr", "Bellingham"]


def suggest_players(favorite_team: str | None) -> list[str]:
    if favorite_team and favorite_team in PLAYERS_BY_TEAM:
        return list(PLAYERS_BY_TEAM[favorite_team])
    return list(GLOBAL_TOP_PLAYERS)
