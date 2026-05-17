-- =============================================================================
-- Aurora PostgreSQL 16 — Prode Mundial 2026
-- DDL completo del schema relacional
--
-- Propósito: espejo de DynamoDB para queries con JOIN.
--            Aurora es SOLO LECTURA desde el punto de vista del agente.
--            La Lambda sync_dynamo_to_aurora es el único writer.
--
-- Convenciones:
--   Tablas:    snake_case plural
--   Columnas:  snake_case
--   PKs:       id UUID DEFAULT gen_random_uuid()
--   FKs:       <tabla_singular>_id UUID NOT NULL REFERENCES <tabla>(id)
--   Timestamps: created_at TIMESTAMPTZ DEFAULT NOW()
--   Índices:   idx_<tabla>_<columna(s)>
--
-- Ejecutar: alembic upgrade head (en CI/CD, nunca en Lambda runtime)
-- Schema:  prode (no usar public para tablas/vistas del producto)
-- Teardown (solo objetos de este DDL en public): aurora_schema_drop.sql
-- =============================================================================

-- =============================================================================
-- ESQUEMA
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS prode;

COMMENT ON SCHEMA prode IS
    'Schema dedicado del Prode Mundial 2026. Tablas, vistas, tipos y funciones viven aquí; '
    'las extensiones permanecen en public.';

SET search_path TO prode, public;

-- =============================================================================
-- EXTENSIONES (en public; visibles vía search_path)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- búsqueda por alias (futuro)

-- =============================================================================
-- TIPOS ENUMERADOS
-- =============================================================================

CREATE TYPE platform_type AS ENUM (
    'TELEGRAM',
    'TEAMS'
);

CREATE TYPE match_phase AS ENUM (
    'GROUP',
    'R16',
    'QF',
    'SF',
    'THIRD_PLACE',
    'FINAL'
);

CREATE TYPE match_status AS ENUM (
    'SCHEDULED',
    'IN_PROGRESS',
    'FINISHED',
    'CANCELLED'
);

CREATE TYPE prediction_status AS ENUM (
    'ACTIVE',       -- predicción vigente
    'SUPERSEDED',   -- reemplazada por una nueva antes de la veda
    'SCORED'        -- ya se calcularon los puntos
);

CREATE TYPE scoring_reason AS ENUM (
    'EXACT_SCORE',              -- 5 pts
    'CORRECT_WINNER_AND_DIFF',  -- 3 pts
    'CORRECT_WINNER_ONLY',      -- 1 pt
    'INCORRECT'                 -- 0 pts
);

CREATE TYPE result_source AS ENUM (
    'AUTO_WEBSEARCH',
    'MANUAL_ADMIN'
);

CREATE TYPE trivia_difficulty AS ENUM (
    'easy',     -- 1 pt
    'medium',   -- 2 pts
    'hard'      -- 3 pts
);

CREATE TYPE trivia_state AS ENUM (
    'PENDING',
    'ANSWERED',
    'EXPIRED'
);

-- =============================================================================
-- TABLA: users
-- Espejo de USER#<uuid>/PROFILE en DynamoDB.
-- JOIN target para predicciones, membresías y ranking.
-- =============================================================================

CREATE TABLE users (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    alias                   VARCHAR(50)     NOT NULL,
    platform                platform_type   NOT NULL,
    platform_id_hash        VARCHAR(64)     NOT NULL,   -- SHA-256(chat_id / Teams userId)
    notifications_enabled   BOOLEAN         NOT NULL DEFAULT TRUE,
    total_points            INTEGER         NOT NULL DEFAULT 0,
    match_points            INTEGER         NOT NULL DEFAULT 0,
    trivia_points           INTEGER         NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Invariante: un platform_id_hash es único por plataforma
    CONSTRAINT uq_users_platform_hash UNIQUE (platform, platform_id_hash),
    CONSTRAINT chk_users_alias_length CHECK (char_length(alias) BETWEEN 2 AND 50),
    CONSTRAINT chk_users_points_non_negative CHECK (
        total_points >= 0 AND match_points >= 0 AND trivia_points >= 0
    ),
    CONSTRAINT chk_users_points_coherent CHECK (
        total_points = match_points + trivia_points
    )
);

COMMENT ON TABLE users IS
    'Espejo de DynamoDB USER#<uuid>/PROFILE. '
    'Fuente de verdad: DynamoDB. Este registro es actualizado por sync_dynamo_to_aurora.';

CREATE INDEX idx_users_alias ON users (alias);
CREATE INDEX idx_users_platform ON users (platform, platform_id_hash);
CREATE INDEX idx_users_total_points ON users (total_points DESC);


