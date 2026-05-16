"""
src/dao/aurora/ranking_repo.py
Queries con JOIN contra Aurora PostgreSQL via RDS Proxy.
SPEC: SPEC-2026-007/008 | TASK: TASK-011 | Modo: IA-Assisted

PRINCIPIO: este módulo es SOLO LECTURA desde el punto de vista del agente.
           La Lambda sync_dynamo_to_aurora es el único writer en Aurora.
"""
import os
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text


class RankingRepo:
    """
    Repositorio de rankings. Lee de Aurora via RDS Proxy.
    Todas las operaciones son SELECT — sin INSERT, UPDATE ni DELETE.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_group_ranking(self, group_id: str) -> list[dict]:
        """
        SELECT * FROM v_group_ranking WHERE group_id = :group_id ORDER BY position
        Retorna: [{user_id, alias, total_points, match_points, trivia_points, position}]
        """
        raise NotImplementedError("TASK-011")

    async def get_global_top_n(self, top_n: int = 10) -> list[dict]:
        """
        SELECT * FROM v_user_score_summary ORDER BY global_position LIMIT :top_n
        """
        raise NotImplementedError("TASK-011")

    async def get_user_global_position(self, user_id: str) -> Optional[dict]:
        """
        SELECT * FROM v_user_score_summary WHERE user_id = :user_id
        Retorna posición, puntos y stats del usuario.
        """
        raise NotImplementedError("TASK-011")

    async def get_ranking_history(self, user_id: str, snapshot_date: str) -> Optional[dict]:
        """
        SELECT * FROM ranking_history WHERE user_id = :user_id AND snapshot_date = :date
        Para responder "¿cómo estaba el 14 de junio?"
        """
        raise NotImplementedError("TASK-011")
