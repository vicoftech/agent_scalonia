-- Borra solo lo que crea aurora_schema.sql en public.
-- No toca otras tablas/vistas de la otra aplicación.
-- Sin roles, sin schema prode, sin DROP SCHEMA.

-- Vistas
DROP VIEW IF EXISTS public.v_members_without_prediction;
DROP VIEW IF EXISTS public.v_user_score_summary;
DROP VIEW IF EXISTS public.v_user_prediction_history;
DROP VIEW IF EXISTS public.v_group_ranking;

-- Triggers
DROP TRIGGER IF EXISTS trg_groups_updated_at ON public.groups;
DROP TRIGGER IF EXISTS trg_predictions_updated_at ON public.predictions;
DROP TRIGGER IF EXISTS trg_matches_updated_at ON public.matches;
DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;

-- Función
DROP FUNCTION IF EXISTS public.update_updated_at_column();

-- Tablas (hijas primero)
DROP TABLE IF EXISTS public.ranking_history;
DROP TABLE IF EXISTS public.trivia_sessions;
DROP TABLE IF EXISTS public.group_members;
DROP TABLE IF EXISTS public.predictions;
DROP TABLE IF EXISTS public.match_results;
DROP TABLE IF EXISTS public.groups;
DROP TABLE IF EXISTS public.matches;
DROP TABLE IF EXISTS public.users;

-- Tipos enum
DROP TYPE IF EXISTS public.trivia_state;
DROP TYPE IF EXISTS public.trivia_difficulty;
DROP TYPE IF EXISTS public.result_source;
DROP TYPE IF EXISTS public.scoring_reason;
DROP TYPE IF EXISTS public.prediction_status;
DROP TYPE IF EXISTS public.match_status;
DROP TYPE IF EXISTS public.match_phase;
DROP TYPE IF EXISTS public.platform_type;
