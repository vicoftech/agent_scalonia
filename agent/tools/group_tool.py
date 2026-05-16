"""agent/tools/group_tool.py — TASK-014 | Sprint 2 | IA-Assisted"""
from strands import tool
@tool
def group_tool(action: str, user_id: str, group_name: str = None,
               invite_code: str = None, group_id: str = None) -> dict:
    """Grupos. Actions: create|join|leave|list|info. Máx 50 miembros."""
    raise NotImplementedError("TASK-014 — Sprint 2")
