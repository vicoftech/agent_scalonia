"""Validación de dominio fútbol/mundiales para tools de búsqueda."""

import re

_FOOTBALL_PATTERN = re.compile(
    r"\b("
    r"f[uú]tbol|fifa|mundial(?:es)?|world\s*cup|gol(?:es)?|partido|equipo|selecci[oó]n|"
    r"argentina|brasil|brazil|messi|maradona|offside|fuera\s*de\s*juego|"
    r"fixture|estadio|sedes?|grupo\s*[a-l]|eliminatoria|penal|arbitro|"
    r"2026|ifab|t[aá]ctica|formaci[oó]n|champions|libertadores|"
    r"premier|liga|cop(a|as)|entrenador|portero|delantero"
    r")\b",
    re.IGNORECASE,
)

_BLOCKED_PATTERN = re.compile(
    r"\b(python\s*loop|javascript|bitcoin|elecciones|d[oó]lar|taylor\s*swift|"
    r"us\s*open|verstappen|f1\s*race|diagn[oó]stico|medicamento)\b",
    re.IGNORECASE,
)


def is_football_domain_query(query: str) -> bool:
    """True si la consulta parece relacionada con fútbol o mundiales."""
    text = (query or "").strip()
    if len(text) < 3:
        return False
    if _BLOCKED_PATTERN.search(text):
        return False
    return bool(_FOOTBALL_PATTERN.search(text))
