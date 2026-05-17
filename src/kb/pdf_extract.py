"""Extracción de texto de PDF con pdfplumber (sin Textract ni binarios externos)."""
from __future__ import annotations

import io
import logging
import re
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)

_CALENDAR_MARKERS = ("CALENDARIO\nDE PARTIDOS", "CALENDARIO DE PARTIDOS", "CALENDARIO")
_FWC26_SCHEDULE_HINTS = ("FWC26", "MATCH SCHEDULE", "CALENDARIO DE PARTIDOS")
_KNOCKOUT_PLACEHOLDERS = frozenset({"ANR", "DANR"})


def _clean_pdf_text(text: str) -> str:
    """Recorta ruido de layout y conserva bloques legibles (grupos, calendario)."""
    for marker in _CALENDAR_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            return text[idx:].strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    kept: list[str] = []
    for ln in lines:
        words = ln.split()
        if len(words) <= 4 and sum(1 for w in words if len(w) <= 2) >= max(1, len(words) - 1):
            continue
        kept.append(ln)
    return "\n".join(kept).strip()


def _parse_match_cell(cell: Any) -> str | None:
    if cell is None:
        return None
    s = str(cell).strip()
    if not s or s in _KNOCKOUT_PLACEHOLDERS:
        return None
    m = re.match(r"(\d+)\s+(\d{1,2}:\d{2})\s*\n(.+)", s, re.DOTALL)
    if not m:
        return None
    num, time, rest = m.group(1), m.group(2), m.group(3)
    parts = [x.strip() for x in rest.split("\n") if x.strip() and x.strip() != "v"]
    if len(parts) >= 2 and len(parts[-1]) == 1 and parts[-1].isalpha():
        parts = parts[:-1]
    teams = " vs ".join(parts) if parts else rest.replace("\n", " ")
    return f"Partido {num} — {time} ET — {teams}"


def _city_from_row_header(header: str) -> str | None:
    if not header or "oinuj" in header.lower() or "GRUPO" in header:
        return None
    city = header.split("\n")[0].strip()
    if not city or len(city) > 50:
        return None
    return city


def _extract_fwc26_fixture_table(data: bytes) -> str | None:
    """
    El PDF oficial FWC26 es un póster con tabla por sede.
    pdfplumber.extract_text() pierde sedes (están antes del marcador CALENDARIO).
  """
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages:
            return None
        tables = pdf.pages[0].extract_tables()
        if len(tables) < 2:
            return None
        schedule = tables[1]
        sections: list[str] = []
        for row in schedule:
            if not row or not row[0]:
                continue
            city = _city_from_row_header(str(row[0]))
            if not city:
                continue
            matches = [_parse_match_cell(c) for c in row[1:]]
            matches = [m for m in matches if m]
            if not matches:
                continue
            block = [f"## {city}", f"Total: {len(matches)} partidos (horarios ET).", ""]
            block.extend(f"- {m}" for m in matches)
            sections.append("\n".join(block))
        if not sections:
            return None
        header = (
            "# Mundial FIFA 2026 — Calendario por sede\n"
            "Fuente: FWC26 Match Schedule (FIFA, abril 2026). "
            "Horarios en zona horaria del este de EE.UU. (ET).\n"
        )
        return header + "\n\n".join(sections)


def _extract_with_pdfplumber(data: bytes) -> tuple[str, int]:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        num_pages = len(pdf.pages)
        for page in pdf.pages:
            parts.append((page.extract_text() or "").strip())
    text = "\n\n".join(p for p in parts if p)
    return _clean_pdf_text(text), num_pages


def extract_pdf_bytes(data: bytes, *, source_hint: str = "") -> str:
    """Texto del PDF en memoria. Intenta tabla FWC26 antes del texto plano."""
    hint = source_hint.upper()
    if any(h in hint for h in _FWC26_SCHEDULE_HINTS) or "MATCH SCHEDULE" in hint:
        fixture = _extract_fwc26_fixture_table(data)
        if fixture:
            logger.info("fwc26 fixture table chars=%s", len(fixture))
            return fixture
    fixture = _extract_fwc26_fixture_table(data)
    if fixture and len(fixture) > 500:
        logger.info("fwc26 fixture table (auto) chars=%s", len(fixture))
        return fixture
    text, num_pages = _extract_with_pdfplumber(data)
    logger.info("pdfplumber pages=%s chars=%s", num_pages, len(text))
    if not text.strip():
        raise ValueError("PDF sin texto extraíble (¿escaneado sin OCR?)")
    return text


def extract_pdf_text(*, s3: Any, bucket: str, key: str) -> str:
    """Texto del PDF desde S3. PDFs escaneados sin capa de texto quedarán vacíos."""
    logger.info("pdfplumber s3://%s/%s", bucket, key)
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()
    text = extract_pdf_bytes(data, source_hint=key)
    if not text.strip():
        raise ValueError(
            f"PDF sin texto extraíble (¿escaneado sin OCR?): s3://{bucket}/{key}"
        )
    return text
