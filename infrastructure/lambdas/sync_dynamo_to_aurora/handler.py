"""
infrastructure/lambdas/sync_dynamo_to_aurora/handler.py
=======================================================
Lambda disparada por DynamoDB Streams.
Sincroniza eventos de DynamoDB → Aurora PostgreSQL.

Principio: Aurora es SIEMPRE un espejo de DynamoDB.
           Esta Lambda es el único writer en Aurora.

Patrón: upsert idempotente con ON CONFLICT DO UPDATE.
        Safe de re-ejecutar si falla a mitad.

Filtros de eventos procesados:
  - USER#.../PROFILE     → tabla users
  - MATCH#.../DETAILS    → tabla matches
  - MATCH#.../RESULT     → tabla match_results
  - USER#.../PRED#...    → tabla predictions
  - GROUP#.../DETAILS    → tabla groups
  - GROUP#.../MEMBER#... → tabla group_members
  - USER#.../TRIVIA#...  → tabla trivia_sessions (solo ANSWERED)
  - RANKING_SNAP#...     → tabla ranking_history

Eventos ignorados:
  - WS#...               → efímero, no necesita espejo relacional
  - CACHE#...            → efímero, no necesita espejo relacional
  - JOB_CTRL#...         → control interno, no necesita espejo
  - RANKING#...          → ranking actual, no histórico
"""
import json
import logging
import os
from typing import Any

import boto3
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# ── Conexión Aurora (via RDS Proxy) ──────────────────────────────────────────
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        secret = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["AURORA_SYNC_SECRET_ARN"]
        )
        creds = json.loads(secret["SecretString"])
        proxy_host = os.environ["RDS_PROXY_ENDPOINT"]
        db_name = os.environ.get("DB_NAME", "prode")

        connection_url = (
            f"postgresql+asyncpg://{creds['username']}:{creds['password']}"
            f"@{proxy_host}/{db_name}"
        )
        _engine = create_async_engine(
            connection_url,
            pool_size=3,
            max_overflow=2,
            pool_pre_ping=True,
        )
    return _engine


