"""Extrae fechas de consultas en lenguaje natural (fixture Mundial 2026)."""
from __future__ import annotations

import re
from datetime import date

_MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# "8, 9 o 10 de julio" — captura todos los números antes de "de <mes>"
_DAYS_BEFORE_MONTH = re.compile(
    r"(?:d[ií]as?\s+)?([\d\s,oy]+?)\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
    re.IGNORECASE,
)
_SINGLE_DAY = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
    re.IGNORECASE,
)
_MONTH_ONLY = re.compile(
    r"\b(?:en\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+2026\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(2026-\d{2}-\d{2})\b")


def parse_dates_from_query(text: str, *, year: int = 2026) -> list[date] | None:
    """
    Fechas de calendario mencionadas en la pregunta (día local implícito).
    None si no hay referencia temporal clara.
    """
    q = (text or "").strip()
    if not q:
        return None

    for m in _ISO_DATE.finditer(q):
        try:
            return [date.fromisoformat(m.group(1))]
        except ValueError:
            pass

    m = _DAYS_BEFORE_MONTH.search(q)
    if m:
        month = _MONTHS[m.group(2).lower()]
        days = [int(d) for d in re.findall(r"\d{1,2}", m.group(1))]
        if days:
            return sorted({date(year, month, d) for d in days if 1 <= d <= 31})

    m = _SINGLE_DAY.search(q)
    if m:
        day, mon = int(m.group(1)), _MONTHS[m.group(2).lower()]
        if 1 <= day <= 31:
            return [date(year, mon, day)]

    m = _MONTH_ONLY.search(q)
    if m:
        month = _MONTHS[m.group(1).lower()]
        return None  # mes completo: usar from/to en search, no lista de días

    return None


def parse_month_range(text: str, *, year: int = 2026) -> tuple[str, str] | None:
    """(from_date, to_date) ISO si preguntan por un mes entero."""
    m = _MONTH_ONLY.search((text or "").strip())
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    from datetime import timedelta

    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()
