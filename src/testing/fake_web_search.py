"""Fake web_search para probar result collector / poller sin Tavily."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "data/fixtures/mock_web_search_results.json"
)


def load_web_search_fixture(path: Path | str | None = None) -> dict[str, str]:
    p = Path(path) if path else DEFAULT_FIXTURE
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"fixture inválido: {p}")
    return {str(k).upper(): str(v) for k, v in data.items()}


def _teams_from_key(key: str) -> tuple[str, str]:
    parts = str(key).upper().replace("-", "_").split("_")
    if len(parts) < 2:
        return (), ()
    return parts[0], parts[1]


def build_fake_web_search_fn(
    *,
    fixture: dict[str, str] | None = None,
    fixture_path: Path | str | None = None,
    default_response: str | None = None,
) -> Callable[[str], Optional[str]]:
    """
    Devuelve texto fijo según equipos en la query (ej. MEX y RSA en la pregunta).
    """
    responses = fixture if fixture is not None else load_web_search_fixture(fixture_path)

    def search(query: str) -> Optional[str]:
        q = query.upper()
        for key, text in responses.items():
            home, away = _teams_from_key(key)
            if home and away and home in q and away in q:
                logger.debug("fake_web_search hit key=%s", key)
                return text
        if default_response is not None:
            logger.debug("fake_web_search default for query=%s", query[:60])
            return default_response
        logger.warning("fake_web_search miss query=%s", query[:80])
        return None

    return search


def install_fake_web_search(
    *,
    fixture_path: Path | str | None = None,
    default_response: str | None = None,
) -> Callable[[str], Optional[str]]:
    """Registra el fake en ResultService (set_web_search_fn)."""
    from src.services.result_service import set_web_search_fn

    fn = build_fake_web_search_fn(
        fixture_path=fixture_path,
        default_response=default_response,
    )
    set_web_search_fn(fn)
    return fn