-- =============================================================================
-- TABLA: matches
-- Espejo de MATCH#<uuid>/DETAILS en DynamoDB.
-- JOIN target para predicciones y trivia.
-- =============================================================================

CREATE TABLE matches (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    home_team           VARCHAR(10)     NOT NULL,   -- código FIFA: "ARG", "BRA", "FRA"
    away_team           VARCHAR(10)     NOT NULL,
    phase               match_phase     NOT NULL,
    group_letter        CHAR(1),                    -- NULL para fases eliminatorias
    match_number        SMALLINT        NOT NULL,   -- 1..64 según fixture oficial
    kickoff_utc         TIMESTAMPTZ     NOT NULL,
    venue               VARCHAR(100),
    city                VARCHAR(100),
    country             VARCHAR(50),                -- USA | CAN | MEX
    veda_active         BOOLEAN         NOT NULL DEFAULT FALSE,
    status              match_status    NOT NULL DEFAULT 'SCHEDULED',
    result_processed    BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_matches_number UNIQUE (match_number),
    CONSTRAINT chk_matches_teams_differ CHECK (home_team <> away_team),
    CONSTRAINT chk_matches_group_phase CHECK (
        (phase = 'GROUP' AND group_letter IS NOT NULL) OR
        (phase <> 'GROUP' AND group_letter IS NULL)
    )
);

COMMENT ON TABLE matches IS
    'Espejo de DynamoDB MATCH#<uuid>/DETAILS. '
    'Fixture completo del Mundial 2026 (64 partidos).';

CREATE INDEX idx_matches_kickoff ON matches (kickoff_utc);
CREATE INDEX idx_matches_phase ON matches (phase);
CREATE INDEX idx_matches_status ON matches (status);


-- =============================================================================
-- TABLA: match_results
-- Espejo de MATCH#<uuid>/RESULT en DynamoDB.
-- Separada de matches para que matches sea insertable antes de conocer el resultado.
-- =============================================================================

CREATE TABLE match_results (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id            UUID            NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    result_90min_home   SMALLINT        NOT NULL,   -- Usado para scoring en TODAS las fases
    result_90min_away   SMALLINT        NOT NULL,
    result_final_home   SMALLINT        NOT NULL,   -- Puede diferir si hubo ET/penales
    result_final_away   SMALLINT        NOT NULL,
    went_to_et          BOOLEAN         NOT NULL DEFAULT FALSE,
    went_to_penalties   BOOLEAN         NOT NULL DEFAULT FALSE,
    source              result_source   NOT NULL,
    processed_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    admin_user_id       UUID            REFERENCES users(id), -- no null si source = MANUAL_ADMIN

    CONSTRAINT uq_match_results_match UNIQUE (match_id),
    CONSTRAINT chk_match_results_goals_non_negative CHECK (
        result_90min_home >= 0 AND result_90min_away >= 0 AND
        result_final_home >= 0 AND result_final_away >= 0
    ),
    CONSTRAINT chk_match_results_admin CHECK (
        (source = 'MANUAL_ADMIN' AND admin_user_id IS NOT NULL) OR
        (source = 'AUTO_WEBSEARCH' AND admin_user_id IS NULL)
    )
);

COMMENT ON TABLE match_results IS
    'Resultado de partidos finalizados. '
    'result_90min_* es SIEMPRE la base del scoring, incluso en fases eliminatorias. '
    'Espejo de DynamoDB MATCH#<uuid>/RESULT.';

CREATE INDEX idx_match_results_match_id ON match_results (match_id);


-- =============================================================================
-- TABLA: predictions
-- Espejo de USER#<uuid>/PRED#<match_uuid> en DynamoDB.
-- El JOIN más frecuente: predicciones + usuarios + partidos.
-- =============================================================================

CREATE TABLE predictions (
    id              UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID                NOT NULL REFERENCES users(id),
    match_id        UUID                NOT NULL REFERENCES matches(id),
    home_goals      SMALLINT            NOT NULL,
    away_goals      SMALLINT            NOT NULL,
    status          prediction_status   NOT NULL DEFAULT 'ACTIVE',
    points_earned   SMALLINT,                           -- NULL hasta scoring
    scoring_reason  scoring_reason,                     -- NULL hasta scoring
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    -- Solo puede haber una predicción ACTIVE por usuario/partido
    -- Las SUPERSEDED pueden ser múltiples (historial de cambios)
    CONSTRAINT uq_predictions_active UNIQUE (user_id, match_id)
        DEFERRABLE INITIALLY DEFERRED,                  -- se suspende durante el upsert de sync

    CONSTRAINT chk_predictions_goals_non_negative CHECK (
        home_goals >= 0 AND away_goals >= 0
    ),
    CONSTRAINT chk_predictions_scored_complete CHECK (
        (status = 'SCORED' AND points_earned IS NOT NULL AND scoring_reason IS NOT NULL) OR
        (status <> 'SCORED')
    )
);

