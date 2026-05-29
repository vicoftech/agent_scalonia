"""Invocación AgentCore para generación de briefs."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

import boto3

logger = logging.getLogger(__name__)


def default_invoke_agent(prompt: str, *, session_id: str) -> str:
    region = os.environ.get("AWS_REGION", "us-east-1")
    arn = os.environ.get("AGENTCORE_RUNTIME_ARN", "").strip()
    if not arn:
        raise RuntimeError("AGENTCORE_RUNTIME_ARN no configurado")

    client = boto3.client("bedrock-agentcore", region_name=region)
    payload = json.dumps(
        {
            "prompt": prompt,
            "user_id": "brief-orchestrator",
            "platform": "SYSTEM",
            "session_id": session_id,
        }
    ).encode()
    qualifier = os.environ.get("AGENTCORE_RUNTIME_QUALIFIER", "LIVE")
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        qualifier=qualifier,
        runtimeSessionId=session_id[:64],
        payload=payload,
        contentType="application/json",
    )
    return _read_stream(response)


def _read_stream(response: Any) -> str:
    stream = response.get("response")
    if stream is None:
        return ""
    content_type = (response.get("contentType") or "").lower()
    if "text/event-stream" in content_type:
        chunks: list[str] = []
        for line in stream.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
            if text.startswith("data:"):
                chunks.append(text[5:].strip())
        body = "\n".join(chunks)
    else:
        body = stream.read().decode("utf-8", errors="replace") if hasattr(stream, "read") else str(stream)

    return body.strip()


def make_invoke_agent(
    fn: Callable[[str, str], str] | None = None,
) -> Callable[[str, str], str]:
    """Adaptador (prompt, session_id) -> texto."""

    def _invoke(prompt: str, session_id: str) -> str:
        if fn is not None:
            return fn(prompt, session_id=session_id)
        return default_invoke_agent(prompt, session_id=session_id)

    return _invoke
