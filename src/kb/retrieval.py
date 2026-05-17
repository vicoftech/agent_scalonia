"""Compat: búsqueda KB vía Lambda (agente) o directa (tests/Lambda)."""
from src.kb.lambda_client import search_kb as search_kb_via_lambda
from src.kb.pg import search_chunks

__all__ = ["search_kb", "search_chunks", "search_kb_via_lambda"]


def search_kb(query: str, limit: int = 5) -> list[dict]:
    return search_kb_via_lambda(query, limit=limit)
