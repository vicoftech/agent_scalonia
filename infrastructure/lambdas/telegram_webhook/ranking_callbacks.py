"""Callbacks rnk:* — SPEC-2026-042."""
from __future__ import annotations

from ranking_commands import handle_mi_ranking_command, show_group_ranking
from src.services.prediction_service import PredictionService


def handle_ranking_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("rnk:"):
        return None
    parts = data.split(":")
    if len(parts) < 2:
        return None

    svc = PredictionService()

    if parts[1] == "back":
        return handle_mi_ranking_command(user_id)

    if parts[1] == "g" and len(parts) >= 3:
        gid = svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no válido o sin acceso.", None
        return show_group_ranking(user_id, gid)

    if parts[1] == "pg" and len(parts) >= 4:
        try:
            page = int(parts[2])
        except ValueError:
            return "Página inválida.", None
        gid = svc.resolve_group_short(user_id, parts[3])
        if not gid:
            return "Grupo no válido o sin acceso.", None
        return show_group_ranking(user_id, gid, page=max(page, 0))

    return None
