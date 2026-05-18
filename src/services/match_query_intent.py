"""Detecta consultas de fixture/partidos — priorizar match_tool."""
from __future__ import annotations

import re

_FIXTURE_PATTERNS = [
    r"\b(partido|partidos|fixture|calendario|horario|horarios|kickoff|fecha)\b",
    r"\b(cuándo|cuando)\s+juega\b",
    r"\b(próximo|proximo|siguiente)\s+partido\b",
    r"\b(grupo\s+[a-l]|grupos?\s+del\s+mundial)\b",
    r"\b(vs\.?|contra|frente a)\b",
    r"\b(sede|estadio|ciudad)\b.*\b(partido|juega|mundial)\b",
    r"\b(mundial\s+2026).*\b(partido|juega|fixture|grupo)\b",
    r"\b(juega|juegan)\b.*\b(mundial|2026|argentina|brasil|mexico|méxico)\b",
    r"\b#\d{1,2}\b",  # "#12 ARG vs ..."
    r"\bmatch\s*#?\d+\b",
]

_TEAM_FIXTURE = re.compile(
    r"\b("
    r"argentina|brasil|mexico|méxico|usa|españa|francia|alemania|inglaterra|portugal|"
    r"holanda|uruguay|colombia|ecuador|chile|japon|japón|marruecos|croacia|belgica|bélgica"
    r")\b.*\b(cuándo|cuando|partido|juega|horario|fixture|próximo|proximo)\b",
    re.IGNORECASE,
)


def is_match_fixture_query(text: str) -> bool:
    """True si la pregunta es sobre fixture/partidos del Mundial 2026."""
    q = (text or "").strip().lower()
    if len(q) < 4:
        return False
    if _TEAM_FIXTURE.search(q):
        return True
    return any(re.search(p, q, re.IGNORECASE) for p in _FIXTURE_PATTERNS)
