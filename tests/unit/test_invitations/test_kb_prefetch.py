from unittest.mock import patch

from infrastructure.lambdas.telegram_webhook.kb_prefetch import (
    enrich_prompt_with_kb,
    try_direct_knowledge_reply,
)


def test_enrich_skips_without_lambda_env(monkeypatch):
    monkeypatch.delenv("KB_QUERY_LAMBDA_NAME", raising=False)
    prompt, n = enrich_prompt_with_kb("grupos mundial 2026")
    assert "grupos mundial 2026" in prompt
    assert n == 0


def test_enrich_analytical_sin_lambda_instruye_web(monkeypatch):
    monkeypatch.delenv("KB_QUERY_LAMBDA_NAME", raising=False)
    prompt, n = enrich_prompt_with_kb("Compará a Messi y Haaland en goles por partido")
    assert n == 0
    assert "web_search_tool" in prompt


def test_enrich_appends_chunks(monkeypatch):
    monkeypatch.setenv("KB_QUERY_LAMBDA_NAME", "prode-mundial-kb-query-dev")

    long_content = "Historia del mundial 1978: " + "detalle " * 50
    rows = [{"source_path": "mundiales/1978.md", "content": long_content, "score": 0.92}]

    with patch("src.kb.resolve.resolve_kb_then_web") as mock_resolve:
        from src.kb.resolve import KbWebResolveResult

        mock_resolve.return_value = KbWebResolveResult(
            kb_text=long_content,
            web_text=None,
            kb_chunk_count=1,
            kb_max_score=0.92,
            web_fallback_used=False,
            tavily_configured=True,
        )
        prompt, n = enrich_prompt_with_kb("historia del mundial 1978")
    assert n == 1
    assert "Knowledge Base" in prompt
    assert "1978" in prompt
    assert "web_search_tool" in prompt


def test_enrich_web_fallback(monkeypatch):
    monkeypatch.setenv("KB_QUERY_LAMBDA_NAME", "prode-mundial-kb-query-dev")
    web = "Estadísticas comparativas\n" + "dato " * 40

    with patch("src.kb.resolve.resolve_kb_then_web") as mock_resolve:
        from src.kb.resolve import KbWebResolveResult

        mock_resolve.return_value = KbWebResolveResult(
            kb_text="",
            web_text=web,
            kb_chunk_count=0,
            kb_max_score=0.0,
            web_fallback_used=True,
            tavily_configured=True,
        )
        prompt, n = enrich_prompt_with_kb("Compará Messi y Cristiano en mundiales")
    assert n == 0
    assert "Contexto web" in prompt
    assert "Estadísticas" in prompt


def test_direct_knowledge_reply_pele(monkeypatch):
    monkeypatch.setenv("KB_QUERY_LAMBDA_NAME", "prode-mundial-kb-query-dev")
    kb = (
        "Pelé en Chile 1962: lesión vs Checoslovaquia. "
        "Brasil campeón sin él en cancha.\n" + "detalle " * 80
    )

    with patch("src.kb.resolve.resolve_kb_then_web") as mock_resolve:
        from src.kb.resolve import KbWebResolveResult

        mock_resolve.return_value = KbWebResolveResult(
            kb_text=kb,
            web_text=None,
            kb_chunk_count=3,
            kb_max_score=0.88,
            web_fallback_used=False,
            tavily_configured=True,
        )
        reply = try_direct_knowledge_reply("Que paso con Pele en el mundial de 1962?")
    assert reply
    assert "1962" in reply
    assert "Knowledge Base" in reply


def test_direct_knowledge_skips_analytical(monkeypatch):
    monkeypatch.setenv("KB_QUERY_LAMBDA_NAME", "prode-mundial-kb-query-dev")
    assert try_direct_knowledge_reply("Compará Messi y Haaland en goles") is None


def test_enrich_miss_instruye_web(monkeypatch):
    monkeypatch.setenv("KB_QUERY_LAMBDA_NAME", "prode-mundial-kb-query-dev")

    with patch("src.kb.resolve.resolve_kb_then_web") as mock_resolve:
        from src.kb.resolve import KbWebResolveResult

        mock_resolve.return_value = KbWebResolveResult(
            kb_text="",
            web_text=None,
            kb_chunk_count=0,
            kb_max_score=0.0,
            web_fallback_used=False,
            tavily_configured=False,
        )
        prompt, n = enrich_prompt_with_kb("tendencia de Brasil en amistosos")
    assert n == 0
    assert "web_search_tool" in prompt
