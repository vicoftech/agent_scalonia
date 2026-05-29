"""Comandos admin /noticia — SPEC-2026-046."""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_NOTICIA = re.compile(r"^/noticia(?:@[\w_]+)?(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
_NOTICIA_PUBLICAR = re.compile(r"^/noticia_publicar(?:@[\w_]+)?\s*$", re.IGNORECASE)
_NOTICIAS_HOY = re.compile(r"^/noticias_hoy(?:@[\w_]+)?\s*$", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.I)


def _admin_only(user_id: str) -> bool:
    from src.services.auth_service import AuthService

    return AuthService().is_admin_global(user_id)


def _get_draft(profile: dict[str, Any]) -> dict[str, Any] | None:
    draft = profile.get("news_admin_draft")
    return draft if isinstance(draft, dict) else None


def _save_draft(user_id: str, draft: dict[str, Any] | None) -> None:
    from src.dao.dynamo.user_dao import UserDAO

    if draft is None:
        UserDAO().update_profile(user_id, news_admin_draft=None)
    else:
        UserDAO().update_profile(user_id, news_admin_draft=draft)


def _preview_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Publicar", "callback_data": "news:pub:confirm"},
                {"text": "✏️ Editar", "callback_data": "news:pub:edit"},
            ],
            [{"text": "Cancelar", "callback_data": "news:pub:cancel"}],
        ]
    }


def handle_news_command(user_id: str, text: str) -> tuple[str | None, dict | None]:
    if not _admin_only(user_id):
        return "Solo administradores pueden publicar noticias.", None
    stripped = (text or "").strip()
    if _NOTICIAS_HOY.match(stripped):
        return _format_today_list(), None
    if _NOTICIA_PUBLICAR.match(stripped):
        return _publish_draft(user_id)
    m = _NOTICIA.match(stripped)
    if not m:
        return None, None
    arg = (m.group(1) or "").strip()
    if not arg:
        return (
            "📰 Enviá la URL del artículo o pegá el texto de la noticia.\n"
            "Luego usá /noticia_publicar o el botón ✅ Publicar en la vista previa.",
            None,
        )
    url_m = _URL_RE.search(arg)
    if url_m:
        return _start_url_draft(user_id, url_m.group(0))
    return _start_text_draft(user_id, arg)


def handle_news_admin_callback(
    user_id: str,
    data: str,
    *,
    callback_query_id: str | None = None,
) -> tuple[str | None, dict | None]:
    from handler import _get_token, _post_json

    if not _admin_only(user_id):
        return None, None
    token = _get_token()
    if callback_query_id:
        _post_json(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            {"callback_query_id": callback_query_id},
            timeout=5,
        )
    if data == "news:pub:cancel":
        _save_draft(user_id, None)
        return "Publicación cancelada.", None
    if data == "news:pub:edit":
        return "Reenviá la URL o el texto con /noticia …", None
    if data == "news:pub:confirm":
        return _publish_draft(user_id)
    return None, None


def _start_url_draft(user_id: str, url: str) -> tuple[str, dict | None]:
    from src.services.news_curation_service import NewsCurationService
    from src.services.news_telegram_format import format_news_caption

    og = NewsCurationService().fetch_og_article(url)
    if not og:
        return "No pude leer esa URL. Probá con otro enlace o pegá el texto.", None
    _save_draft(user_id, og)
    caption = format_news_caption({**og, "source_type": "ADMIN"}, include_footer=True)
    return f"Vista previa:\n\n{caption}", _preview_keyboard()


def _start_text_draft(user_id: str, text: str) -> tuple[str, dict | None]:
    from src.services.news_telegram_format import format_news_caption

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    headline = lines[0][:200] if lines else "Noticia Prode"
    summary = " ".join(lines[1:]) if len(lines) > 1 else headline
    draft = {
        "headline": headline,
        "summary": summary[:600],
        "article_url": "https://www.fifa.com",
        "category": "Mundial 2026",
        "subcategory": "#Noticias",
        "source_label": "Admin · texto",
        "relevance_score": 80,
        "image_url": "",
    }
    _save_draft(user_id, draft)
    caption = format_news_caption({**draft, "source_type": "ADMIN"}, include_footer=True)
    return f"Vista previa:\n\n{caption}", _preview_keyboard()


def _publish_draft(user_id: str) -> tuple[str, dict | None]:
    from src.dao.dynamo.user_dao import UserDAO

    profile = UserDAO().get_profile(user_id) or {}
    draft = _get_draft(profile)
    if not draft:
        return "No hay borrador. Usá /noticia con una URL o texto.", None
    try:
        from handler import _get_token, _send_photo
        from news_broadcast import broadcast_news_message
        from src.services.world_cup_news_service import WorldCupNewsService

        def _broadcast(**kwargs: Any) -> tuple[int, int]:
            targets = WorldCupNewsService().list_delivery_targets()
            return broadcast_news_message(
                delivery_targets=targets,
                news_id=kwargs["news_id"],
                caption=kwargs["caption"],
                image_url=kwargs["image_url"],
                like_count=kwargs["like_count"],
                token=_get_token(),
                send_photo=_send_photo,
            )

        svc = WorldCupNewsService(broadcast_fn=_broadcast)
        out = svc.publish_admin(user_id, draft)
        _save_draft(user_id, None)
        return (
            f"✅ Noticia publicada.\n"
            f"ID: {out.get('news_id', '')[:8]}…\n"
            f"📤 Enviada a {out.get('sent_count', 0)} usuario(s).\n"
            f"Título: {out.get('headline', '')[:80]}",
            None,
        )
    except Exception:
        logger.exception("publish_admin failed")
        return "No pude publicar la noticia. Revisá los logs.", None


def _format_today_list() -> str:
    from src.services.world_cup_news_service import WorldCupNewsService

    items = WorldCupNewsService().list_today_for_admin()
    if not items:
        return "📰 No hay noticias publicadas hoy (ART)."
    lines = ["📰 Noticias de hoy", ""]
    for it in items:
        slot = it.get("automated_slot") or it.get("source_type", "")
        lines.append(
            f"· {it.get('news_id', '')[:8]}… | {slot} | 👍{int(it.get('like_count') or 0)} "
            f"👁{int(it.get('read_count') or 0)} | {str(it.get('headline') or '')[:50]}"
        )
    return "\n".join(lines)
