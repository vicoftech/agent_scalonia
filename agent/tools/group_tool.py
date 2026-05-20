"""agent/tools/group_tool.py — Grupos (SPEC-026). Creación conversacional delegada a Telegram."""
from __future__ import annotations

from strands import tool


@tool
def group_tool(action: str, user_id: str, group_name: str | None = None) -> str:
    """
    Grupos privados del Prode. En Telegram usá /grupos, /crear-grupo y /editar-grupo.

    Actions: list — resume grupos del usuario (redirige a /grupos en Telegram).
    """
    if action == "list":
        from src.services.group_service import GroupService

        return GroupService().format_groups_list(user_id)
    return (
        "Para crear o administrar grupos usá los comandos de Telegram:\n"
        "/grupos — ver tus grupos\n"
        "/crear-grupo — crear tu grupo\n"
        "/editar-grupo — renombrar, avatar, miembros"
    )
