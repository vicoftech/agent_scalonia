# SPEC-2026-041 — Match Lifecycle Dev Sandbox (4 minutos)

| Campo | Valor |
|-------|--------|
| **SPEC-ID** | SPEC-2026-041 |
| **Estado** | Implementado — requiere `enable_match_lifecycle_sandbox` en dev |
| **Sprint objetivo** | Sprint 2 (dev tooling) |
| **Dependencias** | SPEC-2026-032 (modelo canónico, **no modificar**), SPEC-031, SPEC-022, SPEC-025, SPEC-021 |
| **Relación** | Complementa a [SPEC-2026-032](SPEC-2026-032-match-lifecycle-schedules.md); no lo reemplaza |

---

## 1. Problema

En desarrollo hace falta ver el **ciclo completo** de un partido (trivia → reminders → veda → resultado → scoring) de forma **automática y real**:

- EventBridge Scheduler (o equivalente)
- Lambdas desplegadas
- Colas SQS (`match_notifications`, `scoring`)
- Telegram vía `match_notify_dispatcher` (sin `--telegram-direct` ni scripts locales)

Esperar **más de 4 horas** por partido (offsets de producto) no es viable para iterar. Cambiar manualmente `kickoff_utc` y disparar Lambdas a mano tampoco valida el wiring end-to-end.

**SPEC-2026-032** define el scheduling **de producción** (offsets reales, alta de partido). Este SPEC define un **modo sandbox solo dev** que comprime la misma secuencia a **≈4–6 minutos**, sin solapar nombres ni semántica de 032.

---

## 2. Objetivo

Poder decir:

> “Marco un partido de prueba en `dev` como sandbox, invoco el manager una vez, y en ~5 minutos veo dispararse solo: trivia → 3 reminders → veda → resultado → scoring, todo por AWS (Scheduler + Lambdas + SQS + Telegram).”

Requisitos:

- Mismos **destinos** que prod (mismas Lambdas y colas).
- **No** altera partidos sin flag sandbox ni offsets de SPEC-032.
- Schedules de corta vida; cleanup explícito o automático.
- Desactivado en prod (`enable_match_lifecycle_sandbox=false`).

---

## 3. Alcance y no-alcance

### 3.1 En alcance

- Flag `sandbox_mode` en `MATCH#/DETAILS`.
- `MatchScheduleManager` (servicio + Lambda) con acciones `provision` / `cancel`.
- 7 schedules one-time con prefijo `devfast-*` (nombres distintos a los de 032).
- Offsets comprimidos desde `sandbox_started_at`.
- Terraform solo dev: Lambda manager + IAM Scheduler.
- Script CLI opcional: `scripts/provision_match_sandbox.py`.

### 3.2 Fuera de alcance

- Provisionar schedules **al ingest** con offsets reales → **SPEC-032**.
- Cambiar reglas de scoring, veda de producto o mensajes UX.
- Nuevos tipos de evento (solo comprimir los 7 ya definidos en 032).
- Reemplazar `scripts/simulate_match_lifecycle.py` (sigue útil para debug local sin AWS).

---

## 4. Diseño de alto nivel

### 4.1 Campos en DynamoDB (`MATCH#/DETAILS`)

| Campo | Tipo | Default | Uso |
|-------|------|---------|-----|
| `sandbox_mode` | `NONE` \| `DEV_FAST` | `NONE` | Solo partidos de prueba en dev |
| `sandbox_started_at` | ISO UTC | null | Origen de offsets comprimidos |

`kickoff_utc` real se conserva para textos de mensajes; **no** define cuándo disparan los schedules sandbox.

### 4.2 Componentes

```
scripts/provision_match_sandbox.py  (opcional)
        │
        ▼
Lambda match_schedule_manager  ──► EventBridge Scheduler API
        │                              (CreateSchedule / DeleteSchedule)
        ▼
7 schedules devfast-*  ──►  trivia_pre_match_dispatcher
                         match_reminder_dispatcher (tier 1–3)
                         veda_activator
                         result_collector (trigger=sandbox_devfast)
                         scoring_processor (vía SQS tras RESULT o catch-up)
```

### 4.3 Diferencia explícita con SPEC-032

| Aspecto | SPEC-032 (prod) | SPEC-041 (dev sandbox) |
|---------|-----------------|------------------------|
| Cuándo se crean | Alta/update de partido | Invocación manual o script |
| Referencia temporal | `kickoff_utc` | `sandbox_started_at` |
| Prefijo schedule | `trivia-pre-`, `veda-`, … | `devfast-*` |
| Duración ciclo | ~4+ horas | ~4–6 minutos |
| Entornos | prod + dev (futuro) | solo dev con flag Terraform |

---

## 5. Línea de tiempo comprimida (`DEV_FAST`)

A partir de `sandbox_started_at = now()` (UTC):

