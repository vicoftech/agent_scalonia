"""Extracción de texto de PDF con pdfplumber (sin Textract ni binarios externos)."""
from __future__ import annotations

import io
import logging
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)

# PDFs tipo fixture FIFA: mucho ruido de cuadro; el bloque útil suele empezar acá.
_CALENDAR_MARKERS = ("CALENDARIO\nDE PARTIDOS", "CALENDARIO DE PARTIDOS", "CALENDARIO")


def _clean_pdf_text(text: str) -> str:
    """Recorta ruido de layout y conserva bloques legibles (grupos, calendario)."""
    for marker in _CALENDAR_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            return text[idx:].strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    kept: list[str] = []
    for ln in lines:
        # Descarta líneas tipo "nreiV oiluj ed 01" (texto invertido por columnas)
        words = ln.split()
        if len(words) <= 4 and sum(1 for w in words if len(w) <= 2) >= max(1, len(words) - 1):
            continue
        kept.append(ln)
    return "\n".join(kept).strip()


def _extract_with_pdfplumber(data: bytes) -> tuple[str, int]:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        num_pages = len(pdf.pages)
        for page in pdf.pages:
            parts.append((page.extract_text() or "").strip())
    text = "\n\n".join(p for p in parts if p)
    return _clean_pdf_text(text), num_pages


def extract_pdf_text(*, s3: Any, bucket: str, key: str) -> str:
    """Texto del PDF desde S3. PDFs escaneados sin capa de texto quedarán vacíos."""
    logger.info("pdfplumber s3://%s/%s", bucket, key)
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()
    text, num_pages = _extract_with_pdfplumber(data)
    logger.info("pdfplumber pages=%s chars=%s", num_pages, len(text))
    if not text.strip():
        raise ValueError(
            f"PDF sin texto extraíble (¿escaneado sin OCR?): s3://{bucket}/{key}"
        )
    return text