async def _sync_event(session: AsyncSession, pk: str, sk: str, new_image: dict) -> str:
    """
    Procesa un evento individual. Retorna el tipo de evento procesado o 'SKIPPED'.
    Todas las operaciones son upsert idempotente.
    """

    # ── Perfil de usuario ─────────────────────────────────────────────────────
    if pk.startswith("USER#") and sk == "PROFILE":
        await session.execute(sa.text("""
            INSERT INTO users
                (id, alias, platform, platform_id_hash, notifications_enabled,
                 total_points, match_points, trivia_points, created_at, updated_at)
            VALUES
                (:id, :alias, :platform, :platform_id_hash, :notifications_enabled,
                 :total_points, :match_points, :trivia_points, :created_at, NOW())
            ON CONFLICT (id) DO UPDATE SET
                alias                  = EXCLUDED.alias,
                notifications_enabled  = EXCLUDED.notifications_enabled,
                total_points           = EXCLUDED.total_points,
                match_points           = EXCLUDED.match_points,
                trivia_points          = EXCLUDED.trivia_points,
                updated_at             = NOW()
        """), {
            "id":                     new_image["user_id"],
            "alias":                  new_image["alias"],
            "platform":               new_image["platform"],
            "platform_id_hash":       new_image["platform_id_hash"],
            "notifications_enabled":  new_image.get("notifications_enabled", True),
            "total_points":           int(new_image.get("total_points", 0)),
            "match_points":           int(new_image.get("match_points", 0)),
            "trivia_points":          int(new_image.get("trivia_points", 0)),
            "created_at":             new_image.get("created_at"),
        })
        return "USER_PROFILE"

    # ── Partido ───────────────────────────────────────────────────────────────
    if pk.startswith("MATCH#") and sk == "DETAILS":
        await session.execute(sa.text("""
            INSERT INTO matches
                (id, home_team, away_team, phase, group_letter, match_number,
                 kickoff_utc, venue, city, country, veda_active, status, result_processed)
            VALUES
                (:id, :home_team, :away_team, :phase, :group_letter, :match_number,
                 :kickoff_utc, :venue, :city, :country, :veda_active, :status, :result_processed)
            ON CONFLICT (id) DO UPDATE SET
                veda_active       = EXCLUDED.veda_active,
                status            = EXCLUDED.status,
                result_processed  = EXCLUDED.result_processed,
                updated_at        = NOW()
        """), {
            "id":               new_image["match_id"],
            "home_team":        new_image["home_team"],
            "away_team":        new_image["away_team"],
            "phase":            new_image["phase"],
            "group_letter":     new_image.get("group_letter"),
            "match_number":     int(new_image["match_number"]),
            "kickoff_utc":      new_image["kickoff_utc"],
            "venue":            new_image.get("venue"),
            "city":             new_image.get("city"),
            "country":          new_image.get("country"),
            "veda_active":      bool(new_image.get("veda_active", False)),
            "status":           new_image.get("status", "SCHEDULED"),
            "result_processed": bool(new_image.get("result_processed", False)),
        })
        return "MATCH_DETAILS"

    # ── Resultado de partido ──────────────────────────────────────────────────
    if pk.startswith("MATCH#") and sk == "RESULT":
        await session.execute(sa.text("""
            INSERT INTO match_results
                (match_id, result_90min_home, result_90min_away,
                 result_final_home, result_final_away,
                 went_to_et, went_to_penalties, source, processed_at)
            VALUES
                (:match_id, :r90h, :r90a, :rfh, :rfa, :et, :pk, :source, NOW())
            ON CONFLICT (match_id) DO UPDATE SET
                result_90min_home  = EXCLUDED.result_90min_home,
                result_90min_away  = EXCLUDED.result_90min_away,
                result_final_home  = EXCLUDED.result_final_home,
                result_final_away  = EXCLUDED.result_final_away,
                went_to_et         = EXCLUDED.went_to_et,
                went_to_penalties  = EXCLUDED.went_to_penalties,
                source             = EXCLUDED.source
        """), {
            "match_id": new_image["match_id"],
            "r90h":     int(new_image["result_90min_home"]),
            "r90a":     int(new_image["result_90min_away"]),
            "rfh":      int(new_image["result_final_home"]),
            "rfa":      int(new_image["result_final_away"]),
            "et":       bool(new_image.get("went_to_et", False)),
            "pk":       bool(new_image.get("went_to_penalties", False)),
            "source":   new_image.get("source", "AUTO_WEBSEARCH"),
        })
        return "MATCH_RESULT"

    # ── Predicción ────────────────────────────────────────────────────────────
    if pk.startswith("USER#") and sk.startswith("PRED#"):
        await session.execute(sa.text("""
            INSERT INTO predictions
                (id, user_id, match_id, home_goals, away_goals,
                 status, points_earned, scoring_reason, created_at)
            VALUES
                (:id, :user_id, :match_id, :home_goals, :away_goals,
                 :status, :points_earned, :scoring_reason, :created_at)
            ON CONFLICT (user_id, match_id) DO UPDATE SET
                home_goals      = EXCLUDED.home_goals,
                away_goals      = EXCLUDED.away_goals,
                status          = EXCLUDED.status,
                points_earned   = EXCLUDED.points_earned,
                scoring_reason  = EXCLUDED.scoring_reason,
                updated_at      = NOW()
        """), {
            "id":             new_image.get("id", new_image.get("user_id") + "-" + new_image.get("match_id")),
            "user_id":        new_image["user_id"],
            "match_id":       new_image["match_id"],
            "home_goals":     int(new_image["home_goals"]),
            "away_goals":     int(new_image["away_goals"]),
            "status":         new_image.get("status", "ACTIVE"),
            "points_earned":  int(new_image["points_earned"]) if new_image.get("points_earned") is not None else None,
            "scoring_reason": new_image.get("scoring_reason"),
            "created_at":     new_image.get("created_at"),
        })
        return "PREDICTION"

    # ── Grupo ─────────────────────────────────────────────────────────────────
    if pk.startswith("GROUP#") and sk == "DETAILS":
        await session.execute(sa.text("""
            INSERT INTO groups
                (id, name, invite_code, owner_id, max_members, active, created_at)
            VALUES
                (:id, :name, :invite_code, :owner_id, :max_members, :active, :created_at)
            ON CONFLICT (id) DO UPDATE SET
                name        = EXCLUDED.name,
                active      = EXCLUDED.active,
                updated_at  = NOW()
        """), {
            "id":           new_image["group_id"],
            "name":         new_image["name"],
            "invite_code":  new_image["invite_code"],
            "owner_id":     new_image["owner_id"],
            "max_members":  int(new_image.get("max_members", 50)),
            "active":       bool(new_image.get("active", True)),
            "created_at":   new_image.get("created_at"),
        })
        return "GROUP_DETAILS"

    # ── Membresía de grupo ────────────────────────────────────────────────────
    if pk.startswith("GROUP#") and sk.startswith("MEMBER#"):
        await session.execute(sa.text("""
            INSERT INTO group_members (group_id, user_id, joined_at)
            VALUES (:group_id, :user_id, :joined_at)
            ON CONFLICT (group_id, user_id) DO NOTHING
        """), {
            "group_id": new_image["group_id"],
            "user_id":  new_image["user_id"],
            "joined_at": new_image.get("joined_at"),
        })
        return "GROUP_MEMBER"

    # ── Trivia (solo sesiones respondidas para historial) ─────────────────────
    if pk.startswith("USER#") and sk.startswith("TRIVIA#"):
        state = new_image.get("state", "PENDING")
        if state not in ("ANSWERED", "EXPIRED"):
            return "SKIPPED_TRIVIA_PENDING"

        await session.execute(sa.text("""
            INSERT INTO trivia_sessions
                (id, user_id, match_id, question, options, correct_answer,
                 difficulty, user_answer, is_correct, points_earned, state,
                 created_at, answered_at)
            VALUES
                (:id, :user_id, :match_id, :question, :options, :correct_answer,
                 :difficulty, :user_answer, :is_correct, :points_earned, :state,
                 :created_at, :answered_at)
            ON CONFLICT (id) DO UPDATE SET
                user_answer  = EXCLUDED.user_answer,
                is_correct   = EXCLUDED.is_correct,
                points_earned = EXCLUDED.points_earned,
                state        = EXCLUDED.state,
                answered_at  = EXCLUDED.answered_at
        """), {
            "id":             new_image["session_id"],
            "user_id":        new_image["user_id"],
            "match_id":       new_image.get("match_id"),
            "question":       new_image["question"],
            "options":        new_image.get("options", []),
            "correct_answer": new_image["correct_answer"],
            "difficulty":     new_image["difficulty"],
            "user_answer":    new_image.get("user_answer"),
            "is_correct":     new_image.get("is_correct"),
            "points_earned":  int(new_image["points_earned"]) if new_image.get("points_earned") is not None else None,
            "state":          state,
            "created_at":     new_image.get("created_at"),
            "answered_at":    new_image.get("answered_at"),
        })
        return "TRIVIA_SESSION"

    # ── Snapshot de ranking ───────────────────────────────────────────────────
    if pk.startswith("RANKING_SNAP#"):
        snapshot_date = pk.replace("RANKING_SNAP#", "")
        user_id = sk.replace("USER#", "")
        group_id = new_image.get("group_id")  # None = ranking global

        await session.execute(sa.text("""
            INSERT INTO ranking_history
                (snapshot_date, user_id, group_id, position,
                 total_points, match_points, trivia_points,
                 delta_position, delta_points)
            VALUES
                (:snapshot_date, :user_id, :group_id, :position,
                 :total_points, :match_points, :trivia_points,
                 :delta_position, :delta_points)
            ON CONFLICT (snapshot_date, user_id, group_id) DO UPDATE SET
                position       = EXCLUDED.position,
                total_points   = EXCLUDED.total_points,
                match_points   = EXCLUDED.match_points,
                trivia_points  = EXCLUDED.trivia_points,
                delta_position = EXCLUDED.delta_position,
                delta_points   = EXCLUDED.delta_points
        """), {
            "snapshot_date":  snapshot_date,
            "user_id":        user_id,
            "group_id":       group_id,
            "position":       int(new_image["position"]),
            "total_points":   int(new_image.get("total_points", 0)),
            "match_points":   int(new_image.get("match_points", 0)),
            "trivia_points":  int(new_image.get("trivia_points", 0)),
            "delta_position": int(new_image.get("delta_position", 0)),
            "delta_points":   int(new_image.get("delta_points", 0)),
        })
        return "RANKING_SNAPSHOT"

    return "SKIPPED_UNKNOWN_PATTERN"


