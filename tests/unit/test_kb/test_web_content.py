"""Tests web scrape / plantel."""
from src.kb.query_intent import is_squad_roster_query
from src.kb.web_content import (
    extract_players_from_scrape,
    format_squad_scrape_markdown,
    is_messy_web_scrape,
)
from src.services.ai_telegram_format import format_ai_telegram_response

TRANSFERMARKT_SAMPLE = """
Uruguay - Plantilla detallada 2026  Transfermarkt
18                                                        ---                               Brian Rodríguez         Brian Rodríguez           Extremo izquierdo                    26  8,00 mill. €
21                                                        ---                               Facundo Torres          Facundo Torres            Extremo derecho                      26  10,00 mill. €
5                         ---                 Manuel Ugarte  Manuel Ugarte    Pivote    25  30,00 mill. €
15                                                        ---                               Federico Valverde       Federico Valverde         Mediocentro                          27  120,00 mill. €
12                                                        ---                               Santiago Mele           Santiago Mele             Portero                              28  2,00 mill. €
1                                                         ---                               Sergio Rochet           Sergio Rochet             Portero                              33  1,80 mill. €
4                                                         ---                               Ronald Araujo           Ronald Araujo             Defensa central                      27  20,00 mill. €
9                                                         ---                               Darwin Núñez            Darwin Núñez              Delantero centro                     26  25,00 mill. €
#  Jugadores  Edad  Club  Valor de mercado
"""


def test_is_squad_roster_query():
    assert is_squad_roster_query("selección de uruguay")
    assert is_squad_roster_query("plantel uruguay mundial 2026")
    assert not is_squad_roster_query("primer gol mundial")


def test_messy_transfermarkt_detected():
    assert is_messy_web_scrape(TRANSFERMARKT_SAMPLE)


def test_extract_players_from_transfermarkt():
    groups = extract_players_from_scrape(TRANSFERMARKT_SAMPLE)
    assert "Arqueros" in groups
    assert "Sergio Rochet" in groups["Arqueros"]
    assert "Federico Valverde" in groups["Mediocampistas"]
    assert "Darwin Núñez" in groups["Delanteros"]


def test_format_squad_scrape_markdown():
    md = format_squad_scrape_markdown(TRANSFERMARKT_SAMPLE, team_label="🇺🇾 Uruguay")
    assert md is not None
    assert "Arqueros" in md
    assert "Sergio Rochet" in md
    assert "<pre>" not in md


def test_format_transfermarkt_web_reply_no_pre():
    import os

    os.environ["AI_FORMAT_BEDROCK"] = "false"
    raw = (
        "🌐 Información verificada (búsqueda web):\n\n"
        f"{TRANSFERMARKT_SAMPLE}\n\nConsultas restantes: 4"
    )
    out = format_ai_telegram_response(raw, mode="html", variant="kb_direct")
    assert "<pre>" not in out
    assert "Sergio Rochet" in out or "Valverde" in out
    assert "▫️" in out or "Arqueros" in out
