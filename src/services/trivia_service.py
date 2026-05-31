"""Sistema de trivias SPEC-2026-025."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
from src.dao.dynamo.job_ctrl_dao import JobCtrlDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.trivia_dao import TriviaDAO
from src.dao.dynamo.user_dao import UserDAO
from src.jobs.daily_trivia_schedule import (
    compute_daily_trivia_schedule,
    local_today_iso,
    should_publish_daily_trivia,
)
from src.services.trivia_question_bank import (
    pick_any_curated_question,
    pick_curated_question,
    question_fingerprint,
)

logger = logging.getLogger(__name__)

LEVEL_POINTS = {"BASIC": 1, "MEDIUM": 3, "EXPERT": 5}
LEVEL_LABELS = {"BASIC": "Básico", "MEDIUM": "Intermedio", "EXPERT": "Experto"}
MAX_ROUNDS_PER_DAY = 5
MAX_ACTIVE_GROUP_TRIVIAS = 3

PROFILE_TO_LEVEL = {
    "easy": "BASIC",
    "casual": "BASIC",
    "medium": "MEDIUM",
    "fanatic": "MEDIUM",
    "fanático": "MEDIUM",
    "hard": "EXPERT",
    "encyclopedia": "EXPERT",
    "enciclopedia": "EXPERT",
}

TOPIC_QUERIES = {
    "mundiales": "historia copa del mundo FIFA mundiales",
    "historias_mundiales": (
        "anécdotas historias curiosidades leyendas copa del mundo FIFA mundiales"
    ),
    "records": "récords estadísticas copa del mundo FIFA goleadores",
    "selecciones": "selecciones nacionales copa del mundo",
    "jugadores": "leyendas jugadores copa del mundo",
    "reglas": "reglas FIFA fútbol",
    "libre": "curiosidades fútbol copa del mundo",
}

DAILY_GENERAL_TOPIC = "historias_mundiales"
DAILY_GENERAL_LEVEL = "MEDIUM"
DAILY_TRIVIA_JOB = "DAILY_TRIVIA"
GENERATION_MAX_ATTEMPTS = 3
MIN_CONTEXT_CHARS = 80
GENERIC_TRIVIA_CONTEXT = (
    "Copa Mundial FIFA: historia, campeones, goleadores, sedes, récords, "
    "selecciones nacionales, finales memorables y curiosidades del fútbol."
)


class TriviaService:
    def __init__(
        self,
        *,
        trivia_dao: TriviaDAO | None = None,
        user_dao: UserDAO | None = None,
        group_dao: GroupDAO | None = None,
        job_ctrl_dao: JobCtrlDAO | None = None,
        match_dao: MatchDAO | None = None,
    ):
        self._trivia = trivia_dao or TriviaDAO()
        self._users = user_dao or UserDAO()
        self._groups = group_dao or GroupDAO()
        self._job_ctrl = job_ctrl_dao or JobCtrlDAO()
        self._matches = match_dao or MatchDAO()

    def level_for_user(self, user_id: str, level: str | None = None) -> str:
        if level:
            up = level.upper()
            if up in LEVEL_POINTS:
                return up
        profile = self._users.get_profile(user_id) or {}
        fk = str(profile.get("football_knowledge") or "medium").lower()
        return PROFILE_TO_LEVEL.get(fk, "MEDIUM")

    def _is_admin(self, user_id: str) -> bool:
        profile = self._users.get_profile(user_id) or {}
        return bool(profile.get("is_admin"))

    def rounds_remaining(self, user_id: str) -> int:
        if self._is_admin(user_id):
            return MAX_ROUNDS_PER_DAY
        profile = self._users.get_profile(user_id) or {}
        used = int(profile.get("trivia_rounds_today") or 0)
        return max(0, MAX_ROUNDS_PER_DAY - used)

    def _ensure_can_play(self, user_id: str) -> None:
        if self._is_admin(user_id):
            return
        profile = self._users.get_profile(user_id) or {}
        used = int(profile.get("trivia_rounds_today") or 0)
        if used >= MAX_ROUNDS_PER_DAY:
            raise ValueError("DAILY_LIMIT")

    def _rounds_footer(self, user_id: str) -> str:
        if self._is_admin(user_id):
            return "\n\n📊 Rondas hoy: ilimitadas (admin)"
        remaining = self.rounds_remaining(user_id)
        return f"\n\n📊 Rondas restantes hoy: {remaining}/{MAX_ROUNDS_PER_DAY}"

    def _fetch_context(self, topic: str, *, match: dict | None = None) -> tuple[str, str]:
        """Retorna (contexto, source) donde source es kb o web."""
        if match:
            from src.services.trivia_kb_generator import fetch_pre_match_kb_context

            text = fetch_pre_match_kb_context(match).strip()
            return text[:6000], "kb" if len(text) >= MIN_CONTEXT_CHARS else "web"

        topic_key = (topic or "mundiales").lower()
        base = TOPIC_QUERIES.get(topic_key, TOPIC_QUERIES["mundiales"])
        try:
            from src.kb.resolve import resolve_kb_then_web

            result = resolve_kb_then_web(base, enqueue_on_web=False)
            kb_text = (result.kb_text or "").strip()
            if len(kb_text) >= MIN_CONTEXT_CHARS:
                return kb_text[:4000], "kb"
            if result.tavily_configured:
                web_text = (result.web_text or "").strip()
                if web_text:
                    return web_text[:4000], "web"
            return kb_text[:4000], "kb"
        except Exception:
            logger.exception("trivia context fetch failed")
            return "", "kb"

    def _answered_fingerprints(self, user_id: str | None) -> set[str]:
        if not user_id:
            return set()
        return self._users.get_answered_question_fingerprints(user_id)

    def _exclude_fingerprints(self, user_id: str | None) -> set[str]:
        """Preguntas ya generadas (global) + respondidas por el usuario."""
        fps = self._trivia.get_used_question_fingerprints()
        if user_id:
            fps |= self._answered_fingerprints(user_id)
        return fps

    def _prepare_generation_context(self, topic: str, ctx: str) -> str:
        """Asegura contexto mínimo para Bedrock aunque KB/web devuelvan poco."""
        text = (ctx or "").strip()
        topic_key = (topic or "mundiales").lower()
        topic_line = TOPIC_QUERIES.get(topic_key, TOPIC_QUERIES["mundiales"])
        if len(text) >= MIN_CONTEXT_CHARS:
            return text[:4000]
        parts = [GENERIC_TRIVIA_CONTEXT, f"Tema: {topic_line}"]
        if text:
            parts.append(text)
        merged = "\n\n".join(parts).strip()
        return merged[:4000]

    def generate_trivia_question(
        self,
        *,
        topic: str = "mundiales",
        level: str = "MEDIUM",
        context: str | None = None,
        match: dict | None = None,
        exclude_fingerprints: set[str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """KB/web + Bedrock on-demand; fallback curado (SPEC-049)."""
        from src.services.trivia_kb_generator import generate_question_from_context

        level = level.upper() if level.upper() in LEVEL_POINTS else "MEDIUM"
        exclude = set(exclude_fingerprints or [])
        if user_id:
            exclude |= self._exclude_fingerprints(user_id)

        context_source = "kb"
        if context is not None:
            ctx = self._prepare_generation_context(topic, context)
        else:
            raw_ctx, context_source = self._fetch_context(topic, match=match)
            ctx = self._prepare_generation_context(topic, raw_ctx)

        if ctx:
            for attempt in range(1, GENERATION_MAX_ATTEMPTS + 1):
                q = generate_question_from_context(
                    context=ctx,
                    topic=topic,
                    level=level,
                    match=match,
                    exclude_fingerprints=exclude,
                    attempt=attempt,
                    context_source=context_source,
                )
                if q and q.get("question_fp") not in exclude:
                    logger.info(
                        "trivia_generated topic=%s level=%s source=%s fp=%s attempt=%s",
                        topic,
                        level,
                        q.get("source"),
                        q.get("question_fp"),
                        attempt,
                    )
                    return q

        # Fallback curado: solo excluir preguntas ya respondidas por el usuario
        # (el registry global agotaba ~12 ítems manuales en dev).
        curated_exclude = self._answered_fingerprints(user_id) if user_id else exclude
        q = pick_curated_question(
            topic=topic, level=level, exclude_fingerprints=curated_exclude
        )
        if q:
            q.setdefault("source", "manual")
            return q

        q = pick_curated_question(
            topic="mundiales", level=level, exclude_fingerprints=curated_exclude
        )
        if q:
            q.setdefault("source", "manual")
            return q

        q = pick_any_curated_question(exclude_fingerprints=curated_exclude)
        if q:
            q.setdefault("source", "manual")
            return q

        logger.warning(
            "trivia_generation_failed topic=%s level=%s context_len=%s",
            topic,
            level,
            len(ctx),
        )
        raise ValueError("GENERATION_FAILED")

    def generate_pre_match_trivia(self, match: dict[str, Any]) -> dict[str, Any]:
        from src.services.trivia_kb_generator import generate_pre_match_question

        home = match.get("home_team", "")
        away = match.get("away_team", "")
        exclude = self._trivia.get_used_question_fingerprints()
        q = generate_pre_match_question(match, level="EXPERT", exclude_fingerprints=exclude)
        if not str(q.get("question", "")).startswith("Pre-partido"):
            q["question"] = f"Pre-partido {home} vs {away}: {q['question']}"
        q["match_id"] = match.get("match_id")
        return q

    def _broadcast_user_ids(self) -> list[str]:
        seen: set[str] = set()
        for group in self._groups.list_groups_for_broadcast():
            gid = group.get("group_id")
            if not gid:
                continue
            for user_id in self._groups.list_member_user_ids(gid):
                seen.add(user_id)
        return list(seen)

    def dispatch_pre_match_trivia(self, match: dict[str, Any]) -> dict[str, Any]:
        """Genera trivia pre-partido, persiste y envía por Telegram a miembros ACTIVE."""
        from src.clients.telegram_client import get_bot_token, send_telegram_message

        q = self.generate_pre_match_trivia(match)
        trivia_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        home = match.get("home_team", "")
        away = match.get("away_team", "")
        group = match.get("group_letter")
        grp = f" · Grupo {group}" if group else ""
        header = f"⚽ TRIVIA PRE-PARTIDO{grp}\n\n{home} vs {away}"
        item = self._trivia.put_broadcast_trivia(
            {
                "trivia_id": trivia_id,
                "type": "PRE_MATCH",
                "level": "EXPERT",
                "points": 5,
                "match_id": match.get("match_id"),
                "group_id": GLOBAL_GROUP_ID,
                "status": "SENT",
                "sent_at": now.isoformat(),
                "closes_at": (now + timedelta(hours=2)).isoformat(),
                **q,
            }
        )
        member_ids = self._broadcast_user_ids()
        targets = self._users.list_telegram_delivery_targets(member_ids)
        message = self.format_question_message(item, header=header)
        keyboard = self.answer_keyboard(trivia_id=trivia_id)
        token = get_bot_token()
        sent = skipped = 0
        for target in targets:
            chat_id = target.get("tg_chat_id")
            if not chat_id:
                skipped += 1
                continue
            try:
                send_telegram_message(
                    int(chat_id), message, token, reply_markup=keyboard
                )
                sent += 1
            except Exception:
                logger.exception(
                    "pre_match_trivia send failed user=%s",
                    str(target.get("user_id", ""))[:8],
                )
                skipped += 1
        logger.info(
            "pre_match_trivia source=%s match=%s",
            q.get("source", "?"),
            str(match.get("match_id", ""))[:8],
        )
        return {
            "status": "OK",
            "trivia_id": trivia_id,
            "match_id": match.get("match_id"),
            "question_source": q.get("source"),
            "telegram_sent": sent,
            "telegram_skipped": skipped,
            "eligible": len(targets),
        }

    def format_question_message(self, q: dict[str, Any], *, header: str = "") -> str:
        level = q.get("level", "MEDIUM")
        pts = LEVEL_POINTS.get(level, 3)
        label = LEVEL_LABELS.get(level, level)
        lines = []
        if header:
            lines.append(header)
        lines.append(f"🧠 TRIVIA — {label}  [{pts} pts si acertás]\n")
        lines.append(q["question"])
        opts = q.get("options") or {}
        lines.append("")
        for letter in ("A", "B", "C", "D"):
            if letter in opts:
                lines.append(f"[{letter}] {opts[letter]}")
        return "\n".join(lines)

    def answer_keyboard(self, *, session_id: str | None = None, trivia_id: str | None = None) -> dict:
        prefix = f"trv:s:{session_id}" if session_id else f"trv:t:{trivia_id}"
        return {
            "inline_keyboard": [
                [
                    {"text": "A", "callback_data": f"{prefix}:A"},
                    {"text": "B", "callback_data": f"{prefix}:B"},
                    {"text": "C", "callback_data": f"{prefix}:C"},
                    {"text": "D", "callback_data": f"{prefix}:D"},
                ]
            ]
        }

    def start_play(self, user_id: str, *, level: str | None = None, topic: str = "mundiales") -> dict[str, Any]:
        self._ensure_can_play(user_id)
        lvl = self.level_for_user(user_id, level)
        q = self.generate_trivia_question(
            topic=topic,
            level=lvl,
            user_id=user_id,
            exclude_fingerprints=self._exclude_fingerprints(user_id),
        )
        session_id = str(uuid.uuid4())
        record = {
            "session_id": session_id,
            "user_id": user_id,
            "level": lvl,
            "points": LEVEL_POINTS[lvl],
            "question_fp": q.get("question_fp") or question_fingerprint(q.get("question", "")),
            **q,
        }
        self._trivia.put_play_session(record)
        msg = self.format_question_message(q)
        msg += self._rounds_footer(user_id)
        return {
            "session_id": session_id,
            "message": msg,
            "keyboard": self.answer_keyboard(session_id=session_id),
        }

    def answer_play_session(self, user_id: str, session_id: str, answer: str) -> str:
        session = self._trivia.get_play_session(user_id, session_id)
        if not session:
            return "No encontré esa trivia. Pedí una nueva con /trivia."
        if session.get("state") == "ANSWERED":
            return "Ya respondiste esta trivia."

        letter = answer.strip().upper()[:1]
        correct_letter = (session.get("correct_answer") or session.get("correct") or "A").upper()
        is_correct = letter == correct_letter
        pts = int(session.get("points") or 0) if is_correct else 0

        fp = session.get("question_fp") or question_fingerprint(session.get("question", ""))
        duplicate = fp in self._users.get_answered_question_fingerprints(user_id)
        if duplicate:
            pts = 0

        self._trivia.complete_play_session(
            user_id,
            session_id,
            answer=letter,
            is_correct=is_correct,
            points_earned=pts,
        )
        if fp:
            self._users.mark_answered_question_fingerprint(user_id, fp)
        self._users.add_trivia_round(user_id, points=pts)

        return self._format_answer_result(
            is_correct=is_correct,
            points=pts,
            correct_letter=correct_letter,
            options=session.get("options_map") or {},
            explanation=session.get("explanation", ""),
            user_id=user_id,
            duplicate_question=duplicate,
        )

    def answer_broadcast(self, user_id: str, trivia_id: str, answer: str) -> str:
        self._ensure_can_play(user_id)

        trivia = self._trivia.get_trivia(trivia_id)
        if not trivia:
            return "Esta trivia ya no está disponible."
        if self._trivia.has_answered(trivia_id, user_id):
            return "Ya respondiste esta trivia."

        if (trivia.get("closes_at") or "") < datetime.now(timezone.utc).isoformat():
            return "Esta trivia ya cerró."

        letter = answer.strip().upper()[:1]
        correct = (trivia.get("correct") or "A").upper()
        is_correct = letter == correct
        fp = trivia.get("question_fp") or question_fingerprint(trivia.get("question", ""))
        duplicate = fp in self._users.get_answered_question_fingerprints(user_id)
        pts = int(trivia.get("points") or 0) if is_correct and not duplicate else 0

        self._trivia.put_answer(
            trivia_id=trivia_id,
            user_id=user_id,
            answer=letter,
            is_correct=is_correct,
            points=pts,
        )
        self._trivia.increment_trivia_stats(trivia_id, correct=is_correct)
        if fp:
            self._users.mark_answered_question_fingerprint(user_id, fp)
        self._users.add_trivia_round(user_id, points=pts)

        return self._format_answer_result(
            is_correct=is_correct,
            points=pts,
            correct_letter=correct,
            options=trivia.get("options") or {},
            explanation=trivia.get("explanation", ""),
            user_id=user_id,
            duplicate_question=duplicate,
        )

    def _format_answer_result(
        self,
        *,
        is_correct: bool,
        points: int,
        correct_letter: str,
        options: dict,
        explanation: str,
        user_id: str,
        duplicate_question: bool = False,
    ) -> str:
        opt_text = options.get(correct_letter, "")
        profile = self._users.get_profile(user_id) or {}
        total = int(profile.get("total_points") or 0)

        if duplicate_question:
            head = (
                "ℹ️ Ya habías respondido esta misma pregunta antes.\n"
                "No se suman puntos duplicados.\n\n"
                f"La respuesta correcta era {correct_letter}"
            )
        elif is_correct:
            head = f"✅ ¡Correcto! +{points} pts\n\nLa respuesta era {correct_letter}"
        else:
            head = f"❌ Incorrecto — sin puntos esta vez\n\nLa respuesta correcta era {correct_letter}"

        if opt_text:
            head += f" — {opt_text}"
        if explanation and not duplicate_question:
            head += f"\n\n{explanation}"
        if profile.get("is_admin"):
            used = int(profile.get("trivia_rounds_today") or 0)
            head += f"\n\n📊 Total: {total} pts | Rondas hoy: {used} (ilimitadas)"
        else:
            remaining = self.rounds_remaining(user_id)
            head += f"\n\n📊 Total: {total} pts | Rondas hoy: {remaining}/{MAX_ROUNDS_PER_DAY}"
        return head

    def publish_daily_general(
        self,
        *,
        created_by: str = "SYSTEM",
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Publica la trivia diaria general (historias de mundiales).
        Horario: min(10:00 ART, primer partido del día − 2 h).
        Idempotente por día calendario ART vía JOB_CTRL#DAILY_TRIVIA/<fecha>.
        """
        today = local_today_iso()
        schedule = compute_daily_trivia_schedule(self._matches.list_matches())

        if not force and not should_publish_daily_trivia(schedule):
            return {
                "status": "NOT_YET",
                "run_date": today,
                "publish_at_local": schedule.publish_at_iso,
                "first_kickoff_local": (
                    schedule.first_kickoff_local.isoformat()
                    if schedule.first_kickoff_local
                    else None
                ),
                "matches_today": schedule.matches_today,
            }

        if not force and self._job_ctrl.is_processed(DAILY_TRIVIA_JOB, today):
            existing = self._trivia.get_daily_general_for_date(today)
            return {
                "status": "SKIPPED",
                "run_date": today,
                "trivia_id": (existing or {}).get("trivia_id"),
            }

        existing = self._trivia.get_daily_general_for_date(today)
        if existing and not force:
            self._job_ctrl.mark_processed(
                DAILY_TRIVIA_JOB,
                today,
                meta={"trivia_id": existing["trivia_id"]},
            )
            return {
                "status": "SKIPPED",
                "run_date": today,
                "trivia_id": existing["trivia_id"],
            }

        exclude = self._trivia.get_used_question_fingerprints()
        q = self.generate_trivia_question(
            topic=DAILY_GENERAL_TOPIC,
            level=DAILY_GENERAL_LEVEL,
            exclude_fingerprints=exclude,
        )
        trivia_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        item = self._trivia.put_broadcast_trivia(
            {
                "trivia_id": trivia_id,
                "type": "DAILY_GENERAL",
                "level": DAILY_GENERAL_LEVEL,
                "points": LEVEL_POINTS[DAILY_GENERAL_LEVEL],
                "topic": DAILY_GENERAL_TOPIC,
                "created_by": created_by,
                "status": "SENT",
                "sent_at": now.isoformat(),
                "closes_at": (now + timedelta(hours=24)).isoformat(),
                "daily_date": today,
                **q,
            }
        )
        self._job_ctrl.mark_processed(
            DAILY_TRIVIA_JOB,
            today,
            meta={"trivia_id": trivia_id},
        )
        recipients = self._trivia.list_group_member_user_ids(GLOBAL_GROUP_ID)
        return {
            "status": "CREATED",
            "run_date": today,
            "trivia_id": trivia_id,
            "topic": DAILY_GENERAL_TOPIC,
            "publish_at_local": schedule.publish_at_iso,
            "first_kickoff_local": (
                schedule.first_kickoff_local.isoformat()
                if schedule.first_kickoff_local
                else None
            ),
            "matches_today": schedule.matches_today,
            "recipient_count": len(recipients),
            "message": self.format_question_message(
                item,
                header="📚 Trivia del día — Historias del Mundial",
            ),
        }

    def build_daily_delivery_for_user(
        self,
        user_id: str,
        profile: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Mensaje + teclado si hay trivia diaria pendiente y no se mostró aún."""
        if profile.get("notifications_enabled") is False:
            return None

        today = local_today_iso()
        trivia = self._trivia.get_daily_general_for_date(today)
        if not trivia:
            return None
        trivia_id = trivia["trivia_id"]
        if self._trivia.has_answered(trivia_id, user_id):
            return None
        if profile.get("daily_trivia_prompted_id") == trivia_id:
            return None
        if (trivia.get("closes_at") or "") < datetime.now(timezone.utc).isoformat():
            return None

        self._users.update_profile(user_id, daily_trivia_prompted_id=trivia_id)
        return {
            "trivia_id": trivia_id,
            "message": self.format_question_message(
                trivia,
                header="📚 Trivia del día — Historias del Mundial",
            ),
            "keyboard": self.answer_keyboard(trivia_id=trivia_id),
        }

    def create_and_send_general(
        self,
        admin_user_id: str,
        *,
        topic: str,
        level: str = "EXPERT",
    ) -> dict[str, Any]:
        profile = self._users.get_profile(admin_user_id) or {}
        if not profile.get("is_admin"):
            raise ValueError("NOT_ADMIN")

        exclude = self._trivia.get_used_question_fingerprints()
        q = self.generate_trivia_question(
            topic=topic,
            level=level,
            exclude_fingerprints=exclude,
        )
        trivia_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        item = self._trivia.put_broadcast_trivia(
            {
                "trivia_id": trivia_id,
                "type": "GENERAL",
                "level": level,
                "points": LEVEL_POINTS[level],
                "created_by": admin_user_id,
                "status": "SENT",
                "sent_at": now.isoformat(),
                "closes_at": (now + timedelta(hours=24)).isoformat(),
                **q,
            }
        )
        member_ids = self._trivia.list_group_member_user_ids(GLOBAL_GROUP_ID)
        targets = self._users.list_telegram_delivery_targets(member_ids)
        msg = self.format_question_message(item, header="📢 Trivia general del Prode")
        return {
            "trivia_id": trivia_id,
            "group_id": GLOBAL_GROUP_ID,
            "message": msg,
            "keyboard": self.answer_keyboard(trivia_id=trivia_id),
            "member_count": len(member_ids),
            "delivery_targets": targets,
        }

    def create_group_trivia_draft(
        self,
        owner_user_id: str,
        *,
        group_id: str | None,
        topic: str,
        level: str,
    ) -> dict[str, Any]:
        gid = group_id or self._groups.get_owner_group_id(owner_user_id)
        if not gid:
            raise ValueError("NO_GROUP")
        group = self._groups.get_group(gid) or {}
        if group.get("owner_id") != owner_user_id:
            profile = self._users.get_profile(owner_user_id) or {}
            if not profile.get("is_admin"):
                raise ValueError("NOT_OWNER")

        active = self._trivia.count_active_group_trivias(gid)
        if active >= MAX_ACTIVE_GROUP_TRIVIAS:
            raise ValueError("GROUP_TRIVIA_LIMIT")

        exclude = self._trivia.get_used_question_fingerprints()
        q = self.generate_trivia_question(
            topic=topic,
            level=level,
            exclude_fingerprints=exclude,
        )
        trivia_id = uuid.uuid4().hex[:8]
        preview = self.format_question_message(
            q,
            header=f"Vista previa — {LEVEL_LABELS.get(level, level)} ({LEVEL_POINTS[level]} pts)",
        )
        return {"trivia_id": trivia_id, "preview": preview, "question": q, "group_id": gid}

    def send_group_trivia(self, owner_user_id: str, trivia_id: str, question: dict[str, Any], group_id: str) -> dict:
        now = datetime.now(timezone.utc)
        item = self._trivia.put_broadcast_trivia(
            {
                "trivia_id": trivia_id,
                "type": "GROUP",
                "group_id": group_id,
                "level": question["level"],
                "points": LEVEL_POINTS[question["level"]],
                "created_by": owner_user_id,
                "status": "SENT",
                "sent_at": now.isoformat(),
                "closes_at": (now + timedelta(hours=24)).isoformat(),
                **question,
            }
        )
        member_ids = self._trivia.list_group_member_user_ids(group_id)
        targets = self._users.list_telegram_delivery_targets(member_ids)
        return {
            "trivia_id": trivia_id,
            "group_id": group_id,
            "message": self.format_question_message(item),
            "keyboard": self.answer_keyboard(trivia_id=trivia_id),
            "member_count": len(member_ids),
            "delivery_targets": targets,
        }

    def stats_for_trivia(self, trivia_id: str) -> str:
        t = self._trivia.get_trivia(trivia_id)
        if not t:
            return "Trivia no encontrada."
        total = int(t.get("total_answers") or 0)
        correct = int(t.get("correct_count") or 0)
        pct = (100.0 * correct / total) if total else 0.0
        return json.dumps(
            {
                "trivia_id": trivia_id,
                "total_answers": total,
                "correct_count": correct,
                "accuracy_pct": round(pct, 1),
            },
            ensure_ascii=False,
        )
