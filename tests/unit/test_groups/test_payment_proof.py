"""Comprobantes de pago — reenvío al admin."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.group_upgrade_service import GroupUpgradeService
from src.services.payment_proof_notify import PaymentProofNotifier, USER_RECEIPT_ACK


def test_user_receipt_ack_message():
    assert "Recibimos tu comprobante" in USER_RECEIPT_ACK
    assert "admin" in USER_RECEIPT_ACK.lower()


@patch("src.services.payment_proof_notify.UserDAO")
def test_notify_admins_prefers_copy_message(mock_users):
    mock_users.return_value.list_admin_telegram_targets.return_value = [
        {"user_id": "admin1", "tg_chat_id": 111},
    ]
    copied: list[tuple[int, int, int, str]] = []
    sent_media: list[tuple] = []

    def copy_message(to_id: int, from_id: int, msg_id: int, cap: str) -> bool:
        copied.append((to_id, from_id, msg_id, cap))
        return True

    def send_media(chat_id: int, file_id: str, kind: str, caption: str) -> bool:
        sent_media.append((chat_id, file_id, kind, caption))
        return True

    notifier = PaymentProofNotifier(
        users=mock_users.return_value,
        send_media=send_media,
        copy_message=copy_message,
    )
    count = notifier.notify_admins(
        file_id="fid123",
        file_kind="photo",
        caption="Comprobante test",
        from_chat_id=999,
        message_id=42,
    )
    assert count == 1
    assert copied == [(111, 999, 42, "Comprobante test")]
    assert sent_media == []


@patch("src.services.payment_proof_notify.UserDAO")
def test_notify_admins_sends_media(mock_users):
    mock_users.return_value.list_admin_telegram_targets.return_value = [
        {"user_id": "admin1", "tg_chat_id": 111},
    ]
    sent: list[tuple[int, str, str, str]] = []

    def send_media(chat_id: int, file_id: str, kind: str, caption: str) -> bool:
        sent.append((chat_id, file_id, kind, caption))
        return True

    notifier = PaymentProofNotifier(
        users=mock_users.return_value,
        send_media=send_media,
    )
    count = notifier.notify_admins(
        file_id="fid123",
        file_kind="document",
        caption="Comprobante test",
    )
    assert count == 1
    assert sent[0][0] == 111
    assert sent[0][1] == "fid123"
    assert sent[0][2] == "document"


def test_group_upgrade_proof_does_not_auto_credit():
    users = MagicMock()
    purchases = MagicMock()
    purchases.find_by_file_id.return_value = None
    profile = {
        "user_id": "u1",
        "alias": "toti",
        "group_upgrade_purchase_pending": True,
        "group_upgrade_wizard_units": 1,
        "group_upgrade_purchase_id": "pid-1",
        "group_upgrade_quote_ars": 14999,
        "group_upgrade_alloc_draft": "[]",
        "pending_group_upgrade_units": 0,
    }
    users.get_profile.return_value = profile
    users.update_profile.side_effect = lambda _u, **kw: profile.update(kw)

    notified: list[tuple[str, str, str]] = []

    svc = GroupUpgradeService(
        users=users,
        purchases=purchases,
        groups=MagicMock(),
        matches=MagicMock(),
        admin_proof_notify=lambda fid, kind, cap, **kw: notified.append((fid, kind, cap)) or 1,
    )
    msg = svc.handle_payment_proof("u1", file_id="f1", file_kind="photo")
    assert "Recibimos tu comprobante" in msg
    assert profile.get("pending_group_upgrade_units", 0) == 0
    purchases.mark_paid.assert_called_once()
    assert len(notified) == 1


def test_group_upgrade_cooldown_still_notifies_admin():
    users = MagicMock()
    purchases = MagicMock()
    profile = {
        "user_id": "u1",
        "alias": "vic",
        "group_upgrade_purchase_pending": True,
        "group_upgrade_wizard_units": 2,
        "group_upgrade_purchase_id": "pid-1",
        "group_upgrade_quote_ars": 29997,
        "group_upgrade_alloc_draft": "[]",
        "last_group_upgrade_purchase_at": "2026-05-31T00:00:00+00:00",
    }
    users.get_profile.return_value = profile
    notified: list[tuple] = []

    def notify(*args, **kwargs):
        notified.append((args, kwargs))
        return 1

    svc = GroupUpgradeService(
        users=users,
        purchases=purchases,
        groups=MagicMock(),
        matches=MagicMock(),
        admin_proof_notify=notify,
    )
    msg = svc.handle_payment_proof(
        "u1",
        file_id="f1",
        file_kind="photo",
        from_chat_id=12345,
        message_id=99,
    )
    assert "24 h" in msg
    assert "reenviamos al admin" in msg.lower()
    assert len(notified) == 1
    assert notified[0][1]["from_chat_id"] == 12345
    purchases.mark_paid.assert_not_called()
