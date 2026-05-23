"""Comandos /invitar sin LLM — SPEC-020 / SPEC-029."""
from __future__ import annotations

import re

from src.dao.dynamo.group_dao import GroupDAO
from src.dao.dynamo.user_dao import UserDAO
from src.services.auth_service import AuthService
from src.services.invitation_service import InvitationService
from src.services.invitation_telegram_ui import invite_destination_keyboard

_INVITAR = re.compile(r"^/invitar(?:@[\w_]+)?(?:\s+(\d+))?\s*$", re.IGNORECASE)
_LISTAR = re.compile(r"^/mis[-_]invitaciones\s*$", re.IGNORECASE)
_REVOCAR = re.compile(r"^/revocar(?:@[\w_]+)?\s+([A-Za-z0-9]{8})\s*$", re.IGNORECASE)
_UNIRME = re.compile(r"^/unirme(?:@[\w_]+)?\s+([A-Za-z0-9]{8})\s*$", re.IGNORECASE)


def handle_invitation_command(user_id: str, text: str) -> tuple[str, dict | None] | str | None:
    """Respuesta fija, opcional reply_markup (SPEC-029)."""
    text = (text or "").strip()
    svc = InvitationService()
    auth = AuthService()
    groups = GroupDAO()

    m = _INVITAR.match(text)
    if m:
        max_uses = int(m.group(1) or 1)
        is_admin = auth.is_admin_global(user_id)
        owner_gid = groups.get_owner_group_id(user_id)
        if not is_admin and not owner_gid:
            return (
                "Creá un grupo antes de invitar (usá /crear-grupo).",
                None,
            )
        profile = UserDAO().get_profile(user_id) or {}
        ctx_gid = profile.get("group_context_group_id")
        if ctx_gid:
            grp = groups.get_group(ctx_gid)
            if not grp:
                UserDAO().update_profile(user_id, group_context_group_id=None)
                ctx_gid = None
        # Admin siempre elige destino (no atar a group_context de /editar-grupo)
        if ctx_gid and not is_admin:
            grp = groups.get_group(ctx_gid)
            if grp:  # noqa: SIM102 — ctx validado arriba
                slots = auth.slots_available(ctx_gid, actor_user_id=user_id)
                can_invite, _reason = auth.check_can_invite(user_id, ctx_gid)
                use_context = can_invite and (
                    slots is None or max_uses <= slots
                )
                if use_context:
                    try:
                        result = svc.create_invitation(
                            user_id, max_uses=max_uses, group_id=ctx_gid
                        )
                        return result["message"], None
                    except ValueError as exc:
                        return str(exc), None
                if not is_admin:
                    if slots is not None and max_uses > slots:
                        s = "slot" if slots == 1 else "slots"
                        d = "disponible" if slots == 1 else "disponibles"
                        return (
                            f"Solo tenés {slots} {s} {d} en tu grupo",
                            None,
                        )
                    return (
                        f"No podés invitar a este grupo ({_reason}).",
                        None,
                    )
        owner_group = groups.get_group(owner_gid) if owner_gid else None
        intro = (
            f"🔗 Invitaciones — {max_uses} cupo{'s' if max_uses != 1 else ''}\n\n"
            "Elegí el grupo destino:"
        )
        if is_admin:
            intro += "\nPor defecto podés invitar al torneo General (GLOBAL)."
        return intro, invite_destination_keyboard(
            max_uses, is_admin=is_admin, owner_group=owner_group
        )

    if _LISTAR.match(text):
        rows = svc.list_my_invitations(user_id)
        if not rows:
            return "No tenés invitaciones activas.", None
        lines = [
            f"- {r['invite_id']} [{r['status']}] {r['uses_count']}/{r['max_uses']}\n  {r['link']}"
            for r in rows
        ]
        return "Tus invitaciones:\n" + "\n".join(lines), None

    m = _REVOCAR.match(text)
    if m:
        invite_id = m.group(1)
        try:
            svc.revoke_invitation(invite_id, user_id)
            return f"Invitación {invite_id} revocada.", None
        except ValueError as exc:
            return str(exc), None

    m = _UNIRME.match(text)
    if m:
        invite_id = m.group(1)
        try:
            result = svc.accept_invitation_for_existing_user(user_id, invite_id)
        except ValueError as exc:
            code = str(exc)
            if code in (
                "INVITATION_NOT_USABLE",
                "INVITATION_NOT_ACTIVE",
                "INVITATION_INVALID",
            ):
                return (
                    "Esta invitación ya no está vigente. "
                    "Pedile a quien te la mandó que genere una nueva.",
                    None,
                )
            if code == "INVITATION_EXPIRED":
                return "Esta invitación expiró (tenía 24hs). Pedí una nueva.", None
            if code == "LIMIT_REACHED_INVITES":
                return (
                    "El grupo ya no tiene cupo. Pedile al admin que amplíe el límite.",
                    None,
                )
            return str(exc), None
        name = result.get("group_name", "el grupo")
        if result.get("joined_new"):
            return (
                f'✅ Te sumamos a "{name}".\nUsá /grupos para ver tus grupos.',
                None,
            )
        return f'ℹ️ Ya formás parte de "{name}".', None

    return None
