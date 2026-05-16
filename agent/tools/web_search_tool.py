"""agent/tools/web_search_tool.py — TASK-020 | Sprint 3 | IA-Assisted
Cache en DynamoDB CACHE#<sha256(query)>/RESULT con TTL 24h"""
from strands import tool
@tool
def web_search_tool(query: str) -> str:
    """Busca partidos, resultados y estadísticas del Mundial 2026. Resultados cacheados 24h."""
    raise NotImplementedError("TASK-020 — Sprint 3")
