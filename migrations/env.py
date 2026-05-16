"""migrations/env.py — Alembic configuration for Aurora PostgreSQL"""
import os
import json
import boto3
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    """Obtiene la URL de Aurora desde Secrets Manager."""
    secret_arn = os.environ.get("AURORA_SYNC_SECRET_ARN")
    proxy_host = os.environ.get("RDS_PROXY_ENDPOINT", "localhost")
    db_name    = os.environ.get("DB_NAME", "prode")

    if secret_arn:
        secret = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
        creds  = json.loads(secret["SecretString"])
        return (f"postgresql+psycopg2://{creds['username']}:{creds['password']}"
                f"@{proxy_host}/{db_name}")

    # Fallback para desarrollo local
    return os.environ.get(
        "DATABASE_URL",
        f"postgresql+psycopg2://prode_sync:devpassword@localhost:5432/{db_name}"
    )


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(url=url, target_metadata=None,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
