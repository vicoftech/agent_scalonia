"""tests/unit/test_kb/test_chunking.py"""
from src.kb.chunking import chunk_text


def test_chunk_by_section_for_fixture():
    text = "# Mundial 2026\nIntro.\n\n## KANSAS CITY\n- Partido 1\n\n## DALLAS\n- Partido 2"
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert "KANSAS CITY" in chunks[0] or "KANSAS CITY" in chunks[1]
    kc = next(c for c in chunks if "KANSAS" in c)
    assert "Partido 1" in kc
    assert "DALLAS" not in kc
