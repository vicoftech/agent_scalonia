"""Formato unificado de respuestas IA para Telegram."""
from src.services.ai_telegram_format import (
    AI_RESPONSE_FORMAT_PROMPT,
    format_ai_telegram_response,
    format_prediction_analysis,
)


def test_format_prompt_present():
    assert "párrafos" in AI_RESPONSE_FORMAT_PROMPT.lower()


def test_format_paragraphs_and_bold_html():
    raw = "## Historia\n\nMessi ganó el **Mundial 2022**.\n\nFue en Qatar."
    out = format_ai_telegram_response(raw, mode="html")
    assert "<b>" in out
    assert "Messi" in out
    assert "\n\n" in out


def test_format_table_html():
    raw = "| Equipo | Pts |\n| --- | --- |\n| ARG | 9 |\n| MEX | 6 |"
    out = format_ai_telegram_response(raw, mode="html")
    assert "<pre>" in out
    assert "ARG" in out


def test_format_skips_short_system_message():
    raw = "No pude generar una respuesta. No se descontó una consulta."
    out = format_ai_telegram_response(raw, mode="html")
    assert "<b>" not in out
    assert "No pude generar" in out


def test_format_credits_footer_html():
    raw = "Respuesta del agente.\n\nConsultas restantes: 3"
    out = format_ai_telegram_response(raw, mode="html")
    assert "Consultas restantes" in out
    assert "3" in out


def test_format_prediction_analysis_plain():
    brief = {
        "ia_prediction_line": "Dado el análisis previo me inclino por México como ganador del partido.",
        "home_team": "MEX",
        "away_team": "RSA",
        "home_strengths": ["Ataque vertical"],
        "home_weaknesses": ["Aéreos"],
        "away_strengths": ["Transiciones"],
        "away_weaknesses": [],
    }
    out = format_prediction_analysis(brief, mode="plain")
    assert "Contexto IA" in out
    assert "México" in out or "MEX" in out
    assert "💪" in out or "Fortalezas" in out
    assert "Análisis informativo" in out
