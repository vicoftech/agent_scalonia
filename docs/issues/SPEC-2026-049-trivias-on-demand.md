# SPEC-2026-049 — Trivias on-demand (KB / web_search, niveles, límites, deduplicación)

| Campo | Valor |
|-------|--------|
| **SPEC-ID** | SPEC-2026-049 |
| **Tipo** | Bugfix + realineación con SPEC-025 |
| **Estado** | **Implementado** |
| **Sprint** | Post SPEC-048 |
| **Extiende / corrige** | [SPEC-2026-025](../.cursor/rules/15-trivias.mdc) (diseño original LLM+KB) |
| **Depende de** | SPEC-017 (KB + `resolve_kb_then_web`), SPEC-019 (`football_knowledge`), SPEC-032 (fixture partidos), `trivia_kb_generator.py` |
| **Síntoma reportado** | Admin: `/trivia-admin` → «Ya usamos todas las preguntas del banco…». Usuario: `/trivia` → «Por hoy no quedan preguntas nuevas…» o «Ya jugaste tus 5 rondas…» |
| **Componentes** | `trivia_service.py`, `trivia_kb_generator.py` (generalizar), `trivia_dao.py`, `trivia_commands.py`, `agent/tools/trivia_tool.py`, tests `tests/unit/test_trivia/` |

---

## 1. Problema (as-built)

### 1.1 Síntomas en producción / dev

| Actor | Acción | Mensaje actual | Expectativa |
|-------|--------|----------------|-------------|
| Usuario | `/trivia` o botón 🎯 Trivia | «Por hoy no quedan preguntas nuevas para vos en el banco…» | Nueva pregunta calibrada a su nivel (Casual / Fanático / Experto) |
| Usuario | Responder broadcast / daily | «Ya jugaste tus 5 rondas de trivia hoy…» | Correcto si ya consumió 5 rondas; no confundir con banco agotado |
| Admin | `/trivia-admin records` | «Ya usamos todas las preguntas del banco…» | Generar y publicar sin límite de banco ni de rondas diarias |

### 1.2 Causa raíz (código actual)

| # | Gap | Evidencia | Impacto |
|---|-----|-----------|---------|
| G1 | **Generación no es on-demand** | `TriviaService.generate_trivia_question()` solo llama `pick_curated_question()` sobre `FALLBACK_QUESTIONS` (~12 ítems en `src/fixtures/trivia_questions.py`) | El banco se agota en minutos; `TRIVIA_BANK_EXHAUSTED` |
| G2 | **KB/web existen pero no se usan en `/trivia`** | `_fetch_context()` y `resolve_kb_then_web` están implementados pero **no** se invocan desde `generate_trivia_question()` | Desalineación total con SPEC-025 y regla `15-trivias.mdc` |
| G3 | **Pre-partido sí usa LLM; play no** | `trivia_kb_generator.generate_pre_match_question()` → KB → Bedrock → fallback | Solo el flujo automático pre-partido cumple el diseño |
| G4 | **Registro global de fingerprints pequeño** | `CONFIG#TRIVIA / USED_QUESTION_FPS`, máx. **500** entradas, compartido por play + admin + daily + pre-partido | Tras pocas sesiones de prueba, todas las preguntas curadas quedan excluidas |
| G5 | **Exclusión por usuario amplia** | `_exclude_fingerprints(user_id)` = registry global **∪** fingerprints ya respondidos por el usuario | Con banco de 12 preguntas, un usuario que respondió 5 en onboarding agota opciones al pedir `/trivia` |
| G6 | **Admin no exento del límite diario** | `_ensure_can_play()` se aplica a `start_play` y `answer_broadcast` sin chequear `is_admin` | Admin puede ver DAILY_LIMIT al responder trivias broadcast aunque deba ser ilimitado en **generación** y **juego** |
| G7 | **Nivel admin fijo EXPERT** | `/trivia-admin` siempre `level="EXPERT"` | Aceptable para broadcast global; play personal sí debe respetar perfil |
| G8 | **Etiquetas UX vs internas** | Perfil: Casual / Fanático / Enciclopedia (`easy`/`medium`/`hard`) → `BASIC`/`MEDIUM`/`EXPERT` | Mapping existe en `PROFILE_TO_LEVEL`; falta generación LLM por nivel |

