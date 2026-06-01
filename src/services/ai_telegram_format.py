"""Formato consistente de respuestas IA para Telegram — Ask IA y análisis de predicciones."""
from __future__ import annotations

import html
import re
from typing import Any, Literal

OutputMode = Literal["html", "plain"]

MAX_TG_MESSAGE = 4096

AI_RESPONSE_FORMAT_PROMPT = (
    "[Formato Telegram — obligatorio]\n"
    "- Separá ideas en párrafos (línea en blanco entre bloques).\n"
    "- Usá títulos cortos con ## o **negrita** para lo importante.\n"
    "- Listas con viñetas (- o •); tablas con columnas | si comparás datos.\n"
    "- Emojis solo al inicio de títulos o bullets (⚽ 🏆 📊 👥 🎯).\n"
    "- Español rioplatense, claro y escaneable."
)

_SYSTEM_SKIP_MARKERS = (
    "Comando no válido",
    "No pude iniciar",
    "No pude generar",
    "No se descontó",
    "Hubo un error",
    "El agente no está",
    "⛔ Usaste todas",
    "Sesión de IA cerrada",
    "Escribí tu siguiente pregunta",
    "Tenés ",
    " consultas disponibles",
    "Transferí $",
    "Para enviar un comprobante",
)

_SECTION_EMOJI: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"fortaleza", re.I), "💪"),
    (re.compile(r"debilidad|weakness", re.I), "⚠️"),
    (re.compile(r"predicci|prediction|inclino por", re.I), "🎯"),
    (re.compile(r"análisis|analisis|contexto ia", re.I), "📊"),
    (re.compile(r"plantel|nómina|nomina|jugador", re.I), "👥"),
    (re.compile(r"historia|récord|record", re.I), "📜"),
    (re.compile(r"resultado|marcador", re.I), "🏁"),
    (re.compile(r"grupo|fixture|partido", re.I), "⚽"),
    (re.compile(r"web|knowledge base|kb", re.I), "🌐"),
]

_HEADER_RE = re.compile(r"^#{1,3}\s+(.+)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_MD_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_LIST_RE = re.compile(r"^(\s*)([-•*]|\d+[.)])\s+")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")
_CREDITS_FOOTER_RE = re.compile(
    r"\n\nConsultas restantes:\s*\d+\s*$",
    re.I,
)


def escape_html(text: str) -> str:
    return html.escape(text or "", quote=False)


def _section_emoji(title: str) -> str:
    for pattern, emoji in _SECTION_EMOJI:
        if pattern.search(title):
            return emoji
    return "📌"


