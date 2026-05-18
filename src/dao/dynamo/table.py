"""Cliente DynamoDB con región explícita (Lambda + AgentCore)."""
from __future__ import annotations

import os

import boto3


def get_table(table_name: str | None = None):
    name = table_name or os.environ.get("DYNAMODB_TABLE", "ProdeTable")
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    return boto3.resource("dynamodb", region_name=region).Table(name)
