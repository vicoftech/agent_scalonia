"""GET /news/r/{news_id} — redirect + READ — SPEC-2026-046."""
from __future__ import annotations

import logging
import os
logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    os.environ.setdefault("DYNAMODB_TABLE", os.environ.get("DYNAMODB_TABLE", "ProdeTable-dev"))

    path = event.get("rawPath") or event.get("path") or ""
    parts = [p for p in path.split("/") if p]
    news_id = ""
    if len(parts) >= 3 and parts[0] == "news" and parts[1] == "r":
        news_id = parts[2]
    params = event.get("queryStringParameters") or {}
    token = (params.get("t") or "").strip()

    from src.dao.dynamo.news_dao import NewsDAO
    from src.services.news_read_token import decode_read_token
    from src.services.world_cup_news_service import WorldCupNewsService

    item = NewsDAO().get_details(news_id) if news_id else None
    if not item:
        return _response(404, "Noticia no encontrada")

    user_id = decode_read_token(token, news_id) if token else None
    if user_id:
        WorldCupNewsService().record_read(user_id, news_id)

    article_url = (item.get("article_url") or "").strip()
    if not article_url:
        return _response(404, "Sin URL de artículo")

    return {
        "statusCode": 302,
        "headers": {
            "Location": article_url,
            "Cache-Control": "no-store",
        },
        "body": "",
    }


def _response(code: int, message: str) -> dict:
    return {
        "statusCode": code,
        "headers": {"Content-Type": "text/plain; charset=utf-8"},
        "body": message,
    }
