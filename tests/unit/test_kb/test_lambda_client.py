"""KB Lambda client defaults."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from src.kb import lambda_client


def test_kb_query_function_name_default(monkeypatch):
    monkeypatch.delenv("KB_QUERY_LAMBDA_NAME", raising=False)
    monkeypatch.setenv("ENV", "dev")
    assert lambda_client._kb_query_function_name() == "prode-mundial-kb-query-dev"


def test_search_kb_uses_get_session(monkeypatch):
    monkeypatch.setenv("KB_QUERY_LAMBDA_NAME", "my-kb-fn")
    mock_lam = MagicMock()
    mock_lam.invoke.return_value = {
        "Payload": MagicMock(read=lambda: b'{"chunks":[{"content":"x"}]}'),
    }
    mock_session = MagicMock()
    mock_session.client.return_value = mock_lam
    with patch("src.dao.dynamo.table.get_session", return_value=mock_session):
        rows = lambda_client.search_kb("México mundial 2026", limit=3)
    assert len(rows) == 1
    mock_session.client.assert_called_with("lambda")
    mock_lam.invoke.assert_called_once()
