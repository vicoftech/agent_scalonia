"""Cliente DynamoDB con región explícita (Lambda + scripts CLI)."""
from __future__ import annotations

import os
from typing import Any

import boto3

_session: boto3.Session | None = None


def configure_aws(
    *,
    profile: str | None = None,
    region: str | None = None,
) -> None:
    """
    Fija la sesión boto3 para scripts locales (--profile / AWS_PROFILE).
    Llamar antes del primer get_table() en el proceso.
    """
    global _session
    prof = profile or os.environ.get("AWS_PROFILE")
    reg = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    if profile:
        os.environ["AWS_PROFILE"] = profile
    if region:
        os.environ["AWS_REGION"] = region
    _session = boto3.Session(profile_name=prof, region_name=reg)


def get_session() -> boto3.Session:
    global _session
    if _session is None:
        reg = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        prof = os.environ.get("AWS_PROFILE")
        _session = boto3.Session(profile_name=prof, region_name=reg)
    return _session


def get_table(table_name: str | None = None) -> Any:
    name = table_name or os.environ.get("DYNAMODB_TABLE", "ProdeTable")
    return get_session().resource("dynamodb").Table(name)
