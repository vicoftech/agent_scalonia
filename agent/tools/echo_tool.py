"""agent/tools/echo_tool.py — smoke test MVP"""
from __future__ import annotations

import datetime
import json

from strands import tool


@tool
def echo_tool(message: str) -> str:
    """Repite el mensaje con timestamp. Smoke test del pipeline agente → Telegram."""
    payload = {
        "echo": message,
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "status": "MVP operativo — Prode Mundial 2026 ⚽",
        "features_enabled": [
            "echo",
            "match_fixture",
            "knowledge_base",
            "web_search",
            "invitations",
        ],
        "features_pending": ["predicciones", "veda", "rankings", "grupos"],
    }
    return json.dumps(payload, ensure_ascii=False)
