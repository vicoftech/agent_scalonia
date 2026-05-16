"""Initial schema — Prode Mundial 2026

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-15

Esta migration crea el schema completo de Aurora PostgreSQL.
Es idempotente: usa IF NOT EXISTS en todas las operaciones.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensiones
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # Tipos enumerados (IF NOT EXISTS requiere bloque DO en PG < 16)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE platform_type AS ENUM ('TELEGRAM', 'TEAMS');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE match_phase AS ENUM
                ('GROUP', 'R16', 'QF', 'SF', 'THIRD_PLACE', 'FINAL');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE match_status AS ENUM
                ('SCHEDULED', 'IN_PROGRESS', 'FINISHED', 'CANCELLED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE prediction_status AS ENUM
                ('ACTIVE', 'SUPERSEDED', 'SCORED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE scoring_reason AS ENUM
                ('EXACT_SCORE', 'CORRECT_WINNER_AND_DIFF',
                 'CORRECT_WINNER_ONLY', 'INCORRECT');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE result_source AS ENUM
                ('AUTO_WEBSEARCH', 'MANUAL_ADMIN');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE trivia_difficulty AS ENUM ('easy', 'medium', 'hard');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE trivia_state AS ENUM ('PENDING', 'ANSWERED', 'EXPIRED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # Tabla: users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("alias", sa.String(50), nullable=False),
        sa.Column("platform", postgresql.ENUM("TELEGRAM", "TEAMS",
                  name="platform_type", create_type=False), nullable=False),
        sa.Column("platform_id_hash", sa.String(64), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("total_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("match_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("trivia_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("platform", "platform_id_hash", name="uq_users_platform_hash"),
        sa.CheckConstraint("char_length(alias) BETWEEN 2 AND 50", name="chk_users_alias_length"),
        sa.CheckConstraint(
            "total_points >= 0 AND match_points >= 0 AND trivia_points >= 0",
            name="chk_users_points_non_negative",
        ),
        sa.CheckConstraint(
            "total_points = match_points + trivia_points",
            name="chk_users_points_coherent",
        ),
    )
    op.create_index("idx_users_alias", "users", ["alias"])
    op.create_index("idx_users_platform", "users", ["platform", "platform_id_hash"])
    op.create_index("idx_users_total_points", "users", [sa.text("total_points DESC")])

    # Tabla: matches
    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("home_team", sa.String(10), nullable=False),
        sa.Column("away_team", sa.String(10), nullable=False),
        sa.Column("phase", postgresql.ENUM("GROUP", "R16", "QF", "SF", "THIRD_PLACE", "FINAL",
                  name="match_phase", create_type=False), nullable=False),
        sa.Column("group_letter", sa.CHAR(1), nullable=True),
        sa.Column("match_number", sa.SmallInteger, nullable=False),
        sa.Column("kickoff_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("venue", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(50), nullable=True),
        sa.Column("veda_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", postgresql.ENUM(
            "SCHEDULED", "IN_PROGRESS", "FINISHED", "CANCELLED",
            name="match_status", create_type=False),
            nullable=False, server_default="'SCHEDULED'"),
        sa.Column("result_processed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("match_number", name="uq_matches_number"),
        sa.CheckConstraint("home_team <> away_team", name="chk_matches_teams_differ"),
    )
    op.create_index("idx_matches_kickoff", "matches", ["kickoff_utc"])
    op.create_index("idx_matches_phase", "matches", ["phase"])
    op.create_index("idx_matches_status", "matches", ["status"])

    # Tabla: match_results
    op.create_table(
        "match_results",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_90min_home", sa.SmallInteger, nullable=False),
        sa.Column("result_90min_away", sa.SmallInteger, nullable=False),
        sa.Column("result_final_home", sa.SmallInteger, nullable=False),
        sa.Column("result_final_away", sa.SmallInteger, nullable=False),
        sa.Column("went_to_et", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("went_to_penalties", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("source", postgresql.ENUM("AUTO_WEBSEARCH", "MANUAL_ADMIN",
                  name="result_source", create_type=False), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("match_id", name="uq_match_results_match"),
    )
    op.create_index("idx_match_results_match_id", "match_results", ["match_id"])

    # Tabla: groups
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("invite_code", sa.CHAR(6), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("max_members", sa.SmallInteger, nullable=False, server_default="50"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("invite_code", name="uq_groups_invite_code"),
    )
    op.create_index("idx_groups_invite_code", "groups", ["invite_code"])
    op.create_index("idx_groups_owner", "groups", ["owner_id"])

    # Tabla: group_members
    op.create_table(
        "group_members",
        sa.Column("group_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
    )
    op.create_index("idx_group_members_user", "group_members", ["user_id"])
    op.create_index("idx_group_members_group", "group_members", ["group_id"])

    # Tabla: predictions
    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("home_goals", sa.SmallInteger, nullable=False),
        sa.Column("away_goals", sa.SmallInteger, nullable=False),
        sa.Column("status", postgresql.ENUM(
            "ACTIVE", "SUPERSEDED", "SCORED",
            name="prediction_status", create_type=False),
            nullable=False, server_default="'ACTIVE'"),
        sa.Column("points_earned", sa.SmallInteger, nullable=True),
        sa.Column("scoring_reason", postgresql.ENUM(
            "EXACT_SCORE", "CORRECT_WINNER_AND_DIFF", "CORRECT_WINNER_ONLY", "INCORRECT",
            name="scoring_reason", create_type=False), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "match_id",
                            name="uq_predictions_active",
                            deferrable=True, initially="DEFERRED"),
    )
    op.create_index("idx_predictions_user", "predictions", ["user_id"])
    op.create_index("idx_predictions_match", "predictions", ["match_id"])
    op.create_index("idx_predictions_user_match", "predictions", ["user_id", "match_id"])
    op.execute(
        "CREATE INDEX idx_predictions_active_only ON predictions (user_id, match_id) "
        "WHERE status = 'ACTIVE'"
    )

    # Tabla: trivia_sessions
    op.create_table(
        "trivia_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("matches.id"), nullable=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("options", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("correct_answer", sa.String(200), nullable=False),
        sa.Column("difficulty", postgresql.ENUM("easy", "medium", "hard",
                  name="trivia_difficulty", create_type=False), nullable=False),
        sa.Column("user_answer", sa.String(200), nullable=True),
        sa.Column("is_correct", sa.Boolean, nullable=True),
        sa.Column("points_earned", sa.SmallInteger, nullable=True),
        sa.Column("state", postgresql.ENUM("PENDING", "ANSWERED", "EXPIRED",
                  name="trivia_state", create_type=False),
                  nullable=False, server_default="'PENDING'"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("answered_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_trivia_user", "trivia_sessions", ["user_id"])
    op.create_index("idx_trivia_user_date", "trivia_sessions", ["user_id", "created_at"])
    op.create_index("idx_trivia_match", "trivia_sessions", ["match_id"])

    # Tabla: ranking_history
    op.create_table(
        "ranking_history",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("total_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("match_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("trivia_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("delta_position", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("delta_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("snapshot_date", "user_id", "group_id",
                            name="uq_ranking_history_snap"),
    )
    op.create_index("idx_ranking_history_date", "ranking_history",
                    [sa.text("snapshot_date DESC")])
    op.create_index("idx_ranking_history_user", "ranking_history",
                    ["user_id", sa.text("snapshot_date DESC")])
    op.create_index("idx_ranking_history_group", "ranking_history",
                    ["group_id", sa.text("snapshot_date DESC")])

    # Función y triggers para updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("users", "matches", "predictions", "groups"):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)

    # Vistas
    op.execute("""
        CREATE VIEW v_group_ranking AS
        SELECT gm.group_id, g.name AS group_name, u.id AS user_id, u.alias,
               u.total_points, u.match_points, u.trivia_points,
               RANK() OVER (PARTITION BY gm.group_id ORDER BY u.total_points DESC, u.created_at ASC) AS position
        FROM group_members gm
        JOIN groups g ON g.id = gm.group_id
        JOIN users u  ON u.id = gm.user_id
        WHERE g.active = TRUE;
    """)
    op.execute("""
        CREATE VIEW v_user_prediction_history AS
        SELECT p.user_id, p.id AS prediction_id, m.match_number, m.home_team, m.away_team,
               m.phase, m.kickoff_utc, p.home_goals AS pred_home, p.away_goals AS pred_away,
               r.result_90min_home AS actual_home, r.result_90min_away AS actual_away,
               p.status, p.points_earned, p.scoring_reason, p.created_at AS predicted_at
        FROM predictions p
        JOIN matches m            ON m.id = p.match_id
        LEFT JOIN match_results r ON r.match_id = m.id
        WHERE p.status IN ('ACTIVE', 'SCORED')
        ORDER BY m.kickoff_utc ASC;
    """)
    op.execute("""
        CREATE VIEW v_user_score_summary AS
        SELECT u.id AS user_id, u.alias, u.total_points, u.match_points, u.trivia_points,
               COUNT(p.id) FILTER (WHERE p.status = 'SCORED')         AS predictions_scored,
               COUNT(p.id) FILTER (WHERE p.scoring_reason = 'EXACT_SCORE') AS exact_predictions,
               COUNT(ts.id) FILTER (WHERE ts.is_correct = TRUE)        AS trivia_correct,
               RANK() OVER (ORDER BY u.total_points DESC)              AS global_position
        FROM users u
        LEFT JOIN predictions p      ON p.user_id = u.id
        LEFT JOIN trivia_sessions ts ON ts.user_id = u.id AND ts.state = 'ANSWERED'
        GROUP BY u.id, u.alias, u.total_points, u.match_points, u.trivia_points;
    """)
    op.execute("""
        CREATE VIEW v_members_without_prediction AS
        SELECT gm.group_id, gm.user_id, u.alias, u.platform, u.notifications_enabled,
               m.id AS match_id, m.home_team, m.away_team, m.kickoff_utc
        FROM group_members gm
        JOIN users u    ON u.id = gm.user_id
        CROSS JOIN matches m
        LEFT JOIN predictions p ON (p.user_id = gm.user_id AND p.match_id = m.id AND p.status = 'ACTIVE')
        WHERE p.id IS NULL AND m.status = 'SCHEDULED' AND u.notifications_enabled = TRUE;
    """)

    # Roles
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prode_sync') THEN
                CREATE ROLE prode_sync LOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prode_reader') THEN
                CREATE ROLE prode_reader LOGIN;
            END IF;
        END $$;
    """)
    op.execute("""
        GRANT INSERT, UPDATE ON TABLE
            users, matches, match_results, predictions,
            groups, group_members, trivia_sessions, ranking_history
        TO prode_sync;
        GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO prode_sync;
        GRANT SELECT ON TABLE
            users, matches, match_results, predictions, groups, group_members,
            trivia_sessions, ranking_history,
            v_group_ranking, v_user_prediction_history,
            v_user_score_summary, v_members_without_prediction
        TO prode_reader;
    """)


def downgrade() -> None:
    # Vistas
    for view in ("v_members_without_prediction", "v_user_score_summary",
                 "v_user_prediction_history", "v_group_ranking"):
        op.execute(f"DROP VIEW IF EXISTS {view}")

    # Tablas (orden inverso de dependencias)
    for table in ("ranking_history", "trivia_sessions", "predictions",
                  "group_members", "groups", "match_results", "matches", "users"):
        op.drop_table(table)

    # Tipos enumerados
    for typ in ("trivia_state", "trivia_difficulty", "result_source", "scoring_reason",
                "prediction_status", "match_status", "match_phase", "platform_type"):
        op.execute(f"DROP TYPE IF EXISTS {typ}")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column CASCADE")
