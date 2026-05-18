"""tests/unit/test_kb — SPEC-2026-017 SC-01 a SC-06."""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DYNAMODB_TABLE", "ProdeTable-test")

from src.kb.cache import TTL_LIVE_MATCH, TTL_RECENT_RESULT, make_cache_key, ttl_for_search_type
from src.kb.domain import is_football_domain_query


class TestDomainValidation:
    def test_rechaza_consulta_fuera_de_dominio(self):
        assert not is_football_domain_query("¿Cómo hago un loop en Python?")

    def test_acepta_consulta_futbol(self):
        assert is_football_domain_query("¿Cuántos goles hizo Maradona en el Mundial 86?")


class TestCacheTtl:
    def test_sc03_live_match_ttl(self):
        assert ttl_for_search_type("live_match") == TTL_LIVE_MATCH
        assert TTL_LIVE_MATCH == 600

    def test_sc03_result_ttl(self):
        assert ttl_for_search_type("result") == TTL_RECENT_RESULT
        assert TTL_RECENT_RESULT == 86400

    def test_sc06_fixture_ttl(self):
        assert ttl_for_search_type("fixture") == 60 * 60 * 6


class TestWebSearchTool:
    def test_sc01_cache_hit(self, monkeypatch):
        from agent.tools import web_search_tool as wst

        monkeypatch.setenv("DYNAMODB_TABLE", "ProdeTable-test")
        with patch.object(wst, "get_from_cache", return_value="resultado cacheado"):
            with patch.object(wst, "_resolve_search") as mock_search:
                out = wst.web_search_tool("Argentina 2026 goles", search_type="stats")
        assert out == "resultado cacheado"
        mock_search.assert_not_called()

    def test_sc02_cache_miss_persiste(self, monkeypatch):
        from agent.tools import web_search_tool as wst

        monkeypatch.setenv("DYNAMODB_TABLE", "ProdeTable-test")
        wst._search_fn = lambda q: "resultado web"
        try:
            with patch.object(wst, "get_from_cache", return_value=None):
                with patch.object(wst, "save_to_cache") as mock_save:
                    out = wst.web_search_tool(
                        "resultado ARG vs BRA 2026", search_type="result"
                    )
            assert "resultado web" in out
            mock_save.assert_called_once()
            args = mock_save.call_args[0]
            assert args[3] == TTL_RECENT_RESULT
        finally:
            wst._search_fn = None

    def test_fuera_de_dominio_no_busca(self):
        from agent.tools.web_search_tool import web_search_tool

        with patch("agent.tools.web_search_tool._resolve_search") as mock_search:
            out = web_search_tool("bitcoin price today")
        assert "fútbol" in out.lower()
        mock_search.assert_not_called()


class TestKbRetrievalTool:
    def test_sin_datos_mensaje_claro(self):
        import importlib

        krt = importlib.import_module("agent.tools.kb_retrieval_tool")

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
            out = krt.kb_retrieval_tool("goles Maradona en el Mundial 1986")
        assert "Tavily" in out or "suficiente" in out.lower()

    def test_sc04_pgvector_formatea_chunks(self):
        import importlib

        krt = importlib.import_module("agent.tools.kb_retrieval_tool")

        long_content = "Maradona anotó 5 goles en 1986. " * 15
        rows = [
            {
                "source_path": "knowledge-base/mundiales/ediciones/1986.md",
                "content": long_content,
                "score": 0.92,
            }
        ]
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
            out = krt.kb_retrieval_tool("goles Maradona Mundial 1986")
        assert "5 goles" in out
        assert "1986" in out

    def test_comparativa_dispara_web_en_tool(self, monkeypatch):
        import importlib

        krt = importlib.import_module("agent.tools.kb_retrieval_tool")

        monkeypatch.setenv("TAVILY_API_KEY", "test")
        web = "Messi vs Haaland stats\n" + "x " * 50
        with patch("src.kb.resolve.resolve_kb_then_web") as mock_resolve:
            from src.kb.resolve import KbWebResolveResult

            mock_resolve.return_value = KbWebResolveResult(
                kb_text="",
                web_text=web,
                kb_chunk_count=0,
                kb_max_score=0.4,
                web_fallback_used=True,
                tavily_configured=True,
            )
            out = krt.kb_retrieval_tool("Compará Messi y Haaland en goles")
        assert "Haaland" in out
        assert "Knowledge Base ni en la web" not in out


class TestCacheKey:
    def test_cache_key_formato(self):
        key = make_cache_key("Argentina fixture 2026")
        assert key.startswith("CACHE#")
        assert len(key) == 6 + 32