| # | Evento (032) | Offset prod (032) | Offset sandbox (041) |
|---|--------------|-------------------:|---------------------:|
| 1 | Trivia pre-partido | −120 min | **+0 s** |
| 2 | Reminder #1 | −60 min | **+60 s** |
| 3 | Reminder #2 | −30 min | **+120 s** |
| 4 | Reminder #3 | −15 min | **+150 s** |
| 5 | Veda | −30 min | **+180 s** |
| 6 | Resultado | +110 min | **+240 s** |
| 7 | Scoring catch-up | +120 min | **+270 s** |

La regla global `result_collector` `rate(5 minutes)` puede coexistir; el schedule `devfast-result-{match_id}` fuerza un disparo puntual para el partido sandbox.

---

## 6. Nombres de schedules (idempotencia)

Prefijo obligatorio: `prode-{env}-devfast-` + sufijo.

| # | Sufijo (041) | Equivalente prod (032) |
|---|--------------|-------------------------|
| 1 | `devfast-trivia-{match_id}` | `trivia-pre-{match_id}` |
| 2 | `devfast-remind1-{match_id}` | `remind-60-{match_id}` |
| 3 | `devfast-remind2-{match_id}` | `remind-30-{match_id}` |
| 4 | `devfast-remind3-{match_id}` | `remind-15-{match_id}` |
| 5 | `devfast-veda-{match_id}` | `veda-{match_id}` |
| 6 | `devfast-result-{match_id}` | `result-{match_id}` |
| 7 | `devfast-scoring-{match_id}` | `scoring-catchup-{match_id}` |

Si el nombre excede límite AWS: `devfast-{event}-{sha256(match_id)[:16]}` + registro en `JOB_CTRL#SCHEDULE#<match_id>` (mismo patrón que 032).

---

## 7. Targets y payloads

Cada schedule invoca la **misma Lambda** que en prod (032):

| Schedule | Target | Payload mínimo |
|----------|--------|----------------|
| devfast-trivia | `trivia_pre_match_dispatcher` | `{"match_id":"<uuid>","sandbox":true}` |
| devfast-remind1..3 | `match_reminder_dispatcher` | `{"match_id":"<uuid>","reminder_tier":1\|2\|3,"sandbox":true}` |
| devfast-veda | `veda_activator` | `{"match_id":"<uuid>","sandbox":true}` |
| devfast-result | `result_collector` | `{"match_id":"<uuid>","trigger":"sandbox_devfast"}` |
| devfast-scoring | `scoring_processor` o encolar SQS | Si no hay RESULT: no-op; si hay RESULT y `!result_processed`: `FINISH_MATCH` |

Cambios en Lambdas:

- Aceptar `sandbox: true` opcional (logging/métricas; **sin** cambiar reglas de negocio).
- `result_collector`: rama `trigger == "sandbox_devfast"` → `collect_result(match_id)` para ese partido.
- Reminders/veda/trivia: **no** usar `telegram_direct`; notificaciones vía colas donde aplique (resultado/scoring) o envío directo solo si la Lambda ya lo hace en prod sin cola (documentar por Lambda).

### 7.1 Prerrequisitos Terraform (dev)

```hcl
enable_result_collector         = true
enable_result_queues            = true
enable_match_lifecycle_sandbox  = true
```

Colas esperadas:

- `prode-match-notify-{env}` → `match_notify_dispatcher` → Telegram
- `prode-scoring-{env}` → `scoring_processor`

---

## 8. API — `MatchScheduleManager`

**Ubicación:** `src/services/match_schedule_manager.py`

```python
class MatchScheduleManager:
    def provision_sandbox_schedules(self, match_id: str, *, mode: str = "DEV_FAST") -> dict: ...
    def cancel_sandbox_schedules(self, match_id: str) -> dict: ...
```

**Lambda:** `infrastructure/lambdas/match_schedule_manager/handler.py`

```json
{ "action": "provision", "match_id": "<uuid>", "mode": "DEV_FAST" }
{ "action": "cancel", "match_id": "<uuid>" }
```

**Comportamiento `provision`:**

1. Validar `env` permite sandbox.
2. `get_match(match_id)`; error si no existe.
3. `UpdateItem`: `sandbox_mode=DEV_FAST`, `sandbox_started_at=now`.
4. Calcular 7 `at(yyyy-mm-ddThh:mm:ss)` UTC desde tabla §5.
5. `CreateSchedule` idempotente (si existe → `UpdateSchedule`).
6. Retornar `{ "status": "OK", "schedules": [ { "name", "at" }, ... ] }`.

**Comportamiento `cancel`:**

1. `DeleteSchedule` para los 7 `devfast-*` (ignorar `ResourceNotFound`).
2. Opcional: `sandbox_mode=NONE`, limpiar `sandbox_started_at`.

---

## 9. Terraform

**Archivo:** `infrastructure/terraform/match_lifecycle_sandbox.tf`

**Variable:**

```hcl
variable "enable_match_lifecycle_sandbox" {
  type        = bool
  default     = false
  description = "Lambda match_schedule_manager + permisos Scheduler (solo dev)."
}
```

**Recursos:**

