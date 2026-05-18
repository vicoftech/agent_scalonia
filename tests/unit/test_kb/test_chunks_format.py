from src.kb.chunks_format import format_kb_chunks


def test_format_kb_chunks_includes_source_and_content():
    text = format_kb_chunks(
        [{"source_path": "rules.md", "content": "5 puntos por acierto exacto."}]
    )
    assert "[rules.md]" in text
    assert "5 puntos" in text