def _should_light_format(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if len(stripped) < 220 and any(m in stripped for m in _SYSTEM_SKIP_MARKERS):
        return True
    return False


def _split_blocks(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return []
    parts = re.split(r"\n\s*\n", normalized)
    return [p.strip() for p in parts if p.strip()]


def _is_table_block(block: str) -> bool:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    pipe_lines = sum(1 for ln in lines if "|" in ln)
    return pipe_lines >= 2 and (pipe_lines / len(lines)) >= 0.5


def _parse_table_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or _TABLE_SEP_RE.match(stripped):
            continue
        if "|" not in stripped:
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells:
            rows.append(cells)
    return rows


def _format_table(rows: list[list[str]], *, mode: OutputMode) -> str:
    if not rows:
        return ""
    col_count = max(len(r) for r in rows)
    widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                widths[i] = max(widths[i], len(cell))

    def _pad_row(row: list[str]) -> str:
        padded = []
        for i in range(col_count):
            cell = row[i] if i < len(row) else ""
            padded.append(cell.ljust(widths[i]))
        return "  ".join(padded).rstrip()

    grid_lines = [_pad_row(row) for row in rows]
    if mode == "html":
        body = "\n".join(escape_html(line) for line in grid_lines)
        return f"<pre>{body}</pre>"
    return "\n".join(grid_lines)


def _inline_to_html(text: str) -> str:
    out = escape_html(text)
    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    out = _ITALIC_MD_RE.sub(r"<i>\1</i>", out)
    return out


def _inline_to_plain(text: str) -> str:
    out = _BOLD_RE.sub(r"\1", text)
    out = _ITALIC_MD_RE.sub(r"\1", out)
    out = re.sub(r"^#{1,3}\s+", "", out, flags=re.M)
    return out.strip()


def _format_header(title: str, *, mode: OutputMode) -> str:
    clean = _inline_to_plain(title)
    emoji = _section_emoji(clean)
    if mode == "html":
        return f"<b>{emoji} {_inline_to_html(clean)}</b>"
    return f"{emoji} {clean}"


def _format_list_block(block: str, *, mode: OutputMode) -> str:
    lines = block.splitlines()
    formatted: list[str] = []
    for line in lines:
        m = _LIST_RE.match(line)
        if not m:
            formatted.append(_inline_to_html(line) if mode == "html" else _inline_to_plain(line))
            continue
        item = line[m.end() :].strip()
        bullet = "▫️"
        if mode == "html":
            formatted.append(f"{bullet} {_inline_to_html(item)}")
        else:
            formatted.append(f"• {_inline_to_plain(item)}")
    return "\n".join(formatted)


def _format_block(block: str, *, mode: OutputMode) -> str:
    if _is_table_block(block):
        return _format_table(_parse_table_rows(block), mode=mode)

    lines = block.splitlines()
    first = lines[0].strip()
    header_match = _HEADER_RE.match(first)
    if header_match:
        header = _format_header(header_match.group(1), mode=mode)
        rest = "\n".join(lines[1:]).strip()
        if not rest:
            return header
        body = _format_block(rest, mode=mode) if rest else ""
        return f"{header}\n\n{body}" if body else header

    if all(_LIST_RE.match(ln) or not ln.strip() for ln in lines):
        return _format_list_block(block, mode=mode)

    if len(first) < 80 and first.endswith(":") and len(lines) > 1:
        label = _format_header(first[:-1], mode=mode)
        rest = _format_list_block("\n".join(lines[1:]), mode=mode)
        return f"{label}\n{rest}"

    if mode == "html":
        return _inline_to_html(block)
    return _inline_to_plain(block)


def format_ai_telegram_response(
    text: str,
    *,
    mode: OutputMode = "html",
    variant: str = "general",
) -> str:
    """
    Normaliza respuestas IA: párrafos, títulos, emojis, grillas y énfasis.
    variant: general | prediction | kb_direct
    """
    raw = (text or "").strip()
    if not raw:
        return ""

    if _should_light_format(raw):
        if mode == "html":
            return _inline_to_html(raw)
        return raw

    footer_match = _CREDITS_FOOTER_RE.search(raw)
    footer = footer_match.group(0).strip() if footer_match else ""
    body = _CREDITS_FOOTER_RE.sub("", raw).strip()

    blocks = _split_blocks(body)
    if not blocks:
        blocks = [body]

    formatted_blocks: list[str] = []
    for block in blocks:
        formatted_blocks.append(_format_block(block, mode=mode))

    out = "\n\n".join(formatted_blocks)
    if variant == "prediction" and mode == "plain":
        out = f"📊 Contexto IA\n\n{out}"
    if footer:
        if mode == "html":
            footer_plain = footer.replace("Consultas restantes:", "").strip()
            m = re.search(r"(\d+)", footer_plain)
            n = m.group(1) if m else "?"
            out = f"{out}\n\n<i>💬 Consultas restantes: {escape_html(n)}</i>"
        else:
            out = f"{out}\n\n💬 {footer}"
    return out[:MAX_TG_MESSAGE]


def format_prediction_analysis(
    match_brief: dict[str, Any],
    *,
    mode: OutputMode = "plain",
) -> str:
    """Bloque de análisis IA en wizard / brief de predicción."""
    line = (match_brief.get("ia_prediction_line") or "").strip()
    if not line:
        return ""

    home = match_brief.get("home_team") or ""
    away = match_brief.get("away_team") or ""

    def _bullets(label: str, items: list[Any], emoji: str) -> str:
        if not items:
            return ""
        rows = [f"- {emoji} {label}: {x}" for x in items[:4]]
        return "\n".join(rows)

    sections = [
        f"## Análisis del partido {home} vs {away}",
        f"🎯 {line}",
        _bullets(f"Fortalezas {home}", match_brief.get("home_strengths") or [], "💪"),
        _bullets(f"Debilidades {home}", match_brief.get("home_weaknesses") or [], "⚠️"),
        _bullets(f"Fortalezas {away}", match_brief.get("away_strengths") or [], "💪"),
        _bullets(f"Debilidades {away}", match_brief.get("away_weaknesses") or [], "⚠️"),
        "_Análisis informativo; no es recomendación de apuesta ni marcador exacto._",
    ]
    raw = "\n\n".join(s for s in sections if s)
    return format_ai_telegram_response(raw, mode=mode, variant="prediction")
