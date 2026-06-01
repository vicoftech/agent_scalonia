"""Ask IA — prefetch KB/web."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.kb.resolve import KbWebResolveResult
from src.services.ask_ia_knowledge import prepare_ask_ia_turn, try_direct_knowledge_reply


@patch.dict("os.environ", {"KB_QUERY_LAMBDA_NAME": "prode-kb-query-dev"})
@patch("src.kb.resolve.resolve_kb_then_web")
def test_prepare_includes_web_context_in_agent_prompt(mock_resolve):
    mock_resolve.return_value = KbWebResolveResult(
        kb_text="KB snippet",
        web_text="Web sobre el primer gol de Laurent en 1930.",
        kb_chunk_count=1,
        kb_max_score=0.5,
        web_fallback_used=True,
        tavily_configured=True,
    )
    prep = prepare_ask_ia_turn("¿Quién hizo el primer gol en un mundial?")
    assert prep.direct_reply is None
    assert prep.agent_prompt is not None
    assert "NO invoques herramientas" in prep.agent_prompt
    assert "Web sobre el primer gol" in prep.agent_prompt
    assert "KB snippet" in prep.agent_prompt


@patch.dict("os.environ", {"KB_QUERY_LAMBDA_NAME": "prode-kb-query-dev"})
@patch("src.kb.resolve.format_kb_web_miss_message", return_value="No encontré información suficiente.")
@patch("src.kb.resolve.resolve_kb_then_web")
def test_prepare_miss_returns_direct_message(mock_resolve, _miss):
    mock_resolve.return_value = KbWebResolveResult(
        kb_text="",
        web_text=None,
        kb_chunk_count=0,
        kb_max_score=0.0,
        web_fallback_used=False,
        tavily_configured=True,
    )
    with patch("src.kb.domain.is_football_domain_query", return_value=True):
        prep = prepare_ask_ia_turn("tema muy raro xyz abc historia mundial")
    assert prep.direct_reply == "No encontré información suficiente."
    assert prep.agent_prompt is None


@patch.dict("os.environ", {"KB_QUERY_LAMBDA_NAME": "prode-kb-query-dev"})
@patch("src.kb.resolve.resolve_kb_then_web")
@patch("src.kb.resolve.kb_is_sufficient", return_value=True)
@patch("src.kb.resolve._is_usable_web_result", return_value=False)
def test_direct_reply_from_kb_only(mock_web, mock_suff, mock_resolve):
    mock_resolve.return_value = KbWebResolveResult(
        kb_text=(
            "El primer gol en la historia de los Mundiales fue anotado por Lucien Laurent "
            "de Francia, el 13 de julio de 1930, en el partido Francia vs México en Uruguay. "
            "Fue el gol número 1 del torneo inaugural."
        ),
        web_text=None,
        kb_chunk_count=2,
        kb_max_score=0.9,
        web_fallback_used=False,
        tavily_configured=True,
    )
    with (
        patch("src.kb.domain.is_football_domain_query", return_value=True),
        patch("src.services.match_query_intent.is_match_fixture_query", return_value=False),
        patch("src.kb.query_intent.is_analytical_query", return_value=False),
        patch("src.services.prediction_score_parse.looks_like_simple_score", return_value=False),
    ):
        out = try_direct_knowledge_reply("primer gol mundial historia")
    assert out is not None
    assert "Laurent" in out or "Knowledge Base" in out


@patch.dict("os.environ", {"KB_QUERY_LAMBDA_NAME": "prode-kb-query-dev"})
@patch("src.kb.resolve.resolve_kb_then_web")
def test_direct_reply_squad_prefers_kb_over_messy_web(mock_resolve):
    kb = (
        "### Uruguay (URU)\n\n#### Arqueros\n- Sergio Rochet\n- Fernando Muslera\n\n"
        "#### Delanteros\n- Darwin Núñez\n"
    )
    web = "Uruguay Transfermarkt\n18 --- Brian Rodríguez Extremo izquierdo 26 8,00 mill. €"
    mock_resolve.return_value = KbWebResolveResult(
        kb_text=kb,
        web_text=web,
        kb_chunk_count=1,
        kb_max_score=0.4,
        web_fallback_used=True,
        tavily_configured=True,
    )
    with (
        patch("src.kb.domain.is_football_domain_query", return_value=True),
        patch("src.services.match_query_intent.is_match_fixture_query", return_value=False),
        patch("src.kb.query_intent.is_analytical_query", return_value=False),
        patch("src.services.prediction_score_parse.looks_like_simple_score", return_value=False),
        patch("src.kb.resolve._is_usable_web_result", return_value=True),
    ):
        out = try_direct_knowledge_reply("selección de uruguay plantel")
    assert out is not None
    assert "Knowledge Base" in out
    assert "Sergio Rochet" in out
    assert "Transfermarkt" not in out


@patch.dict("os.environ", {"KB_QUERY_LAMBDA_NAME": "prode-kb-query-dev"})
@patch("src.kb.resolve.resolve_kb_then_web")
def test_direct_reply_skips_messy_web_only(mock_resolve):
    web = (
        "Uruguay - Plantilla Transfermarkt\n"
        "18 --- Brian Rodríguez Brian Rodríguez Extremo izquierdo 26 8,00 mill. €\n"
        "15 --- Federico Valverde Federico Valverde Mediocentro 27 120,00 mill. €\n"
        "1 --- Sergio Rochet Sergio Rochet Portero 33 1,80 mill. €\n"
        "4 --- Ronald Araujo Ronald Araujo Defensa central 27 20,00 mill. €\n"
        "9 --- Darwin Núñez Darwin Núñez Delantero centro 26 25,00 mill. €\n"
        "# Jugadores Edad Club Valor de mercado\n"
    )
    mock_resolve.return_value = KbWebResolveResult(
        kb_text="",
        web_text=web,
        kb_chunk_count=0,
        kb_max_score=0.0,
        web_fallback_used=True,
        tavily_configured=True,
    )
    with (
        patch("src.kb.domain.is_football_domain_query", return_value=True),
        patch("src.services.match_query_intent.is_match_fixture_query", return_value=False),
        patch("src.kb.query_intent.is_analytical_query", return_value=False),
        patch("src.services.prediction_score_parse.looks_like_simple_score", return_value=False),
        patch("src.kb.resolve._is_usable_web_result", return_value=True),
    ):
        out = try_direct_knowledge_reply("plantel uruguay")
    assert out is None
