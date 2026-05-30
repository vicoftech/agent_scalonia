"""Atajos /proximo /partidos /reglas /grupos — menú Telegram."""
from __future__ import annotations

import re

from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.prediction_dao import PredictionDAO
from src.dao.dynamo.user_dao import UserDAO
from src.services.match_service import MatchService

_PROXIMO = re.compile(r"^/proximo(?:@[\w_]+)?\s*$", re.IGNORECASE)
_REGLAS = re.compile(r"^/reglas(?:@[\w_]+)?\s*$", re.IGNORECASE)
_MENU = re.compile(r"^/menu(?:@[\w_]+)?\s*$", re.IGNORECASE)


def format_mi_puntuacion(user_id: str) -> str:
    profile = UserDAO().get_profile(user_id) or {}
    total = int(profile.get("total_points") or 0)
    match_pts = int(profile.get("match_points") or 0)
    trivia_pts = int(profile.get("trivia_points") or 0)

    preds = PredictionDAO().list_user_predictions(user_id)
    scored = [p for p in preds if p.get("points_earned") is not None]
    active = [p for p in preds if p.get("status") == "ACTIVE"]
    pred_pts = sum(int(p.get("points_earned") or 0) for p in scored)

    lines = [
        "📊 Mi puntuación",
        "",
        f"Total perfil: {total} pts",
        f"  · Partidos (perfil): {match_pts} pts",
        f"  · Trivia (perfil): {trivia_pts} pts",
        f"  · Predicciones puntuadas (suma): {pred_pts} pts",
        "",
        f"Predicciones activas: {len(active)}",
        f"Predicciones ya puntuadas: {len(scored)}",
    ]
    if scored:
        lines.append("\nÚltimas puntuadas:")
        matches = MatchDAO()
        for p in sorted(scored, key=lambda x: x.get("updated_at", ""), reverse=True)[:8]:
            m = matches.get_match(p.get("match_id", "")) or {}
            ht = m.get("home_team", "?")
            at = m.get("away_team", "?")
            lines.append(
                f"· {ht} vs {at}: pred {p.get('home_goals')}-{p.get('away_goals')} "
                f"→ {int(p.get('points_earned') or 0)} pts"
            )
    else:
        lines.append("\nTodavía no tenés predicciones puntuadas.")
    lines.append("\nRanking detallado del grupo: próximamente en /grupos.")
    return "\n".join(lines)


def format_resultados(*, limit: int = 12) -> str:
    dao = MatchDAO()
    svc = MatchService(dao=dao)
    finished = svc.search(status="FINISHED", limit=limit)
    if not finished:
        scheduled = svc.list_all()
        any_finished = [m for m in scheduled if (m.get("status") or "").upper() == "FINISHED"]
        if not any_finished:
            return (
                "🏁 Resultados\n\n"
                "Aún no hay partidos marcados como finalizados en el fixture."
            )
        finished = any_finished[:limit]

    lines = ["🏁 Resultados recientes", ""]
    for m in finished:
        res = dao.get_result(m["match_id"])
        if res:
            score = (
                f"{int(res.get('result_90min_home', res.get('result_final_home', 0)))}-"
                f"{int(res.get('result_90min_away', res.get('result_final_away', 0)))}"
            )
            num = m.get("match_number", "?")
            lines.append(f"· #{num} {m['home_team']} {score} {m['away_team']}")
        else:
            lines.append(f"· {svc.format_match(m)} — marcador pendiente")
    return "\n".join(lines)


def handle_shortcut_command(
    user_id: str, text: str
) -> tuple[str, dict | None] | None:
    text = (text or "").strip()

    if _MENU.match(text):
        from bot_commands import admin_menu_hint
        from src.services.auth_service import AuthService

        base = (
            "✅ Menú actualizado (botón / y teclado de abajo).\n\n"
            "Usá /help para la lista completa.\n"
            "Atajos: ⏭️ Próximo · ⚽ Partidos · 🤖 Ask IA · "
            "🏆 Mi ranking · 👥 Grupos · 📖 Reglas"
        )
        if AuthService().is_admin_global(user_id):
            base += f"\n\n{admin_menu_hint()}"
        return base, None

    if _REGLAS.match(text):
        from bot_commands import handle_reglas_command

        return handle_reglas_command(user_id), None

    if _PROXIMO.match(text):
        from src.services.prediction_service import PredictionService
        from src.services.prediction_wizard import _clear_wizard

        svc = PredictionService()
        _clear_wizard(svc, user_id)
        return svc.list_proximo_view(user_id)

    from ranking_commands import handle_mi_ranking_command, matches_mi_ranking_command

    if matches_mi_ranking_command(text):
        return handle_mi_ranking_command(user_id, text)

    from ask_ia_commands import handle_ask_ia_command

    ask_reply = handle_ask_ia_command(user_id, text)
    if ask_reply:
        return ask_reply

    return None


def should_refresh_bot_menu(text: str) -> bool:
    """Comandos que disparan setMyCommands (menú del botón /)."""
    t = (text or "").strip().lower().split("@")[0].split()[0]
    return t in {
        "/menu",
        "/start",
        "/help",
        "/ayuda",
        "/proximo",
        "/partidos",
        "/grupos",
        "/mi_ranking",
        "/mi-ranking",
        "/mi_puntuacion",
        "/mi-puntuacion",
        "/ask_ia",
        "/reglas",
        "/completo",
    }
