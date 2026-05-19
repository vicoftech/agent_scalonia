"""Sistema de trivias SPEC-2026-025."""
from __future__ import annotations

import json
import logging
import re
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
from src.fixtures.trivia_questions import FALLBACK_QUESTIONS

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

TRIVIA_SECTION = """
## Trivias (SPEC-025)
- /trivia o trivia_tool action=play: una ronda (máx 5/día). Opciones A/B/C/D solo vía botones en Telegram.
- action=answer con session_id o trivia_id + answer A|B|C|D.
- Trivia diaria general (historias de mundiales): ~10:00 Argentina o 2 h antes del primer partido del día; el usuario la ve al escribir al bot.
- Sin penalización por error. Puntos: Básico +1, Intermedio +3, Experto +5.
- Generación: usá contexto KB/web; trivia_tool play elige nivel según football_knowledge del perfil.
""".strip()


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

    def rounds_remaining(self, user_id: str) -> int:
        profile = self._users.get_profile(user_id) or {}
        used = int(profile.get("trivia_rounds_today") or 0)
        return max(0, MAX_ROUNDS_PER_DAY - used)

    def _ensure_can_play(self, user_id: str) -> None:
        if self.rounds_remaining(user_id) <= 0:
            raise ValueError("DAILY_LIMIT")

    def _fetch_context(self, topic: str, *, match: dict | None = None) -> str:
        topic_key = (topic or "mundiales").lower()
        base = TOPIC_QUERIES.get(topic_key, TOPIC_QUERIES["mundiales"])
        if match:
            base = f"{match.get('home_team')} {match.get('away_team')} {base}"
        try:
            from src.kb.resolve import resolve_kb_web

            result = resolve_kb_web(query=base, caller_user_id="trivia-generator")
            text = (result.kb_text or "").strip()
            if len(text) < 80 and result.tavily_configured:
                text = (result.web_text or text or "").strip()
            return text[:4000]
        except Exception:
            logger.exception("trivia context fetch failed")
            return ""

    def generate_trivia_question(
        self,
        *,
        topic: str = "mundiales",
        level: str = "MEDIUM",
        context: str | None = None,
        match: dict | None = None,
    ) -> dict[str, Any]:
        level = level.upper() if level.upper() in LEVEL_POINTS else "MEDIUM"
        ctx = context if context is not None else self._fetch_context(topic, match=match)

        topic_key = (topic or "mundiales").lower()
        for q in FALLBACK_QUESTIONS:
            if q["level"] == level and q["topic"] == topic_key:
                return dict(q)
        for q in FALLBACK_QUESTIONS:
            if q["level"] == level and (topic_key == q["topic"] or topic_key == "libre"):
                return dict(q)

        if ctx:
            parsed = self._question_from_context(ctx, level=level, topic=topic)
            if parsed:
                return parsed

        return dict(FALLBACK_QUESTIONS[0])

    def _question_from_context(self, context: str, *, level: str, topic: str) -> dict | None:
        """Heurística simple: pregunta tipo '¿Cuál de estos datos es correcto?' con fragmentos."""
        sentences = [s.strip() for s in re.split(r"[.!?]\s+", context) if len(s) > 20]
        if len(sentences) < 2:
            return None
        fact = sentences[0][:200]
        distractors = [s[:80] for s in sentences[1:4]]
        while len(distractors) < 3:
            distractors.append("Ninguna de las anteriores")
        options = {"A": fact, "B": distractors[0], "C": distractors[1], "D": distractors[2]}
        return {
            "topic": topic,
            "level": level,
            "question": f"Según el contexto del Mundial, ¿cuál afirmación es la más precisa?",
            "options": options,
            "correct": "A",
            "explanation": fact,
            "source": "KB",
            "verified": True,
        }

    def generate_pre_match_trivia(self, match: dict[str, Any]) -> dict[str, Any]:
        topic = "pre_partido"
        home = match.get("home_team", "")
        away = match.get("away_team", "")
        q = self.generate_trivia_question(
            topic="selecciones",
            level="EXPERT",
            match=match,
        )
        q["question"] = (
            f"Pre-partido {home} vs {away}: "
            + q["question"]
        )
        q["match_id"] = match.get("match_id")
        return q

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
        q = self.generate_trivia_question(topic=topic, level=lvl)
        session_id = str(uuid.uuid4())
        record = {
            "session_id": session_id,
            "user_id": user_id,
            "level": lvl,
            "points": LEVEL_POINTS[lvl],
            **q,
        }
        self._trivia.put_play_session(record)
        msg = self.format_question_message(q)
        remaining = self.rounds_remaining(user_id) - 1
        msg += f"\n\n📊 Rondas restantes hoy: {max(0, remaining)}/{MAX_ROUNDS_PER_DAY}"
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

        self._trivia.complete_play_session(
            user_id,
            session_id,
            answer=letter,
            is_correct=is_correct,
            points_earned=pts,
        )
        self._users.add_trivia_round(user_id, points=pts)

        return self._format_answer_result(
            is_correct=is_correct,
            points=pts,
            correct_letter=correct_letter,
            options=session.get("options_map") or {},
            explanation=session.get("explanation", ""),
            user_id=user_id,
        )

    def answer_broadcast(self, user_id: str, trivia_id: str, answer: str) -> str:
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
        pts = int(trivia.get("points") or 0) if is_correct else 0

        self._trivia.put_answer(
            trivia_id=trivia_id,
            user_id=user_id,
            answer=letter,
            is_correct=is_correct,
            points=pts,
        )
        self._trivia.increment_trivia_stats(trivia_id, correct=is_correct)
        if pts:
            self._users.add_trivia_round(user_id, points=pts, count_round=False)

        return self._format_answer_result(
            is_correct=is_correct,
            points=pts,
            correct_letter=correct,
            options=trivia.get("options") or {},
            explanation=trivia.get("explanation", ""),
            user_id=user_id,
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
    ) -> str:
        opt_text = options.get(correct_letter, "")
        profile = self._users.get_profile(user_id) or {}
        total = int(profile.get("total_points") or 0)
        remaining = self.rounds_remaining(user_id)

        if is_correct:
            head = f"✅ ¡Correcto! +{points} pts\n\nLa respuesta era {correct_letter}"
        else:
            head = f"❌ Incorrecto — sin puntos esta vez\n\nLa respuesta correcta era {correct_letter}"

        if opt_text:
            head += f" — {opt_text}"
        if explanation:
            head += f"\n\n{explanation}"
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

        q = self.generate_trivia_question(
            topic=DAILY_GENERAL_TOPIC,
            level=DAILY_GENERAL_LEVEL,
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

        q = self.generate_trivia_question(topic=topic, level=level)
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

        q = self.generate_trivia_question(topic=topic, level=level)
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