### 1.3 Diagrama — flujo actual vs deseado

```mermaid
flowchart TD
  subgraph actual [As-built /trivia play]
    A1[/trivia] --> B1[pick_curated_question]
    B1 --> C1{¿Queda en FALLBACK?}
    C1 -->|No| D1[TRIVIA_BANK_EXHAUSTED]
    C1 -->|Sí| E1[Sesión play]
  end

  subgraph deseado [SPEC-049]
    A2[/trivia] --> B2[resolve_kb_then_web por tema]
    B2 --> C2[Bedrock: 1 MCQ verificable]
    C2 --> D2{fingerprint único?}
    D2 -->|No| C2
    D2 -->|Sí| E2[Registrar fp + sesión]
    C2 -->|falla| F2[FALLBACK curado acotado]
  end
```

---

## 2. Requisitos de producto (mandatorios)

| ID | Requisito | Detalle |
|----|-----------|---------|
| **R1** | **Generación a demanda** | Cada trivia nueva se genera en el momento desde contexto KB (`resolve_kb_then_web`) y, si el contexto es insuficiente (< ~80 chars útiles), complementar con **web_search** (Tavily). El banco `FALLBACK_QUESTIONS` queda como **último recurso**, no como fuente principal. |
| **R2** | **Respetar nivel del perfil** | Mapeo canónico onboarding → generación → puntos: **Casual** (`easy`) → `BASIC` (+1 pt), **Fanático** (`medium`) → `MEDIUM` (+3 pts), **Experto / Enciclopedia** (`hard`) → `EXPERT` (+5 pts). El prompt Bedrock debe indicar dificultad (hechos obvios vs estadísticas vs curiosidades raras). |
| **R3** | **5 trivias/día por usuario; admin ilimitado** | Contador `trivia_rounds_today` en `USER#/PROFILE`, reset diario ART (misma convención que jobs). **Admin global** (`is_admin=true`): sin límite en `start_play`, `answer_play_session`, `answer_broadcast` ni al publicar `/trivia-admin`. |
| **R4** | **Hash anti-repetición** | Toda pregunta generada o curada expone `question_fp = SHA256(normalize(question))`. Antes de servir: excluir fps del registry global y del set por usuario. Tras publicar/responder: `register_question_fingerprint`. Reintentar generación (máx. 3) si colisiona. |
| **R5** | **Pre-partido con contexto de ambas selecciones** | Trivia `PRE_MATCH` debe anclarse a **home_team** y **away_team** (nombres FIFA + display names), con contexto KB/web que cubra **ambos** equipos. Validación ya existente en `_question_references_match()` — mantener y aplicar también si se refactoriza el generador. |

---

## 3. Objetivos

1. Eliminar `TRIVIA_BANK_EXHAUSTED` en uso normal (admin y usuarios con rondas disponibles).
2. Unificar pipeline de generación: **play**, **daily general**, **admin general**, **grupo owner** y **pre-partido** comparten el mismo núcleo LLM+KB.
3. Mensajes de error distinguibles: límite diario vs fallo de generación vs trivia cerrada.
4. Mantener arquitectura híbrida: escrituras DynamoDB; sync Aurora vía streams existente en `TRIVIA_ANSWER#`.
5. Tests unitarios que mockeen Bedrock/KB y validen niveles, límites admin y deduplicación.

---

## 4. Alcance

**Incluye**

- Refactor `generate_trivia_question()` → pipeline on-demand.
- Extraer `generate_question_from_context()` genérico (tema + nivel + contexto + exclude_fps) desde lógica de `trivia_kb_generator.py`.
- Exención admin en `_ensure_can_play()` y en UI de rondas restantes.
- Ajuste registry: política de retención (§7.3) y/o partición por usuario para play personal.
- Mensajes Telegram claros en `trivia_commands.py`.
- Regresión en `tests/unit/test_trivia/`.

**No incluye (MVP de esta spec)**

- Flujo admin con vista previa + botones Regenerar/Enviar (SPEC-025 § Tipo 1) — hoy `/trivia-admin` publica directo; se puede iterar en SPEC posterior.
- Sincronización Aurora de preguntas generadas (solo respuestas ya sincronizan).
- Trivias multijugador en tiempo real.

