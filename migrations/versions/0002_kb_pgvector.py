"""kb_chunks + pgvector

Revision ID: 0002_kb_pgvector
Revises: 0001_initial_schema
"""
from pathlib import Path

from alembic import op

revision = "0002_kb_pgvector"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_SQL = (Path(__file__).resolve().parents[2] / "infrastructure/db/kb_pgvector.sql").read_text()


def upgrade() -> None:
    op.execute(_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prode.kb_chunks;")
