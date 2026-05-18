"""tests/unit/test_kb — SPEC-2026-023 SC-01 a SC-07."""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DYNAMODB_TABLE", "ProdeTable-test")

from src.kb.enrichment_queue import enqueue_enrichment
from src.kb.kb_enrichment_service import (
    DataType,
    KBEnrichmentService,
    classify_query,
    make_slug,
)


class TestClassifyQuery:
    def test_sc03_volatile_resultado_ayer(self):
        assert classify_query("resultado Argentina anoche") == DataType.VOLATILE

    def test_sc02_historical_senegal(self):
        q = "historia de la selección de Senegal en el mundial 2002"
        assert classify_query(q) == DataType.HISTORICAL

    def test_sc06_messi_ambiguous_short(self):
        assert classify_query("Messi") == DataType.AMBIGUOUS

    def test_volatile_wins_over_historical(self):
        q = "resultado mundial 1986 ayer en vivo"
        assert classify_query(q) == DataType.VOLATILE


class TestKBEnrichmentService:
    def test_sc05_dedup_skips_s3_puts_cache(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"partition_key": "KB_ENRICHED#x.md"}}
        mock_s3 = MagicMock()
        svc = KBEnrichmentService(
            kb_bucket="bucket-test",
            dynamodb_table=mock_table,
            s3_client=mock_s3,
        )
        with patch.object(svc, "_enrich_cache") as mock_cache:
            svc.enrich_from_web(
                "historia senegal mundiales",
                "x" * 100,
                DataType.HISTORICAL,
            )
        mock_s3.put_object.assert_not_called()
        mock_cache.assert_called_once()

    def test_sc02_historical_uploads_s3(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_s3 = MagicMock()
        svc = KBEnrichmentService(
            kb_bucket="bucket-test",
            dynamodb_table=mock_table,
            s3_client=mock_s3,
        )
        query = "historia de Senegal en el mundial 1974"
        svc.enrich_from_web(query, "contenido web " * 20, DataType.HISTORICAL)
        mock_s3.put_object.assert_called_once()
        key = mock_s3.put_object.call_args.kwargs["Key"]
        assert key.startswith("enriched/")
        assert key.endswith(".md")
        mock_table.put_item.assert_called()

    def test_should_enrich_false_when_kb_sufficient(self):
        svc = KBEnrichmentService(kb_bucket="b", dynamodb_table=MagicMock())
        assert not svc.should_enrich("q", "x" * 250, "web")

    def test_make_slug_safe(self):
        assert make_slug('¿Historia "Mundial" 1974?').endswith(".md")


class TestEnqueueEnrichment:
    def test_sc07_sqs_fire_and_forget(self, monkeypatch):
        sent = {}

        class FakeSqs:
            def send_message(self, **kw):
                sent.update(kw)

        monkeypatch.setenv("KB_ENRICHMENT_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/q")
        monkeypatch.setattr("src.kb.enrichment_queue.boto3.client", lambda s: FakeSqs())
        enqueue_enrichment(
            "historia del mundial 1974 alemania occidente",
            "web",
            DataType.HISTORICAL,
        )
        assert "MessageBody" in sent

    def test_thread_fallback_without_queue(self, monkeypatch):
        monkeypatch.delenv("KB_ENRICHMENT_QUEUE_URL", raising=False)
        called = []

        def fake_dispatch(q, w, t):
            called.append((q, t))

        monkeypatch.setattr(
            "src.kb.enrichment_queue._dispatch_fn",
            fake_dispatch,
        )
        enqueue_enrichment(
            "historia del mundial 1974 alemania occidente",
            "web " * 30,
            DataType.HISTORICAL,
        )
        import time

        time.sleep(0.2)
        assert called


class TestKbRetrievalIntegration:
    def test_sc01_kb_hit_no_web(self, monkeypatch):
        from agent.tools import kb_retrieval_tool as krt

        long_content = "Maradona " * 40
        rows = [{"source_path": "x.md", "content": long_content}]
        with patch("src.kb.lambda_client.search_kb", return_value=rows):
            with patch("agent.tools.web_search_tool.perform_web_search") as mock_web:
                with patch(
                    "agent.tools.kb_retrieval_tool.enqueue_enrichment"
                ) as mock_eq:
                    out = krt.kb_retrieval_tool("goles Maradona Mundial 1986")
        assert long_content.strip() in out
        mock_web.assert_not_called()
        mock_eq.assert_not_called()

    def test_kb_miss_enqueues_and_returns_web(self, monkeypatch):
        from agent.tools import kb_retrieval_tool as krt

        monkeypatch.setenv("DYNAMODB_TABLE", "ProdeTable-test")
        with patch("src.kb.lambda_client.search_kb", return_value=[]):
            with patch(
                "agent.tools.web_search_tool.perform_web_search",
                return_value="Historia de Senegal en mundiales " * 5,
            ):
                with patch(
                    "agent.tools.kb_retrieval_tool.enqueue_enrichment"
                ) as mock_eq:
                    out = krt.kb_retrieval_tool(
                        "historia de Senegal en el mundial FIFA 2002"
                    )
        assert "Senegal" in out
        mock_eq.assert_called_once()
        assert mock_eq.call_args[0][2] == DataType.HISTORICAL