---

## 5. Diseño — pipeline de generación

### 5.1 Entrada unificada

```python
def generate_trivia_question(
    *,
    topic: str = "mundiales",
    level: str = "MEDIUM",
    match: dict | None = None,
    user_id: str | None = None,
    exclude_fingerprints: set[str] | None = None,
) -> dict[str, Any]:
    """
    1. exclude = global registry ∪ user answered ∪ param
    2. context = fetch_context(topic, match=match)  # resolve_kb_then_web
    3. for attempt in 1..3:
         q = generate_question_from_context(context, level, topic, match, exclude)
         if q and q.question_fp not in exclude: return q
    4. q = pick_curated_question(...) con mismo exclude
    5. if not q: raise GENERATION_FAILED (no TRIVIA_BANK_EXHAUSTED salvo ops)
    """
```

### 5.2 Contexto KB / web

| Tipo | Query base | Match |
|------|------------|-------|
| Play `/trivia` | `TOPIC_QUERIES[topic]` | — |
| Daily general | `historias_mundiales` | — |
| Admin `/trivia-admin` | `TOPIC_QUERIES[topic]` | — |
| Pre-partido | `fetch_pre_match_kb_context(match)` | **obligatorio** — incluye blurb `{home} vs {away}` + búsquedas por equipo |

Reutilizar `src/kb/resolve.py::resolve_kb_then_web` con `enqueue_on_web=False` en Lambda webhook (latencia < 3s p95 objetivo; timeout Bedrock acotado).

### 5.3 Prompt Bedrock (play / general)

Parámetros por nivel en el system prompt:

| Nivel | Instrucción al modelo |
|-------|------------------------|
| BASIC | Hecho ampliamente conocido; opciones claramente distinguibles |
| MEDIUM | Estadística, fecha o dato específico del contexto |
| EXPERT | Curiosidad rara, récord poco conocido; distractors plausibles |

Salida JSON obligatoria (igual que pre-partido):

```json
{
  "question": "...",
  "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "correct": "A",
  "explanation": "..."
}
```

Validaciones post-LLM:

- `correct ∈ {A,B,C,D}`; las 4 opciones no vacías.
- `is_meta_source_question()` → rechazar.
- Pre-partido: `_question_references_match(question, home, away)`.
- `question_fp` no ∈ exclude → si colisiona, reintentar con `temperature` ligeramente mayor o reformular prompt.

`source`: `kb_bedrock` | `web_bedrock` | `manual` (fallback).

### 5.4 Fallback curado

Orden de degradación:

1. LLM + contexto KB
2. LLM + contexto web (si KB < umbral)
3. `pick_curated_question` / `pick_any_curated_question`
4. Error `GENERATION_FAILED` con log estructurado (no culpar al «banco» al usuario)

---

## 6. Límites diarios y admin

### 6.1 Contador

| Campo PROFILE | Semántica |
|---------------|-----------|
| `trivia_rounds_today` | Rondas consumidas hoy (ART) |
| `trivia_rounds_date` | Fecha ART del contador (reset si `!= hoy`) |

Incremento en `add_trivia_round()` al **responder** (play session o broadcast), no al mostrar pregunta — comportamiento actual, mantener.

### 6.2 Reglas

```python
def _ensure_can_play(self, user_id: str) -> None:
    profile = self._users.get_profile(user_id) or {}
    if profile.get("is_admin"):
        return
    if self.rounds_remaining(user_id) <= 0:
        raise ValueError("DAILY_LIMIT")
```

| Flujo | Usuario normal | Admin |
|-------|----------------|-------|
| `/trivia` start | ≤ 5/día | Ilimitado |
| Responder play (`trv:s:`) | Cuenta ronda | No cuenta límite (o no incrementar si se prefiere métricas separadas — **decisión: admin ilimitado, sí incrementar contador para stats pero sin bloquear**) |
| Responder broadcast (`trv:t:`) | ≤ 5/día | Ilimitado |
| `/trivia-admin` publicar | N/A | Sin límite de generación |

