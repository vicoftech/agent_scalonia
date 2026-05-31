"""Comandos /ampliar_plan y callbacks gup:* — SPEC-2026-044."""
from __future__ import annotations

import logging
import re

from src.services.group_upgrade_service import GroupUpgradeService

logger = logging.getLogger(__name__)

_AMPLIAR = re.compile(
    r"^/(?:ampliar[_-]plan|grupo[_-]ampliar)(?:@[\w_]+)?\s*$",
    re.IGNORECASE,
)
_OTORGAR_GRUPO = re.compile(
    r"^/grupo[_-]otorgar[_-]grupo(?:@[\w_]+)?\s+(\S+)(?:\s+(\d+))?\s*$",
    re.IGNORECASE,
)
_OTORGAR_CUPOS = re.compile(
    r"^/grupo[_-]otorgar[_-]cupos(?:@[\w_]+)?\s+(\S+)\s+(\S+)\s+(\d+)\s*$",
    re.IGNORECASE,
)
_APLICAR_U = re.compile(
    r"^/grupo[_-]aplicar[_-]u(?:@[\w_]+)?\s+(\S+)\s+(\d+)\s*$",
    re.IGNORECASE,
)
_COMPRAS = re.compile(r"^/grupo[_-]compras[_-]pendientes(?:@[\w_]+)?\s*$", re.IGNORECASE)
_VER_CUOTAS = re.compile(
    r"^/grupo[_-]ver[_-]cuotas(?:@[\w_]+)?\s+(\S+)\s*$",
    re.IGNORECASE,
)


def _service() -> GroupUpgradeService:
    from handler import _get_token, _send_message
    from payment_proof_commands import notify_admins_payment_proof

    token = _get_token()

    def telegram_notify(chat_id: int, text: str) -> None:
        _send_message(int(chat_id), text, token)

    return GroupUpgradeService(
        telegram_notify=telegram_notify,
        admin_proof_notify=notify_admins_payment_proof,
    )


def handle_group_upgrade_command(user_id: str, text: str) -> tuple[str, dict | None] | None:
    stripped = (text or "").strip()

    if _AMPLIAR.match(stripped):
        return _service().start_wizard(user_id)

    m = _OTORGAR_GRUPO.match(stripped)
    if m:
        count = int(m.group(2) or 1)
        return _service().admin_grant_group_slots(user_id, m.group(1), count), None

    m = _OTORGAR_CUPOS.match(stripped)
    if m:
        return (
            _service().admin_grant_member_packs(
                user_id, m.group(1), m.group(2), int(m.group(3))
            ),
            None,
        )

    m = _APLICAR_U.match(stripped)
    if m:
        return _service().admin_apply_units(user_id, m.group(1), int(m.group(2))), None

    if _COMPRAS.match(stripped):
        return _service().admin_list_pending(user_id), None

    m = _VER_CUOTAS.match(stripped)
    if m:
        return _service().admin_show_quotas(user_id, m.group(1)), None

    return None


def handle_group_upgrade_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("gup:"):
        return None
    try:
        return _service().callback(user_id, data)
    except Exception:
        logger.exception("group_upgrade callback failed data=%s", data[:40])
        return "No pude procesar esa acción. Probá /ampliar_plan de nuevo.", None


def handle_group_upgrade_purchase_proof(
    user_id: str, *, file_id: str, file_kind: str = "photo"
) -> str:
    return _service().handle_payment_proof(
        user_id, file_id=file_id, file_kind=file_kind
    )
