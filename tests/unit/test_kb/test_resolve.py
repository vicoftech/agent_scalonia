"""tests/unit/test_kb/test_resolve.py — ISSUE-2026-024."""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("DYNAMODB_TABLE", "ProdeTable-test")

from src.kb.query_intent import (
    is_analytical_query,
    is_historical_football_query,
    suggested_web_search_type,
)
from src.kb.resolve import (
    format_kb_web_miss_message,
    kb_is_sufficient,
    max_kb_score,
    resolve_kb_then_web,
)


class TestQueryIntent:
    def test_comparativa_es_analitica(self):
        assert is_analytical_query("Compará a Messi y Haaland en goles por partido")
        assert suggested_web_search_type("Compará Messi y Haaland") == "stats"

    def test_historia_no_es_analitica(self):
        assert not is_analytical_query("reglas del fuera de juego en el mundial")

    def test_final_historica_es_historical_football(self):
        q = "Cual fue la mejor final de la historia y cual fue la peor"
        assert is_historical_football_query(q)
        assert is_analytical_query(q)


class TestKbSufficient:
    def test_analytical_requiere_score_alto(self):
        text = "x" * 250
        assert not kb_is_sufficient("Compará Messi y Cristiano", text, 0.78)
        assert kb_is_sufficient("Compará Messi y Cristiano", text, 0.90)

    def test_general_umbral_075(self):
        text = "x" * 250
        assert kb_is_sufficient("historia mundial 1978", text, 0.80)
        assert not kb_is_sufficient("historia mundial 1978", text, 0.50)


class TestResolveKbThenWeb:
    def test_sc03_kb_suficiente_sin_web(self, monkeypatch):
        rows = [
            {
                "source_path": "reglas/offside.md",
                "content": "Fuera de juego: " + "detalle " * 40,
                "score": 0.92,
            }
        ]

        with patch("src.kb.lambda_client.search_kb", return_value=rows):
            with patch("src.kb.resolve.perform_web_search") as mock_web:
                out = resolve_kb_then_web("reglas del fuera de juego")
        assert out.kb_text
        assert out.web_text is None
        assert not out.web_fallback_used
        mock_web.assert_not_called()

    def test_sc04_cero_chunks_intenta_web(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")

        with patch("src.kb.lambda_client.search_kb", return_value=[]):
            with patch(
                "src.kb.resolve.perform_web_search",
                return_value="Titulo\nContenido web largo " * 10,
            ):
                out = resolve_kb_then_web("Compará Messi y Haaland en selecciones")
        assert out.web_fallback_used
        assert out.web_text

    def test_final_historica_kb_alta_no_fuerza_web(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        rows = [
            {
                "source_path": "mundiales/finales.md",
                "content": "La final de 1970 " * 40,
                "score": 0.91,
            }
        ]
        q = "Cual fue la mejor final de la historia y cual fue la peor"

        with patch("src.kb.lambda_client.search_kb", return_value=rows):
            with patch("src.kb.resolve.perform_web_search") as mock_web:
                out = resolve_kb_then_web(q)
        assert out.kb_text
        assert out.web_text is None
        assert not out.web_fallback_used
        mock_web.assert_not_called()

    def test_chunks_baja_relevancia_intenta_web(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        rows = [
            {
                "source_path": "mundiales/2026/sedes.md",
                "content": "Sedes del mundial " * 30,
                "score": 0.55,
            }
        ]

        with patch("src.kb.lambda_client.search_kb", return_value=rows):
            with patch(
                "src.kb.resolve.perform_web_search",
                return_value="Stats Messi vs Haaland\n" + "data " * 50,
            ):
                out = resolve_kb_then_web("Compará Messi y Haaland en goles")
        assert out.web_fallback_used
        assert out.web_text

    def test_sc05_tavily_no_configurado_mensaje(self):
        msg = format_kb_web_miss_message(tavily_configured=False, had_kb_snippet=False)
        assert "Tavily" in msg
        assert "Knowledge Base" in msg


class TestMaxKbScore:
    def test_vacio(self):
        assert max_kb_score([]) == 0.0

    def test_max(self):
        assert max_kb_score([{"score": 0.3}, {"score": 0.9}]) == pytest.approx(0.9)
