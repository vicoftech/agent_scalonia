"""Notificación de comprobantes de pago al admin — Ask IA y ampliación grupos."""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from src.dao.dynamo.user_dao import UserDAO

logger = logging.getLogger(__name__)

USER_RECEIPT_ACK = (
    "✅ Recibimos tu comprobante.\n\n"
    "Se lo enviamos al admin para validarlo. En breve recibirás tu pedido."
)


class PaymentProofNotifier:
    """Reenvía foto/PDF al admin global con datos del usuario."""

    def __init__(
        self,
        users: UserDAO | None = None,
        *,
        send_media: Callable[[int, str, str, str], bool] | None = None,
        copy_message: Callable[[int, int, int, str], bool] | None = None,
        send_text: Callable[[int, str], None] | None = None,
    ):
        self._users = users or UserDAO()
        self._send_media = send_media
        self._copy_message = copy_message
        self._send_text = send_text

    def _admin_targets(self) -> list[dict[str, Any]]:
        targets = self._users.list_admin_telegram_targets()
        if targets:
            return targets
        raw = (os.environ.get("TELEGRAM_ADMIN_CHAT_IDS") or "").strip()
        if not raw:
            return []
        out: list[dict[str, Any]] = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(
                    {
                        "user_id": "env-admin",
                        "tg_chat_id": int(part),
                        "alias": "admin",
                    }
                )
        return out

    def notify_admins(
        self,
        *,
        file_id: str,
        file_kind: str,
        caption: str,
        from_chat_id: int | None = None,
        message_id: int | None = None,
    ) -> int:
        targets = self._admin_targets()
        if not targets:
            logger.warning("payment_proof notify skipped: no admin targets")
            return 0

        sent = 0
        for admin in targets:
            chat_id = int(admin["tg_chat_id"])
            try:
                ok = False
                if (
                    from_chat_id is not None
                    and message_id is not None
                    and self._copy_message is not None
                ):
                    ok = self._copy_message(chat_id, from_chat_id, message_id, caption)
                if not ok and self._send_media is not None:
                    ok = self._send_media(chat_id, file_id, file_kind, caption)
                if ok:
                    sent += 1
                else:
                    logger.warning(
                        "payment_proof media failed admin=%s file_kind=%s",
                        str(admin.get("user_id", ""))[:8],
                        file_kind,
                    )
            except Exception:
                logger.exception(
                    "payment_proof notify failed admin=%s",
                    str(admin.get("user_id", ""))[:8],
                )

        if sent == 0 and self._send_text is not None:
            fallback = (
                f"{caption}\n\n"
                f"(No se pudo reenviar el archivo; file_id={file_id})"
            )
            for admin in targets:
                try:
                    self._send_text(int(admin["tg_chat_id"]), fallback[:4096])
                    sent += 1
                except Exception:
                    logger.exception("payment_proof text fallback failed")
        return sent


def build_ask_ia_admin_caption(profile: dict[str, Any], *, amount_ars: int) -> str:
    alias = (profile.get("alias") or "sin-alias").strip()
    uid = str(profile.get("user_id") or "")[:8]
    return (
        "💳 Comprobante Ask IA\n\n"
        f"Usuario: @{alias} ({uid})\n"
        f"Monto esperado: ${amount_ars:,} ARS\n"
        "Producto: pack consultas Ask IA\n\n"
        "Acción: /ia_otorgar <alias> <cantidad>"
    ).replace(",", ".")


def build_group_upgrade_admin_caption(
    profile: dict[str, Any],
    *,
    units: int,
    amount_ars: int,
    allocation_summary: str,
    purchase_id: str,
) -> str:
    alias = (profile.get("alias") or "sin-alias").strip()
    uid = str(profile.get("user_id") or "")[:8]
    pid = (purchase_id or "")[:8]
    return (
        "💳 Comprobante ampliación grupos\n\n"
        f"Usuario: @{alias} ({uid})\n"
        f"Compra: {units} U · ${amount_ars:,} ARS\n"
        f"ID: {pid}\n"
        f"Asignación pedida:\n{allocation_summary}\n\n"
        "Acción: /grupo_aplicar_u · /grupo_otorgar_grupo · /grupo_otorgar_cupos"
    ).replace(",", ".")