COMMENT ON TABLE predictions IS
    'Predicciones de marcadores. '
    'Espejo de DynamoDB USER#<uuid>/PRED#<match_uuid>. '
    'UNIQUE deferrable para permitir upsert atómico durante sincronización.';

CREATE INDEX idx_predictions_user ON predictions (user_id);
CREATE INDEX idx_predictions_match ON predictions (match_id);
CREATE INDEX idx_predictions_status ON predictions (status);
CREATE INDEX idx_predictions_user_match ON predictions (user_id, match_id);

-- Índice parcial: solo predicciones activas (las más consultadas)
CREATE INDEX idx_predictions_active_only ON predictions (user_id, match_id)
    WHERE status = 'ACTIVE';


-- =============================================================================
-- TABLA: groups
-- Espejo de GROUP#<uuid>/DETAILS en DynamoDB.
-- =============================================================================

CREATE TABLE groups (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(80) NOT NULL,
    invite_code     CHAR(6)     NOT NULL,
    owner_id        UUID        NOT NULL REFERENCES users(id),
    max_members     SMALLINT    NOT NULL DEFAULT 50,
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_groups_invite_code UNIQUE (invite_code),
    CONSTRAINT chk_groups_name_length CHECK (char_length(name) BETWEEN 2 AND 80),
    CONSTRAINT chk_groups_max_members CHECK (max_members BETWEEN 2 AND 50)
);

COMMENT ON TABLE groups IS
    'Grupos de competición. '
    'Espejo de DynamoDB GROUP#<uuid>/DETAILS.';

CREATE INDEX idx_groups_invite_code ON groups (invite_code);
CREATE INDEX idx_groups_owner ON groups (owner_id);


-- =============================================================================
-- TABLA: group_members
-- Espejo de GROUP#<uuid>/MEMBER#<user_uuid> en DynamoDB.
-- Tabla de join N:M entre groups y users.
-- =============================================================================

CREATE TABLE group_members (
    group_id    UUID        NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (group_id, user_id)
);

COMMENT ON TABLE group_members IS
    'Membresías N:M grupos-usuarios. '
    'Espejo de DynamoDB GROUP#<uuid>/MEMBER#<user_uuid>.';

CREATE INDEX idx_group_members_user ON group_members (user_id);
CREATE INDEX idx_group_members_group ON group_members (group_id);


-- =============================================================================
-- TABLA: trivia_sessions
-- Espejo de USER#<uuid>/TRIVIA#<session_uuid> en DynamoDB.
-- En DynamoDB tiene TTL de 30min. En Aurora se mantiene como historial.
-- =============================================================================

CREATE TABLE trivia_sessions (
    id              UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID                NOT NULL REFERENCES users(id),
    match_id        UUID                REFERENCES matches(id), -- partido temático
    question        TEXT                NOT NULL,
    options         TEXT[]              NOT NULL,               -- array de 4 opciones
    correct_answer  VARCHAR(200)        NOT NULL,
    difficulty      trivia_difficulty   NOT NULL,
    user_answer     VARCHAR(200),                               -- NULL hasta que responda
    is_correct      BOOLEAN,                                    -- NULL hasta que responda
    points_earned   SMALLINT,                                   -- NULL hasta scoring
    state           trivia_state        NOT NULL DEFAULT 'PENDING',
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    answered_at     TIMESTAMPTZ,

    CONSTRAINT chk_trivia_options_count CHECK (array_length(options, 1) = 4),
    CONSTRAINT chk_trivia_answered_state CHECK (
        (state = 'ANSWERED' AND user_answer IS NOT NULL AND is_correct IS NOT NULL AND answered_at IS NOT NULL) OR
        (state <> 'ANSWERED')
    ),
    CONSTRAINT chk_trivia_points_coherent CHECK (
        (is_correct = TRUE AND points_earned > 0) OR
        (is_correct = FALSE AND (points_earned = 0 OR points_earned IS NULL)) OR
        (is_correct IS NULL)
    )
);

COMMENT ON TABLE trivia_sessions IS
    'Historial de sesiones de trivia. '
    'El runtime usa DynamoDB (TTL 30min). '
    'Aurora mantiene el historial completo para analytics y desglose de puntos.';

