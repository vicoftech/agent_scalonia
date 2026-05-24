"""
Lambda result_poller — SPEC-028 (mock API en dev / pruebas).

Evento:
  {"trigger": "scheduled"}  — todos los fixtures terminales del mock/API
  {"trigger": "fixture", "api_match_id": 2}
  {"use_mock": true, "mock_fixture_path": "data/fixtures/mock_api_football_fixtures.json"}
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _build_client(event: dict):
    if event.get("use_mock", True):
        from src.clients.api_football_mock import MockApiFootballClient

        path = event.get("mock_fixture_path")
        return MockApiFootballClient(path) if path else MockApiFootballClient()
    raise NotImplementedError(
        "Cliente API-Football real no implementado; usá use_mock=true"
    )


def handler(event: dict, context) -> dict:
    os.environ.setdefault(
        "DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev")
    )
    from src.services.result_poller_service import ResultPollerService

    client = _build_client(event)
    svc = ResultPollerService(api_client=client)
    trigger = event.get("trigger", "scheduled")
    dry_run = bool(event.get("dry_run"))

    if trigger == "fixture":
        api_id = event.get("api_match_id")
        if api_id is None:
            return {"status": "ERROR", "error": "api_match_id required"}
        out = svc.poll_once(api_match_ids=[int(api_id)], dry_run=dry_run)
    else:
        out = svc.poll_once(dry_run=dry_run)

    return {"status": "OK", "trigger": trigger, "dry_run": dry_run, **out}
