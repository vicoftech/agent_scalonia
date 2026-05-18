"""Intención de consulta KB/web — ISSUE-2026-024."""
from __future__ import annotations

import re

_ANALYTICAL_PATTERNS = [
    r"\bcompar[aá]",
    r"\b(versus|vs\.?)\b",
    r"\b(estad[ií]stica|stats|promedio|ranking|asistencias)\b",
    r"\bgoles por partido\b",
    r"\b(tendencia|forma reciente|últimos partidos|rendimiento|momentum)\b",
    r"\b(mejor|peor|más goles|menos goles|quién tiene más)\b",
    r"\b(an[aá]lisis|analiz[aá]|diferencias entre)\b",
    r"\bentre\b.*\b(y|vs\.?|versus)\b",
]


def is_analytical_query(text: str) -> bool:
    """Comparativas, stats agregadas, tendencias — suelen requerir web si la KB no es muy relevante."""
    q = (text or "").strip()
    if len(q) < 8:
        return False
    return any(re.search(p, q, re.IGNORECASE) for p in _ANALYTICAL_PATTERNS)


def suggested_web_search_type(text: str) -> str:
    """search_type para web_search_tool."""
    if is_analytical_query(text):
        return "stats"
    q = (text or "").lower()
    if re.search(r"\b(hoy|ayer|en vivo|live|noticia|novedad)\b", q):
        return "news"
    if re.search(r"\b(resultado|marcador|anoche)\b", q):
        return "result"
    return "general"
