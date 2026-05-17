"""tests/unit/test_kb/test_pdf_extract.py"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("pdfplumber")
from src.kb.pdf_extract import _extract_with_pdfplumber, extract_pdf_bytes

_FIXTURE_PDF = (
    Path(__file__).resolve().parents[3]
    / "knowledge-base"
    / "FWC26 Match Schedule_v17_10042026_ES.pdf"
)


def test_pdfplumber_extracts_text():
    page = MagicMock()
    page.extract_text.return_value = "Hola mundo PDF"
    pdf = MagicMock()
    pdf.pages = [page]
    pdf.__enter__ = MagicMock(return_value=pdf)
    pdf.__exit__ = MagicMock(return_value=False)

    with patch("src.kb.pdf_extract.pdfplumber.open", return_value=pdf):
        text, n = _extract_with_pdfplumber(b"%PDF mock")

    assert n == 1
    assert "Hola mundo" in text


@pytest.mark.skipif(not _FIXTURE_PDF.is_file(), reason="fixture PDF not in tree")
def test_fwc26_schedule_includes_kansas_city():
    data = _FIXTURE_PDF.read_bytes()
    text = extract_pdf_bytes(data, source_hint=_FIXTURE_PDF.name)
    assert "KANSAS CITY" in text
    assert "Partido 19" in text
    assert "ARG vs ALG" in text
    assert len(text) > 2000
