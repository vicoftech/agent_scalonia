"""agent/tools/echo_tool.py — smoke test MVP"""
import datetime
from strands import tool

@tool
def echo_tool(message: str) -> dict:
    """Repite el mensaje con timestamp. Smoke test del pipeline agente → Telegram."""
    return {
        "echo":      message,
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "status":    "MVP operativo — Prode Mundial 2026 ⚽",
        "features_enabled": ["echo"],
        "features_pending": ["predicciones", "veda", "rankings", "grupos", "trivia", "knowledge_base"],
    }
