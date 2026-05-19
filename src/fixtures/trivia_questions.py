"""Banco de preguntas verificadas — fallback si KB/web no alcanzan."""
from __future__ import annotations

FALLBACK_QUESTIONS: list[dict] = [
    {
        "topic": "mundiales",
        "level": "BASIC",
        "question": "¿En qué país se jugó el Mundial 1986 donde Maradona marcó el 'Gol del Siglo'?",
        "options": {"A": "Argentina", "B": "México", "C": "España", "D": "Italia"},
        "correct": "B",
        "explanation": "El Mundial 1986 se disputó en México; Argentina fue campeón.",
        "source": "manual",
    },
    {
        "topic": "records",
        "level": "EXPERT",
        "question": "¿Quién es el máximo goleador en la historia de los Mundiales FIFA?",
        "options": {
            "A": "Pelé",
            "B": "Ronaldo Nazário",
            "C": "Miroslav Klose",
            "D": "Just Fontaine",
        },
        "correct": "C",
        "explanation": "Miroslav Klose anotó 16 goles en Mundiales con Alemania.",
        "source": "manual",
    },
    {
        "topic": "jugadores",
        "level": "MEDIUM",
        "question": "¿Cuántas Copas del Mundo ganó Brasil hasta 2022?",
        "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
        "correct": "C",
        "explanation": "Brasil tiene 5 títulos mundiales (1958, 1962, 1970, 1994, 2002).",
        "source": "manual",
    },
    {
        "topic": "historias_mundiales",
        "level": "MEDIUM",
        "question": (
            "En el Mundial 1990, ¿qué selección eliminó a Inglaterra en semifinales "
            "con los penales de Schillaci y Aldo Serena?"
        ),
        "options": {"A": "Alemania", "B": "Italia", "C": "Argentina", "D": "Brasil"},
        "correct": "B",
        "explanation": "Italia venció a Inglaterra 2-1 en Turín y llegó a la final en casa.",
        "source": "manual",
    },
    {
        "topic": "historias_mundiales",
        "level": "MEDIUM",
        "question": (
            "¿En qué Mundial se popularizó el 'Gol del Siglo' y la 'Mano de Dios' "
            "de Diego Maradona en el mismo partido?"
        ),
        "options": {"A": "1982", "B": "1986", "C": "1990", "D": "1994"},
        "correct": "B",
        "explanation": "Fue en México 1986, cuartos de final Argentina vs Inglaterra.",
        "source": "manual",
    },
    {
        "topic": "historias_mundiales",
        "level": "EXPERT",
        "question": (
            "¿Qué país organizó el primer Mundial con 32 equipos, en 1998, "
            "donde Zidane brilló en la final?"
        ),
        "options": {"A": "Alemania", "B": "Francia", "C": "Japón", "D": "Sudáfrica"},
        "correct": "B",
        "explanation": "Francia 1998 fue el primer torneo de 32 selecciones; Francia ganó 3-0 a Brasil.",
        "source": "manual",
    },
]