- `aws_lambda_function.match_schedule_manager` (count = flag).
- IAM: `scheduler:CreateSchedule`, `UpdateSchedule`, `DeleteSchedule`, `GetSchedule`, `ListSchedules`; `lambda:InvokeFunction` en targets; DynamoDB read/write en tabla Prode.
- **No** crear los 7 schedules en Terraform; solo el manager los crea vía API.

**Outputs:**

- `match_schedule_manager_function_name`

---

## 10. Flujo de uso en dev

```bash
# 1. Partido de prueba ya en Dynamo (ej. MEX vs RSA)
export AWS_PROFILE=asap_dev

# 2. Provisionar sandbox (~5 min de ciclo)
python scripts/provision_match_sandbox.py \
  --match-id <uuid> \
  --profile asap_dev \
  --action provision

# 3. Esperar ~5 min; revisar Telegram y CloudWatch

# 4. Limpiar schedules
python scripts/provision_match_sandbox.py \
  --match-id <uuid> \
  --profile asap_dev \
  --action cancel
```

Equivalente AWS CLI:

```bash
aws lambda invoke \
  --function-name prode-match-schedule-manager-dev \
  --payload '{"action":"provision","match_id":"<uuid>","mode":"DEV_FAST"}' \
  out.json
```

---

## 11. Idempotencia y seguridad

- `provision` dos veces con el mismo `match_id`: actualiza horarios si cambió `sandbox_started_at`; no duplica schedules.
- `cancel` idempotente.
- **Nunca** crear/editar schedules sin prefijo `devfast-` desde este manager.
- **Nunca** habilitar `enable_match_lifecycle_sandbox` en `env=prod`.
- No loguear `platform_id` ni tokens.

---

## 12. Observabilidad

- Log estructurado en manager: `match_id`, acción, lista `{name, at}`.
- Métrica opcional: `MatchLifecycleSandbox.Provisioned`, `MatchLifecycleSandbox.Cancelled`.
- Lambdas target: log `sandbox=true` cuando venga en payload.

---

## 13. Criterios de aceptación (Gherkin)

```gherkin
Feature: Match lifecycle dev sandbox

  Scenario SC-01 — Provisionar sandbox
    Dado un partido en dev con sandbox_mode NONE
    Cuando invoco provision con mode DEV_FAST
    Entonces existen 7 schedules devfast-* en Scheduler
    Y sandbox_mode es DEV_FAST en DynamoDB

  Scenario SC-02 — Secuencia comprimida
    Dado sandbox provisionado hace menos de 1 minuto
    Cuando pasan 5 minutos
    Entonces se ejecutaron trivia, 3 reminders, veda, result y scoring catch-up
    Y las notificaciones de resultado llegaron por SQS match_notifications

  Scenario SC-03 — Sin solapamiento con 032
    Dado schedules prod trivia-pre-{match_id} (futuro)
    Cuando provisiono sandbox para el mismo match_id
    Entonces no se modifican los schedules sin prefijo devfast-

  Scenario SC-04 — Cancel
    Cuando invoco cancel
    Entonces no quedan schedules devfast-* para ese match_id

  Scenario SC-05 — Prod bloqueado
    Dado env prod y enable_match_lifecycle_sandbox false
    Cuando invoco provision
    Entonces error o no-op documentado
```

---

## 14. Tareas de implementación

| ID | Tarea | Archivos |
|----|-------|----------|
| TASK-041-001 | Campos `sandbox_mode`, `sandbox_started_at` en match_dao + ingest opcional | `match_dao.py` |
| TASK-041-002 | `MatchScheduleManager` + unit tests offsets | `match_schedule_manager.py`, `tests/unit/` |
| TASK-041-003 | Lambda `match_schedule_manager` | `infrastructure/lambdas/match_schedule_manager/` |
| TASK-041-004 | Terraform sandbox + IAM Scheduler | `match_lifecycle_sandbox.tf` |
| TASK-041-005 | `result_collector` trigger `sandbox_devfast` | `handler.py`, `result_collector_service` |
| TASK-041-006 | Flag `sandbox` en lambdas lifecycle (log) | trivia, reminder, veda handlers |
| TASK-041-007 | CLI `provision_match_sandbox.py` | `scripts/` |
| TASK-041-008 | Documentar en README dev / runbook | `infrastructure/terraform/README.md` |

---

## 15. Reglas NUNCA

- NO usar prefijos de schedule de SPEC-032 (`trivia-pre-`, `veda-`, etc.) en modo sandbox.
- NO habilitar sandbox en producción.
- NO depender de `--telegram-direct` para validar este flujo (debe usar colas donde 031/022 lo definan).
- NO cambiar offsets de producto en 032 por conveniencia de dev.

---

## 16. Referencias

- [SPEC-2026-032 — Schedules por partido (prod)](SPEC-2026-032-match-lifecycle-schedules.md)
- `.cursor/rules/11-predictions.mdc` — veda, reminders
- `.cursor/rules/15-trivias.mdc` — trivia pre-partido
- `.cursor/rules/21-result-collector.mdc` — resultado
- `infrastructure/terraform/result_collector.tf` — colas y collector
- `scripts/simulate_match_lifecycle.py` — simulación local (complementaria, no sustituta)