**Decisión producto:** admin **nunca** ve `DAILY_LIMIT`; puede seguir acumulando `trivia_rounds_today` para analytics pero `rounds_remaining` muestra «∞» o omite el pie en mensajes admin.

### 6.3 Mensajes UX

| Código | Usuario | Admin |
|--------|---------|-------|
| `DAILY_LIMIT` | «Ya jugaste tus 5 trivias de hoy. Volvé mañana 🌙» | *(no debería ocurrir)* |
| `GENERATION_FAILED` | «No pude generar una pregunta nueva ahora. Probá en unos minutos.» | Igual + sugerir otro tema |
| ~~`TRIVIA_BANK_EXHAUSTED`~~ | Deprecar en favor de `GENERATION_FAILED` | Idem |

---

## 7. Deduplicación (fingerprints)

### 7.1 Función

```python
def question_fingerprint(question: str) -> str:
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]
```

Ya implementada en `trivia_question_bank.py` — no cambiar algoritmo (invalidaría registry existente).

### 7.2 Stores

| Store | PK/SK | Uso |
|-------|-------|-----|
| Global | `CONFIG#TRIVIA` / `USED_QUESTION_FPS` | Preguntas ya **asignadas** (play, broadcast, daily) |
| Por usuario | `USER#<uuid>` / `TRIVIA_FP#<fp>` o lista en PROFILE | Preguntas ya **respondidas** (evitar puntos duplicados) |

### 7.3 Política de retención global (fix G4)

Problema: lista FIFO de 500 fps borra antiguos pero **sigue bloqueando** mientras están en la lista; con banco estático agota todo.

Con generación on-demand:

- Mantener registry global para ventana **90 días** o **últimos 2000 fps** (subir `MAX_REGISTRY_FINGERPRINTS`).
- Opcional: particionar play personal — excluir solo fps del usuario + fps globales de **últimas 72 h** para broadcasts, no todo el histórico de play LLM.

**Migración dev:** script one-shot `scripts/reset_trivia_fingerprint_registry.py` (solo dev) para desbloquear QA; **no** incluir en prod sin backup.

---

## 8. Pre-partido (R5)

Sin cambio funcional mayor; **verificar** que el refactor no rompa:

1. `fetch_pre_match_kb_context(match)` consulta KB para **home** y **away** por separado y concatena.
2. Prompt exige mención de ambos equipos.
3. `_question_references_match()` rechaza preguntas genéricas.
4. Fallback `pick_curated_for_match_strict` antes de `fixture_template`.
5. Header Telegram: `⚽ TRIVIA PRE-PARTIDO … {home} vs {away}`.

Nivel pre-partido broadcast: **EXPERT** (5 pts) — sin relación con `football_knowledge` del receptor (comportamiento SPEC-025).

---

## 9. Flujos Telegram (sin cambio de comandos)

| Comando | Generación | Nivel |
|---------|------------|-------|
| `/trivia` | On-demand tema `mundiales` | Perfil usuario |
| `/trivia-admin [tema]` | On-demand | EXPERT (broadcast) |
| `/trivia-grupo [tema]` | On-demand | MEDIUM default owner |
| Daily job | On-demand `historias_mundiales` | MEDIUM |
| Pre-partido scheduler | On-demand con `match` | EXPERT |

---

## 10. Criterios de aceptación

### 10.1 Gherkin

```gherkin
Feature: Trivias on-demand SPEC-049

  Scenario: Usuario Casual recibe pregunta BASIC
    Given usuario ACTIVE con football_knowledge=easy y trivia_rounds_today=0
    When invoca /trivia
    Then recibe pregunta con level BASIC y source kb_bedrock o web_bedrock
    And question_fp se registra en CONFIG#TRIVIA

  Scenario: Quinta ronda del día bloqueada
    Given trivia_rounds_today=5 y no es admin
    When invoca /trivia
    Then mensaje DAILY_LIMIT
    And no se crea sesión play

  Scenario: Admin ilimitado
    Given usuario con is_admin=true y trivia_rounds_today=10
    When invoca /trivia
    Then recibe nueva pregunta
    And no ve DAILY_LIMIT

  Scenario: Admin publica general
    Given admin ACTIVE
    When /trivia-admin records
    Then broadcast creado aunque registry tenga >500 fps
    And miembros reciben trivia EXPERT

  Scenario: No repetir pregunta respondida
    Given usuario ya respondió pregunta con fp=X
    When generación propone fp=X
    Then se reintenta hasta 3 veces o pasa a otra pregunta

  Scenario: Pre-partido menciona ambos equipos
    Given partido ARG vs MEX
    When dispatch_pre_match_trivia
    Then question contiene referencia a Argentina y México (o códigos)
```

