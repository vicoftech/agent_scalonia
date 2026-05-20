"""Secciones de system prompt sin imports de servicios pesados (SPEC-2026-027)."""

TRIVIA_SECTION = """
## Trivias (SPEC-025)
- /trivia o trivia_tool action=play: una ronda (máx 5/día). Opciones A/B/C/D solo vía botones en Telegram.
- action=answer con session_id o trivia_id + answer A|B|C|D.
- Trivia diaria general (historias de mundiales): ~10:00 Argentina o 2 h antes del primer partido del día; el usuario la ve al escribir al bot.
- Sin penalización por error. Puntos: Básico +1, Intermedio +3, Experto +5.
- Generación: usá contexto KB/web; trivia_tool play elige nivel según football_knowledge del perfil.
""".strip()
