"""Comandos /partidos, /predecir, /completo — SPEC-2026-021."""
from __future__ import annotations

import re

from src.services.prediction_service import PredictionService

_PARTIDOS = re.compile(r"^/partidos(?:@[\w_]+)?\s*$", re.IGNORECASE)
_COMPLETO = re.compile(r"^/completo(?:@[\w_]+)?\s*$", re.IGNORECASE)
_NEXT = re.compile(r"^/next(?:@[\w_]+)?\s*$", re.IGNORECASE)


def handle_prediction_command(user_id: str, text: str) -> tuple[str, dict | None] | None:
    text = (text or "").strip()
    svc = PredictionService()

    if _PARTIDOS.match(text) or _NEXT.match(text):
        return svc.list_partidos_view(user_id)

    if _COMPLETO.match(text):
        return svc.format_completo_menu(user_id)

    parsed = svc.parse_predecir_command(text)
    if parsed:
        home_code, hg, ag, away_code = parsed
        return svc.save_predecir_command(user_id, home_code, hg, ag, away_code)

    return None