### 10.2 Tests unitarios mínimos

| Test | Assert |
|------|--------|
| `test_generate_uses_kb_not_only_fallback` | Mock Bedrock → source `kb_bedrock` |
| `test_level_maps_casual_fanatico_experto` | easy→BASIC, medium→MEDIUM, hard→EXPERT |
| `test_admin_skips_daily_limit` | 6ª ronda OK para admin |
| `test_fingerprint_retry_on_collision` | Segunda llamada distinta si fp repetido |
| `test_pre_match_requires_both_teams` | Rechazo si prompt no menciona away |

---

## 11. Plan de implementación

| Paso | Archivo | Cambio |
|------|---------|--------|
| 1 | `src/services/trivia_kb_generator.py` | Renombrar/generalizar → `generate_question_from_context(topic, level, context, match?, exclude)` |
| 2 | `src/services/trivia_service.py` | Rewire `generate_trivia_question`; usar `_fetch_context`; admin bypass en `_ensure_can_play` y mensajes |
| 3 | `src/dao/dynamo/trivia_dao.py` | Subir `MAX_REGISTRY_FINGERPRINTS` o TTL lógico documentado |
| 4 | `infrastructure/lambdas/telegram_webhook/trivia_commands.py` | Mensajes `GENERATION_FAILED`; admin sin confusión banco/límite |
| 5 | `agent/tools/trivia_tool.py` | Alinear errores con servicio |
| 6 | `tests/unit/test_trivia/` | Casos §10.2 |
| 7 | `.cursor/rules/15-trivias.mdc` | Nota «implementado SPEC-049» en generación |
| 8 | Ops dev | Opcional reset registry para QA |

---

## 12. Observabilidad

| Log | Campos |
|-----|--------|
| `trivia_generated` | `user_id` (prefix), `level`, `topic`, `source`, `question_fp`, `attempt` |
| `trivia_generation_failed` | `reason`, `topic`, `level`, `context_len` |

No loggear texto completo de pregunta en prod (PII baja pero ruido); sí fingerprint.

---

## 13. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Latencia Bedrock > 3s | Timeout 8s; fallback curado; cache contexto por tema 5 min en Dynamo `CACHE#` |
| Alucinación LLM | Prompt «solo hechos del contexto»; explanation obligatoria; fallback manual |
| Costo Bedrock | Máx. 3 reintentos; admin rate soft 20/h vía CloudWatch alarm (fuera de MVP) |
| Registry grande | Cap 2000 + ventana temporal |

---

## 14. Definition of Done

- [x] Usuario con rondas disponibles **siempre** recibe pregunta en `/trivia` (salvo outage Bedrock).
- [x] Admin publica `/trivia-admin` sin `TRIVIA_BANK_EXHAUSTED` en condiciones normales.
- [x] Nivel alineado a Casual / Fanático / Experto del perfil.
- [x] 5 rondas/día enforced; admin exento.
- [x] `question_fp` en toda pregunta nueva; no repetición para mismo usuario.
- [x] Pre-partido valida contexto dual de selecciones.
- [x] Tests unitarios verdes.
- [ ] Manual dev: borrar registry + probar 10 `/trivia` consecutivos sin agotar.

---

## 15. Referencias

- Regla steering: `.cursor/rules/15-trivias.mdc`
- Generador pre-partido: `src/services/trivia_kb_generator.py`
- Servicio: `src/services/trivia_service.py` — `generate_trivia_question` (líneas 120–148) hoy solo curado
- DAO registry: `src/dao/dynamo/trivia_dao.py` — `MAX_REGISTRY_FINGERPRINTS = 500`
- Onboarding niveles: `.cursor/rules/09-onboarding.mdc` § M2b