def _deserialize_dynamo_item(dynamo_item: dict) -> dict:
    """
    Convierte el formato DynamoDB typed {'S': 'value'} al dict Python nativo.
    Maneja S (String), N (Number), BOOL, NULL, L (List), M (Map).
    """
    result = {}
    for key, typed_value in dynamo_item.items():
        if "S" in typed_value:
            result[key] = typed_value["S"]
        elif "N" in typed_value:
            val = typed_value["N"]
            result[key] = int(val) if "." not in val else float(val)
        elif "BOOL" in typed_value:
            result[key] = typed_value["BOOL"]
        elif "NULL" in typed_value:
            result[key] = None
        elif "L" in typed_value:
            result[key] = [
                list(v.values())[0] for v in typed_value["L"]
            ]
        elif "M" in typed_value:
            result[key] = _deserialize_dynamo_item(typed_value["M"])
    return result


async def _process_batch(records: list[dict]) -> dict:
    """Procesa un batch de Records de DynamoDB Streams."""
    stats = {"processed": 0, "skipped": 0, "errors": 0}
    engine = _get_engine()
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            for record in records:
                event_name = record.get("eventName", "")
                if event_name not in ("INSERT", "MODIFY"):
                    stats["skipped"] += 1
                    continue

                new_image_raw = record.get("dynamodb", {}).get("NewImage", {})
                if not new_image_raw:
                    stats["skipped"] += 1
                    continue

                new_image = _deserialize_dynamo_item(new_image_raw)
                pk = new_image.get("partition_key", "")
                sk = new_image.get("sort_key", "")

                try:
                    result = await _sync_event(session, pk, sk, new_image)
                    if result.startswith("SKIPPED"):
                        stats["skipped"] += 1
                    else:
                        stats["processed"] += 1
                        logger.debug("Sync OK: %s | pk_prefix=%s", result, pk[:20])
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        "Sync ERROR: pk=%s sk=%s error=%s",
                        pk[:30], sk[:30], type(e).__name__
                    )
                    raise  # re-raise para que la transacción haga rollback

    return stats


def handler(event: dict, context) -> dict:
    """
    Lambda handler para DynamoDB Streams.
    Procesa un batch de Records y sincroniza a Aurora.
    """
    import asyncio

    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "processed": 0}

    logger.info("Procesando batch DynamoDB → Aurora: %d records", len(records))

    stats = asyncio.get_event_loop().run_until_complete(_process_batch(records))

    logger.info(
        "Sync completado: processed=%d skipped=%d errors=%d",
        stats["processed"], stats["skipped"], stats["errors"]
    )

    return {"statusCode": 200, **stats}
