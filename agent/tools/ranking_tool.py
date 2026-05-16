"""agent/tools/ranking_tool.py — TASK-012 | Sprint 2 | IA-Assisted
Lectura desde Aurora: v_group_ranking, v_user_score_summary"""
from strands import tool
@tool
def ranking_tool(action: str, user_id: str, group_id: str = None, top_n: int = 10) -> dict:
    """Rankings. Actions: global|group|user_position|history. Lee de Aurora via RDS Proxy."""
    raise NotImplementedError("TASK-012 — Sprint 2")
