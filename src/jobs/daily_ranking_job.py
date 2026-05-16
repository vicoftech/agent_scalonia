"""
src/jobs/daily_ranking_job.py
EventBridge cron(0 3 * * ? *) UTC | Período: 2026-06-11 → 2026-07-20
SPEC: SPEC-2026-014 | TASK: TASK-021 | Modo: Humano
"""
import logging
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

MUNDIAL_START = date(2026, 6, 11)
MUNDIAL_END   = date(2026, 7, 20)


def handler(event: dict, context) -> dict:
    """
    Flujo completo (9 pasos — todos idempotentes):
    1. is_mundial_active() → SKIPPED si no
    2. is_already_processed(job_run_id) → SKIPPED si sí
    3. catch-up partidos FINISHED + result_processed=false
    4. recalculate_global_ranking() → DynamoDB RANKING#GLOBAL
    5. recalculate_group_ranking() por cada grupo activo
    6. save_ranking_snapshot() → DynamoDB RANKING_SNAP# + Aurora ranking_history
    7. reset_daily_trivia_counters() → trivia_rounds_today=0 en todos los usuarios
    8. send_daily_digest() → SQS NotificationQueue (fire-and-forget)
    9. mark_job_processed(job_run_id) → DynamoDB JOB_CTRL#DAILY_RANKING/<fecha>
    """
    raise NotImplementedError("TASK-021 — Sprint 3")
