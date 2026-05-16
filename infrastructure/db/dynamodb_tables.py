"""
infrastructure/db/dynamodb_tables.py
=====================================
Definición completa de la tabla DynamoDB ProdeTable.

Modelo: Single-Table Design con 4 GSIs.
Fuente de verdad: steering.md — Arquitectura Híbrida de Datos.

Regla de oro: DynamoDB escribe, Aurora lee.
Toda escritura de negocio pasa por aquí. Aurora es espejo.
"""
import aws_cdk as cdk
import aws_cdk.aws_dynamodb as dynamodb
from constructs import Construct


class ProdeTableConstruct(Construct):
    """
    ProdeTable — Single-Table Design.

    PK: partition_key (String)
    SK: sort_key      (String)

    Patrones de PK/SK:
    ─────────────────────────────────────────────────────────
    Entidad              PK                      SK
    ─────────────────────────────────────────────────────────
    Perfil usuario       USER#<uuid>             PROFILE
    Predicción           USER#<uuid>             PRED#<match_uuid>
    Partido              MATCH#<uuid>            DETAILS
    Resultado partido    MATCH#<uuid>            RESULT
    Grupo                GROUP#<uuid>            DETAILS
    Membresía            GROUP#<uuid>            MEMBER#<user_uuid>
    Ranking global       RANKING#GLOBAL          USER#<uuid>
    Ranking grupo        RANKING#GROUP#<g_uuid>  USER#<uuid>
    Snapshot ranking     RANKING_SNAP#<date>     USER#<uuid>
    Trivia sesión        USER#<uuid>             TRIVIA#<session_uuid>
    Trivia histórico     USER#<uuid>             TRIVIA_HIST#<date>#<uuid>
    WS conexión          WS#<connection_id>      DETAILS
    Job control          JOB_CTRL#<job_name>     <YYYY-MM-DD>
    Cache web_search     CACHE#<query_hash>      RESULT
    ─────────────────────────────────────────────────────────

    GSIs:
    ─────────────────────────────────────────────────────────
    GSI-1-platform          platform (PK) | platform_id_hash (SK)
    GSI-2-match-predictions match_id (PK) | user_id (SK)
    GSI-3-group-members     group_id (PK) | user_id (SK)
    GSI-4-ranking-score     ranking_type (PK) | score (SK, Number)
    ─────────────────────────────────────────────────────────
    """

    def __init__(self, scope: Construct, construct_id: str, env_name: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.env_name = env_name
        self.table = self._create()

    def _create(self) -> dynamodb.Table:
        table = dynamodb.Table(
            self, "ProdeTable",
            table_name=f"ProdeTable-{self.env_name}",

            # ── Clave primaria compuesta ──────────────────────────────────
            partition_key=dynamodb.Attribute(
                name="partition_key",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sort_key",
                type=dynamodb.AttributeType.STRING,
            ),

            # ── Capacidad y billing ───────────────────────────────────────
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,

            # ── Streams para sync → Aurora ────────────────────────────────
            # Lambda sync_dynamo_to_aurora consume este stream.
            # Filtra por tipo de evento en código (INSERT/MODIFY).
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,

            # ── Durabilidad ───────────────────────────────────────────────
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),

            # ── TTL ───────────────────────────────────────────────────────
            # Atributo Unix timestamp. Cada ítem con TTL lo setea según su tipo:
            #   WS conexiones:       NOW + 8h
            #   Trivia sesiones:     NOW + 30min
            #   Cache web_search:    NOW + 24h
            #   Ranking snapshots:   NOW + 90d
            time_to_live_attribute="ttl_expiry",

            # ── Retención según entorno ───────────────────────────────────
            removal_policy=(
                cdk.RemovalPolicy.RETAIN
                if self.env_name == "prod"
                else cdk.RemovalPolicy.DESTROY
            ),
        )

        # ── GSI-1: Lookup usuario por plataforma ──────────────────────────
        # Uso: webhook Telegram/Teams → buscar user_id por platform_id_hash
        # Frecuencia: ALTA (cada mensaje entrante)
        # Query: platform = "TELEGRAM" AND platform_id_hash = "<sha256>"
        table.add_global_secondary_index(
            index_name="GSI-1-platform",
            partition_key=dynamodb.Attribute(
                name="platform",           # "TELEGRAM" | "TEAMS"
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="platform_id_hash",   # SHA-256 del chat_id/userId
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["user_id", "alias", "notifications_enabled"],
        )

        # ── GSI-2: Predicciones por partido ───────────────────────────────
        # Uso: Lambda sync lee todas las predicciones de un partido para Aurora.
        #      También para notificar a todos los predictores post-resultado.
        # Frecuencia: MEDIA (al procesar cada resultado)
        # Query: match_id = "<uuid>"
        table.add_global_secondary_index(
            index_name="GSI-2-match-predictions",
            partition_key=dynamodb.Attribute(
                name="match_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── GSI-3: Miembros de un grupo ───────────────────────────────────
        # Uso: listar miembros de un grupo, verificar membresía.
        #      También para el recordatorio de veda: todos los miembros del grupo.
        # Frecuencia: MEDIA
        # Query: group_id = "<uuid>"
        table.add_global_secondary_index(
            index_name="GSI-3-group-members",
            partition_key=dynamodb.Attribute(
                name="group_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["alias", "total_points", "joined_at"],
        )

        # ── GSI-4: Ranking ordenado por puntaje ───────────────────────────
        # Uso: top-10 global sin JOIN. Para ranking simple sin alias de usuario.
        # Frecuencia: BAJA (el ranking completo con alias viene de Aurora)
        # Query: ranking_type = "GLOBAL" ORDER BY score DESC
        # Nota: DynamoDB ordena SK numérico. Score se almacena como Number.
        table.add_global_secondary_index(
            index_name="GSI-4-ranking-score",
            partition_key=dynamodb.Attribute(
                name="ranking_type",       # "GLOBAL" | "GROUP#<uuid>"
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="score",
                type=dynamodb.AttributeType.NUMBER,
            ),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["user_id", "alias", "match_points", "trivia_points"],
        )

        cdk.CfnOutput(
            self, "TableName",
            value=table.table_name,
            description="DynamoDB ProdeTable name",
        )
        cdk.CfnOutput(
            self, "TableArn",
            value=table.table_arn,
            description="DynamoDB ProdeTable ARN — usar en IAM roles de Lambda",
        )
        cdk.CfnOutput(
            self, "StreamArn",
            value=table.table_stream_arn or "stream-not-enabled",
            description="DynamoDB Stream ARN — trigger de Lambda sync_dynamo_to_aurora",
        )

        return table


# ── Documentación de ítems por entidad ────────────────────────────────────────
#
# PERFIL DE USUARIO
# ─────────────────
# PK: USER#<uuid>    SK: PROFILE
# {
#   "partition_key":       "USER#550e8400-e29b-41d4-a716-446655440000",
#   "sort_key":            "PROFILE",
#   "user_id":             "550e8400-e29b-41d4-a716-446655440000",  # UUID interno
#   "alias":               "GolazoFan",
#   "platform":            "TELEGRAM",
#   "platform_id_hash":    "a7f3d9...c8e2",   # SHA-256(chat_id), NUNCA el chat_id
#   "notifications_enabled": True,
#   "total_points":        47,                 # match_points + trivia_points
#   "match_points":        35,
#   "trivia_points":       12,
#   "trivia_rounds_today": 3,                 # reset por daily job a las 3:00 UTC
#   "trivia_last_reset":   "2026-06-15",
#   "created_at":          "2026-06-10T14:23:00Z",
#   "updated_at":          "2026-06-15T20:45:00Z",
# }
#
# PREDICCIÓN
# ──────────
# PK: USER#<uuid>    SK: PRED#<match_uuid>
# {
#   "partition_key":  "USER#550e8400-...",
#   "sort_key":       "PRED#a3f1b200-...",
#   "user_id":        "550e8400-...",          # GSI-2 PK + SK helpers
#   "match_id":       "a3f1b200-...",
#   "home_goals":     2,
#   "away_goals":     0,
#   "status":         "ACTIVE",                # ACTIVE | SUPERSEDED | SCORED
#   "points_earned":  None,                    # null hasta que se procese el resultado
#   "scoring_reason": None,                    # EXACT_SCORE | CORRECT_WINNER_AND_DIFF | ...
#   "created_at":     "2026-06-15T10:00:00Z",
#   "updated_at":     "2026-06-15T10:00:00Z",
# }
#
# PARTIDO
# ───────
# PK: MATCH#<uuid>    SK: DETAILS
# {
#   "partition_key":       "MATCH#a3f1b200-...",
#   "sort_key":            "DETAILS",
#   "match_id":            "a3f1b200-...",
#   "home_team":           "ARG",
#   "away_team":           "BRA",
#   "phase":               "GROUP",            # GROUP | R16 | QF | SF | FINAL | THIRD_PLACE
#   "kickoff_utc":         "2026-06-15T18:00:00Z",
#   "venue":               "MetLife Stadium",
#   "veda_active":         False,              # True desde kickoff-30min
#   "status":              "SCHEDULED",        # SCHEDULED | IN_PROGRESS | FINISHED
#   "result_processed":    False,
# }
#
# RESULTADO
# ─────────
# PK: MATCH#<uuid>    SK: RESULT
# {
#   "partition_key":       "MATCH#a3f1b200-...",
#   "sort_key":            "RESULT",
#   "match_id":            "a3f1b200-...",
#   "result_90min_home":   1,                  # Usado para scoring en todas las fases
#   "result_90min_away":   1,
#   "result_final_home":   1,                  # Puede diferir (penales, ET)
#   "result_final_away":   2,
#   "went_to_et":          False,
#   "went_to_penalties":   True,
#   "source":              "AUTO_WEBSEARCH",   # AUTO_WEBSEARCH | MANUAL_ADMIN
#   "result_processed":    True,
#   "processed_at":        "2026-06-15T20:15:00Z",
# }
#
# TRIVIA SESIÓN (TTL 30min)
# ─────────────────────────
# PK: USER#<uuid>    SK: TRIVIA#<session_uuid>
# {
#   "partition_key":  "USER#550e8400-...",
#   "sort_key":       "TRIVIA#7c3a1f00-...",
#   "session_id":     "7c3a1f00-...",
#   "user_id":        "550e8400-...",
#   "match_id":       "a3f1b200-...",          # Partido temático de la pregunta
#   "question":       "¿En qué año fue el primer Mundial?",
#   "options":        ["1926", "1930", "1934", "1938"],
#   "correct_answer": "1930",
#   "difficulty":     "easy",                  # easy | medium | hard
#   "user_answer":    None,                    # null hasta que responda
#   "is_correct":     None,
#   "points_earned":  None,
#   "state":          "PENDING",               # PENDING | ANSWERED | EXPIRED
#   "ttl_expiry":     1750000000,              # Unix timestamp NOW+30min
#   "created_at":     "2026-06-15T19:00:00Z",
# }
#
# WS CONEXIÓN (TTL 8h)
# ────────────────────
# PK: WS#<connection_id>    SK: DETAILS
# {
#   "partition_key":  "WS#abc123def456",
#   "sort_key":       "DETAILS",
#   "connection_id":  "abc123def456",
#   "user_id":        "550e8400-...",
#   "group_ids":      ["grp-001", "grp-002"], # Grupos del usuario para broadcast
#   "connected_at":   "2026-06-15T19:00:00Z",
#   "ttl_expiry":     1750028800,             # Unix timestamp NOW+8h
# }
#
# CACHE WEB_SEARCH (TTL 24h)
# ──────────────────────────
# PK: CACHE#<sha256(query)>    SK: RESULT
# {
#   "partition_key":  "CACHE#3f4a9b...",
#   "sort_key":       "RESULT",
#   "query":          "Argentina vs Brazil World Cup 2026 score",
#   "result":         "{ ... }",              # JSON string del resultado
#   "ttl_expiry":     1750086400,             # Unix timestamp NOW+24h
#   "cached_at":      "2026-06-15T20:00:00Z",
# }
