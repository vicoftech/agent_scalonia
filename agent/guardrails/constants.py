"""SPEC-2026-015 — mensajes fijos y sección de system prompt."""

OUT_OF_SCOPE_BLOCKED_INPUT = "\n".join([
    "Soy el asistente del Prode Mundial 2026 ⚽",
    "Solo puedo ayudarte con temas de fútbol y mundiales.",
    "¿Tenés alguna pregunta sobre el Mundial 2026?",
])

OUT_OF_SCOPE_BLOCKED_OUTPUT = "\n".join([
    "Solo puedo responder sobre fútbol y mundiales.",
    "¿En qué puedo ayudarte sobre el Mundial 2026?",
])

OUT_OF_SCOPE_LLM_REPLY = "\n".join([
    "Soy el asistente del Prode Mundial 2026 ⚽",
    "Solo puedo ayudarte con temas de fútbol y mundiales.",
    "¿Tenés alguna pregunta sobre el Mundial 2026, la historia de los mundiales,",
    "o querés conocer las reglas del juego?",
])

GUARDRAIL_SECTION = """
## Alcance (importante)

SIEMPRE EN SCOPE — usá kb_retrieval_tool y/o web_search_tool; NO rechaces:
- Jugadores (Messi, Ronaldo, Maradona, Haaland, etc.) y sus estadísticas o comparativas
- Selecciones, clubes, ligas, Champions, mundiales, finales, historia y reglas del fútbol
- Preguntas con "mejor/peor", goles, asistencias, records, trayectoria en copas del mundo

PROHIBIDO responder "Solo puedo responder sobre fútbol y mundiales" si la pregunta trata de fútbol o jugadores.

Fuera de scope (rechazá solo si es claramente otro tema):
- Política, economía, medicina general, programación, otros deportes (tenis, F1, básquet…)
""".strip()
