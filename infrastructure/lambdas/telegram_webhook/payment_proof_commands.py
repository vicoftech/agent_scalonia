"""Reenvío de comprobantes al admin vía Telegram."""
from __future__ import annotations

from src.services.payment_proof_notify import PaymentProofNotifier


def notify_admins_payment_proof(
    file_id: str,
    file_kind: str,
    caption: str,
) -> int:
    from handler import _get_token, _send_document, _send_message, _send_photo

    token = _get_token()

    def send_media(chat_id: int, fid: str, kind: str, cap: str) -> bool:
        if kind == "document":
            return _send_document(chat_id, fid, cap, token)
        return _send_photo(chat_id, fid, cap, token)

    def send_text(chat_id: int, text: str) -> None:
        _send_message(chat_id, text, token)

    return PaymentProofNotifier(send_media=send_media, send_text=send_text).notify_admins(
        file_id=file_id,
        file_kind=file_kind,
        caption=caption,
    )