CREATE INDEX idx_trivia_user ON trivia_sessions (user_id);
CREATE INDEX idx_trivia_user_date ON trivia_sessions (user_id, created_at);
CREATE INDEX idx_trivia_match ON trivia_sessions (match_id);


-- =============================================================================
-- TABLA: ranking_history
-- Espejo de RANKING_SNAP#<date>/USER#<uuid> en DynamoDB.
-- Historial de posiciones diarias para consultas como "¿cómo estaba el 14 de junio?"
-- =============================================================================

CREATE TABLE ranking_history (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date   DATE        NOT NULL,
    user_id         UUID        NOT NULL REFERENCES users(id),
    group_id        UUID        REFERENCES groups(id),   -- NULL = ranking global
    position        SMALLINT    NOT NULL,
    total_points    INTEGER     NOT NULL DEFAULT 0,
    match_points    INTEGER     NOT NULL DEFAULT 0,
    trivia_points   INTEGER     NOT NULL DEFAULT 0,
    delta_position  SMALLINT    NOT NULL DEFAULT 0,      -- negativo = subió posiciones
    delta_points    INTEGER     NOT NULL DEFAULT 0,      -- puntos ganados ese día
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ranking_history_snap UNIQUE (snapshot_date, user_id, group_id)
);

COMMENT ON TABLE ranking_history IS
    'Snapshots diarios de ranking. TTL 90 días en DynamoDB, sin TTL en Aurora. '
    'group_id = NULL significa ranking global.';

CREATE INDEX idx_ranking_history_date ON ranking_history (snapshot_date DESC);
CREATE INDEX idx_ranking_history_user ON ranking_history (user_id, snapshot_date DESC);
CREATE INDEX idx_ranking_history_group ON ranking_history (group_id, snapshot_date DESC);


-- =============================================================================
-- VISTAS — Queries frecuentes del agente pre-armadas
-- =============================================================================

-- Vista: ranking actual por grupo con alias de usuario
CREATE VIEW v_group_ranking AS
SELECT
    gm.group_id,
    g.name                                          AS group_name,
    u.id                                            AS user_id,
    u.alias,
    u.total_points,
    u.match_points,
    u.trivia_points,
    RANK() OVER (
        PARTITION BY gm.group_id
        ORDER BY u.total_points DESC, u.created_at ASC
    )                                               AS position
FROM group_members gm
JOIN groups g   ON g.id = gm.group_id
JOIN users u    ON u.id = gm.user_id
WHERE g.active = TRUE;

COMMENT ON VIEW v_group_ranking IS
    'Ranking actual de cada grupo con posición calculada. '
    'Usado por ranking_tool para responder "/ranking-grupo <nombre>".';


-- Vista: historial de predicciones de un usuario con datos del partido
CREATE VIEW v_user_prediction_history AS
SELECT
    p.user_id,
    p.id                                AS prediction_id,
    m.match_number,
    m.home_team,
    m.away_team,
    m.phase,
    m.kickoff_utc,
    p.home_goals                        AS pred_home,
    p.away_goals                        AS pred_away,
    r.result_90min_home                 AS actual_home,
    r.result_90min_away                 AS actual_away,
    p.status,
    p.points_earned,
    p.scoring_reason,
    p.created_at                        AS predicted_at
FROM predictions p
JOIN matches m               ON m.id = p.match_id
LEFT JOIN match_results r    ON r.match_id = m.id
WHERE p.status IN ('ACTIVE', 'SCORED')
ORDER BY m.kickoff_utc ASC;

COMMENT ON VIEW v_user_prediction_history IS
    'Historial completo de predicciones con resultado real. '
    'Usado por scoring_tool para el desglose de puntos del usuario.';


-- Vista: resumen de puntos por usuario (desglose)
CREATE VIEW v_user_score_summary AS
SELECT
    u.id                                            AS user_id,
    u.alias,
    u.total_points,
    u.match_points,
    u.trivia_points,
    COUNT(p.id) FILTER (WHERE p.status = 'SCORED')  AS predictions_scored,
    COUNT(p.id) FILTER (
        WHERE p.scoring_reason = 'EXACT_SCORE'
    )                                               AS exact_predictions,
    COUNT(ts.id) FILTER (WHERE ts.is_correct = TRUE) AS trivia_correct,
    RANK() OVER (ORDER BY u.total_points DESC)      AS global_position
