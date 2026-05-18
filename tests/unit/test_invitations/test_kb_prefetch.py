from infrastructure.lambdas.telegram_webhook.kb_prefetch import enrich_prompt_with_kb


def test_enrich_skips_without_lambda_env(monkeypatch):
    monkeypatch.delenv("KB_QUERY_LAMBDA_NAME", raising=False)
    prompt, n = enrich_prompt_with_kb("grupos mundial 2026")
    assert prompt == "grupos mundial 2026"
    assert n == 0


def test_enrich_appends_chunks(monkeypatch):
    monkeypatch.setenv("KB_QUERY_LAMBDA_NAME", "prode-mundial-kb-query-dev")

    def fake_search(query: str, limit: int = 5):
        assert query == "fixture"
        return [{"source_path": "fwc26.pdf", "content": "Grupo A: ..."}]

    monkeypatch.setattr(
        "src.kb.lambda_client.search_kb",
        fake_search,
    )
    prompt, n = enrich_prompt_with_kb("fixture")
    assert n == 1
    assert "Knowledge Base" in prompt
    assert "Grupo A" in prompt
