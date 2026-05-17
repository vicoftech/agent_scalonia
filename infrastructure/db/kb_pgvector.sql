-- Knowledge Base — pgvector en Aurora (SPEC-2026-017)
-- Ejecutar vía: alembic upgrade head o psql (migración 0002_kb_pgvector)
-- Writer: Lambda kb_ingest (S3 trigger). Reader: Lambda kb_query.

SET search_path TO prode, public;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS prode.kb_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_path  TEXT NOT NULL,
    chunk_index  INT  NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector(1024) NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_path, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_source_path
    ON prode.kb_chunks (source_path);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding_hnsw
    ON prode.kb_chunks
    USING hnsw (embedding vector_cosine_ops);

COMMENT ON TABLE prode.kb_chunks IS
    'Chunks de la KB con embeddings Titan v2 (1024). Writer: src/kb/ingest_kb --embed';
