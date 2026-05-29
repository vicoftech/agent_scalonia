"""Prompts BRIEF_GENERATION para AgentCore (SPEC-2026-045)."""
from __future__ import annotations

from typing import Any

from src.services.team_flags import resolve_team_display_name


def team_brief_prompt(team_code: str) -> str:
    name = resolve_team_display_name(team_code)
    return f"""[BRIEF_GENERATION]
Modo: generación de brief diario de selección (SPEC-2026-045).
Equipo: {name} ({team_code}).

INSTRUCCIONES:
1. Usá kb_retrieval_tool PRIMERO con query: "{name} selección Mundial 2026 DT táctica plantel {team_code}" (max_results=8 si hace falta nómina).
2. Complementá con web_search_tool (priorizar site:fifa.com para plantel/lesiones; si no hay hits, ampliá a federaciones y medios deportivos).
3. Respondé ÚNICAMENTE con un objeto JSON válido (sin markdown fuera del JSON), con este schema:
{{
  "team_code": "{team_code}",
  "brief_markdown": "markdown con las 7 secciones del informe (máx ~2500 caracteres)",
  "brief_sections": {{"dt":"","path_to_world_cup":"","recent_record":"","best_players":"","tactics":"","leagues_presence":"","last_match":""}},
  "roster": [{{"name":"","position":"FW","club":"","league":"","status":"DISPONIBLE|LESIONADO|SUSPENDIDO","status_note":"","source":"kb|fifa.com|web_other"}}],
  "recent_record": "15G-3E-2P",
  "kb_chunks_used": 0,
  "web_queries_used": ["..."]
}}

Reglas:
- Español rioplatense neutro, sin marcador exacto de partidos futuros.
- Nómina: 18-26 jugadores si hay datos; si no, figuras confirmadas y roster_completeness PARTIAL.
- No inventes jugadores no citados en KB/web.
- brief_markdown debe incluir encabezado ## {name} ({team_code}) y secciones 1-7 + tabla Nómina.
"""


def match_brief_prompt(
    match: dict[str, Any],
    home_brief: dict[str, Any],
    away_brief: dict[str, Any],
) -> str:
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    home_name = resolve_team_display_name(home)
    away_name = resolve_team_display_name(away)
    match_id = match.get("match_id", "")
    return f"""[BRIEF_GENERATION]
Modo: brief de partido previo (SPEC-2026-045).
Partido: {home_name} vs {away_name} (match_id={match_id}, #{match.get('match_number')}, grupo {match.get('group_letter')}).

Contexto — brief {home}:
{(home_brief.get('brief_markdown') or '')[:3500]}

Contexto — brief {away}:
{(away_brief.get('brief_markdown') or '')[:3500]}

Respondé ÚNICAMENTE JSON válido:
{{
  "match_id": "{match_id}",
  "home_strengths": ["..."],
  "home_weaknesses": ["..."],
  "away_strengths": ["..."],
  "away_weaknesses": ["..."],
  "ia_prediction_line": "Dado el análisis previo me inclino por <NOMBRE COMPLETO> como ganador del partido.",
  "ia_prediction_rationale": "2-4 oraciones",
  "brief_markdown": "markdown completo con secciones y bloque 🤖 IA Prediction"
}}

Reglas:
- PROHIBIDO marcador exacto (ej. 2-1) o cuotas.
- ia_prediction_line debe empezar exactamente con: Dado el análisis previo me inclino por
- Favorito: nombre completo del equipo o EMPATE técnico si equilibrado.
"""
