"""Detección y saneo de resultados web (scrapes ruidosos, planteles)."""
from __future__ import annotations

import re

_TRANSFERMARKT_MARKERS = (
    "transfermarkt",
    "mill. €",
    "mill.€",
    "valor de mercado",
)

_MESSY_SCRAPE_RES = [
    re.compile(r"\[\.\.\.\]"),
    re.compile(r"\b\d+\s+---\s+"),
    re.compile(r"---\s+[A-ZÁÉÍÓÚÑ]"),
    re.compile(r"\bmill\.\s*€", re.I),
    re.compile(r"valor de mercado", re.I),
]

_PLAYER_POSITION_RE = re.compile(
    r"(?i)(.+?)\s+("
    r"Portero|Arquero|Pivote|Mediocentro(?:\s+ofensivo)?|"
    r"Defensa central|Lateral izquierdo|Lateral derecho|"
    r"Extremo izquierdo|Extremo derecho|Delantero centro"
    r")\s*(?:\d+\s+)?(?:[\d.,]+\s*(?:mill\.\s*)?€)?"
)

_NAME_TOKEN_RE = re.compile(
    r"([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)+)"
)

_POSITION_GROUPS: dict[str, str] = {
    "portero": "Arqueros",
    "arquero": "Arqueros",
    "defensa central": "Defensores",
    "lateral izquierdo": "Defensores",
    "lateral derecho": "Defensores",
    "pivote": "Mediocampistas",
    "mediocentro": "Mediocampistas",
    "mediocentro ofensivo": "Mediocampistas",
    "extremo izquierdo": "Mediocampistas",
    "extremo derecho": "Mediocampistas",
    "delantero centro": "Delanteros",
}


def is_messy_web_scrape(text: str) -> bool:
    """HTML/tablas rotas de sitios como Transfermarkt — no aptas para respuesta directa."""
    body = (text or "").strip()
    if len(body) < 120:
        return False
    lower = body.lower()
    hits = sum(1 for pat in _MESSY_SCRAPE_RES if pat.search(body))
    if hits >= 2:
        return True
    if any(m in lower for m in _TRANSFERMARKT_MARKERS) and hits >= 1:
        return True
    dash_lines = sum(1 for ln in body.splitlines() if "---" in ln)
    if dash_lines >= 3 and any(m in lower for m in _TRANSFERMARKT_MARKERS):
        return True
    return False


def _position_group(position: str) -> str:
    key = (position or "").strip().lower()
    return _POSITION_GROUPS.get(key, "Jugadores")


def _normalize_duplicate_name(name: str) -> str:
    words = name.split()
    if len(words) >= 4 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half])
    return name.strip()


def _extract_player_name(raw_prefix: str) -> str | None:
    text = re.sub(r"^\d+\s+", "", (raw_prefix or "").strip())
    text = re.sub(r"\s+---.*", "", text).strip()
    chunks = [c.strip() for c in re.split(r"\s{2,}", text) if c.strip()]
    for chunk in chunks:
        m = re.match(
            r"^([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)+)",
            chunk,
        )
        if m:
            return _normalize_duplicate_name(m.group(1))
    names = _NAME_TOKEN_RE.findall(text)
    if not names:
        return None
    cleaned = [_normalize_duplicate_name(re.sub(r"^\d+\s+", "", n).strip()) for n in names]
    cleaned = [n for n in cleaned if len(n) > 4]
    if not cleaned:
        return None
    return max(cleaned, key=len)


def extract_players_from_scrape(text: str) -> dict[str, list[str]]:
    """Agrupa jugadores por rol a partir de texto web ruidoso."""
    groups: dict[str, list[str]] = {}
    seen: set[str] = set()
    for line in (text or "").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = _PLAYER_POSITION_RE.search(line)
        if not m:
            continue
        name = _extract_player_name(m.group(1))
        if not name or name in seen:
            continue
        seen.add(name)
        group = _position_group(m.group(2))
        groups.setdefault(group, []).append(name)
    return groups


def format_squad_scrape_markdown(text: str, *, team_label: str | None = None) -> str | None:
    """Convierte scrape ruidoso en markdown legible para Telegram."""
    players = extract_players_from_scrape(text)
    if len(players) < 2:
        return None
    total = sum(len(v) for v in players.values())
    if total < 5:
        return None

    title = team_label or "Plantel"
    if "transfermarkt" in (text or "").lower():
        title = f"{title} (referencia web)"

    sections = [f"## 👥 {title}"]
    order = ("Arqueros", "Defensores", "Mediocampistas", "Delanteros", "Jugadores")
    for group in order:
        names = players.get(group) or []
        if not names:
            continue
        sections.append(f"### {group}")
        sections.extend(f"- {n}" for n in names[:12])
    sections.append(f"_Total detectado: {total} jugadores._")
    return "\n\n".join(sections)