FROM users u
LEFT JOIN predictions p         ON p.user_id = u.id
LEFT JOIN trivia_sessions ts    ON ts.user_id = u.id AND ts.state = 'ANSWERED'
GROUP BY u.id, u.alias, u.total_points, u.match_points, u.trivia_points;

COMMENT ON VIEW v_user_score_summary IS
    'Resumen completo de puntos con posición global. '
    'Usado por scoring_tool para "/mis-puntos".';


-- Vista: usuarios de un grupo sin predicción para un partido dado
-- Uso: recordatorio de veda — quién no predijo todavía
-- Parámetro: se usa como función o con WHERE en la query del DAO
CREATE VIEW v_members_without_prediction AS
SELECT
    gm.group_id,
    gm.user_id,
    u.alias,
    u.platform,
    u.notifications_enabled,
    m.id                AS match_id,
    m.home_team,
    m.away_team,
    m.kickoff_utc
FROM group_members gm
JOIN users u    ON u.id = gm.user_id
CROSS JOIN matches m
LEFT JOIN predictions p ON (
    p.user_id = gm.user_id
    AND p.match_id = m.id
    AND p.status = 'ACTIVE'
)
WHERE p.id IS NULL
  AND m.status = 'SCHEDULED'
  AND u.notifications_enabled = TRUE;

COMMENT ON VIEW v_members_without_prediction IS
    'Combinación grupo × partido × usuario donde el usuario no tiene predicción activa. '
    'Filtrar por match_id específico en la query del DAO de recordatorios.';


-- =============================================================================
-- FUNCIÓN: actualizar updated_at automáticamente
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_predictions_updated_at
    BEFORE UPDATE ON predictions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_groups_updated_at
    BEFORE UPDATE ON groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- GRANTS — rol de aplicación con permisos mínimos
-- =============================================================================

-- La Lambda sync_dynamo_to_aurora usa el rol 'prode_sync'
-- Las Lambdas de lectura (tools del agente) usan el rol 'prode_reader'

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prode_sync') THEN
        CREATE ROLE prode_sync LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prode_reader') THEN
        CREATE ROLE prode_reader LOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA prode TO prode_sync, prode_reader;

-- prode_sync: solo INSERT y UPDATE (nunca DELETE en producción)
GRANT INSERT, UPDATE ON ALL TABLES IN SCHEMA prode TO prode_sync;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA prode TO prode_sync;

-- prode_reader: solo SELECT (tablas + vistas)
GRANT SELECT ON ALL TABLES IN SCHEMA prode TO prode_reader;

ALTER ROLE prode_sync SET search_path TO prode, public;
ALTER ROLE prode_reader SET search_path TO prode, public;


-- =============================================================================
-- SEED: fixture del Mundial 2026 — fase de grupos
-- Ejecutar después de `alembic upgrade head` en staging.
-- Los UUIDs son determinísticos para facilitar tests.
-- =============================================================================

-- Ejemplo de los primeros partidos (completar con fixture oficial FIFA 2026)
INSERT INTO matches (id, match_number, home_team, away_team, phase, group_letter, kickoff_utc, venue, city, country)
VALUES
    -- Grupo A
    ('00000000-0000-0000-0000-000000000001', 1,  'MEX', 'ECU', 'GROUP', 'A', '2026-06-11 19:00:00+00', 'Estadio Azteca',         'Ciudad de México', 'MEX'),
    ('00000000-0000-0000-0000-000000000002', 2,  'USA', 'CAN', 'GROUP', 'A', '2026-06-11 22:00:00+00', 'SoFi Stadium',           'Los Ángeles',       'USA'),
    -- Grupo B
    ('00000000-0000-0000-0000-000000000003', 3,  'ARG', 'IND', 'GROUP', 'B', '2026-06-12 19:00:00+00', 'MetLife Stadium',        'East Rutherford',   'USA'),
    ('00000000-0000-0000-0000-000000000004', 4,  'ESP', 'POR', 'GROUP', 'B', '2026-06-12 22:00:00+00', 'AT&T Stadium',           'Arlington',         'USA'),
    -- Grupo C
    ('00000000-0000-0000-0000-000000000005', 5,  'BRA', 'CHI', 'GROUP', 'C', '2026-06-13 19:00:00+00', 'Estadio Akron',          'Guadalajara',       'MEX'),
    ('00000000-0000-0000-0000-000000000006', 6,  'FRA', 'AUS', 'GROUP', 'C', '2026-06-13 22:00:00+00', 'BC Place',               'Vancouver',         'CAN')
    -- ... continúa hasta match_number = 64
ON CONFLICT (match_number) DO NOTHING;
