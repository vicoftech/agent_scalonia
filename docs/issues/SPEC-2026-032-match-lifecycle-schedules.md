# SPEC-2026-032 — Schedules por partido (EventBridge Scheduler)

| Campo | Valor |
|-------|--------|
| **SPEC-ID** | SPEC-2026-032 |
| **Estado** | Implementado (código + Terraform); requiere `terraform apply` + backfill schedules |
| **Sprint objetivo** | Sprint 2–3 |
| **Dependencias** | SPEC-021 (predicciones/reminders), SPEC-025 (trivia pre-partido), SPEC-031 (resultados), SPEC-022 (scoring), ADR-005 (veda) |

---

## 1. Problema

Hoy, al dar de alta un partido (`ingest_matches` → `MATCH#/DETAILS`), **no** se crean schedules en EventBridge Scheduler. Solo existen reglas **globales** (p. ej. `result_collector` cada 5 min).

Esto impide disparar de forma puntual y predecible:

- Trivia pre-partido  
- Recordatorios sin predicción  
- Veda  
- Recolección de resultado y scoring  

## 2. Objetivo

**Al crear o actualizar** un partido con `kickoff_utc` válido, el sistema debe **provisionar (crear o actualizar) exactamente 7 schedules one-time** por `match_id`, con nombres determinísticos e idempotentes.

Al **cancelar** o **reemplazar** el fixture del partido, se deben **eliminar** los schedules asociados.

## 3. Línea de tiempo (referencia: `kickoff_utc`)

```
kickoff = T0 (UTC)

  T-120 min ──► (1) Trivia pre-partido
  T-60 min  ──► (2) Reminder #1 (solo sin predicción)
  T-30 min  ──► (3) Reminder #2 (solo sin predicción)
                (5) Veda activa (todos los usuarios / grupos)
  T-15 min  ──► (4) Reminder #3 (solo sin predicción)
  T0        ──► inicio del partido (no hay schedule)
  T+110 min ──► (6) After match — recolectar resultado (estimado fin 90'+descanso)
  T+result  ──► (7) Scoring — encadenado al guardar RESULT (SQS); catch-up schedule opcional
```

> **Nota:** La veda de producto sigue siendo **30 min antes del kickoff** (ADR-005), alineada con el Reminder #2. Los recordatorios #1–#3 usan los offsets pedidos respecto al **kickoff**, no respecto a la veda (actualiza SPEC-021 flujo 9 que hablaba de 30/20/10 min antes de la veda).

## 4. Los 7 eventos por partido

| # | Evento | Offset vs `kickoff_utc` | Lambda / destino | Condición en runtime |
|---|--------|-------------------------|------------------|----------------------|
| 1 | **Trivia pre-partido** | **−120 min** | `trivia_pre_match_dispatcher` | Usuarios GLOBAL con `notifications_enabled` |
| 2 | **Reminder #1** | **−60 min** | `match_reminder_dispatcher` | Usuario **sin** predicción ACTIVE en el grupo activo |
| 3 | **Reminder #2** | **−30 min** | `match_reminder_dispatcher` | Idem |
| 4 | **Reminder #3** | **−15 min** | `match_reminder_dispatcher` | Idem |
| 5 | **Veda** | **−30 min** | `veda_activator` | Siempre: `veda_active=true` en `MATCH#/DETAILS` + notificación |
| 6 | **After match (resultados)** | **+110 min** | `result_collector` (`trigger=match_ended`) | Si no hay RESULT completo; reintentos vía collector global |
| 7 | **Scoring** | Tras (6) | `scoring_processor` (SQS `FINISH_MATCH`) | Predicciones ACTIVE → `SCORED`; no reprocesar si `result_processed` |

### 4.1 Evento 1 — Trivia (−2 h)

- Generar trivia con `TriviaService.generate_pre_match_trivia(match)`.
- Persistir broadcast / sesión según SPEC-025.
- Enviar a usuarios elegibles (Telegram directo o cola `TriviaDispatch`).
- Schedule name: `trivia-pre-{match_id}`.

### 4.2 Eventos 2–4 — Reminders (−60 / −30 / −15 min)

- Query: miembros de grupos ACTIVE con predicción pendiente para ese `match_id` (Aurora `v_members_without_prediction` o scan GSI-2 + filtro).
- **No enviar** si el usuario ya tiene predicción ACTIVE en ese grupo.
- Si predice después del Reminder #1, **no** enviar #2 ni #3 (check en cada disparo).
- Incluir trivia pre-partido pendiente en el cuerpo del reminder (SPEC-025), si aplica.
- Snooze: máx. 1 por reminder, +10 min (comportamiento SPEC-021).
- Schedule names: `remind-60-{match_id}`, `remind-30-{match_id}`, `remind-15-{match_id}`.

### 4.3 Evento 5 — Veda (−30 min)

- `MatchDAO.set_veda_active(match_id, active=True)` con `ConditionExpression` `veda_active = :false`.
- Notificación Telegram: “🎰 ¡NO VA MÁS!” (SPEC-021 flujo 8).
- Schedule name: `veda-{match_id}` (ADR-005).

### 4.4 Evento 6 — Resultados (+110 min)

- Invocar `ResultService.collect_result(match_id)` o publicar evento `match_ended`.
- Fuente: API-Football / mock poller / web_search (SPEC-031).
- Notificación resultado (sin predicción en el mensaje; SPEC actual).
- Schedule name: `result-{match_id}`.
- **Fallback:** regla global `rate(5 minutes)` del `result_collector` si el partido terminó tarde.

### 4.5 Evento 7 — Scoring (encadenado)

- **Primario:** al guardar `MATCH#/RESULT`, `result_service` encola SQS:

```json
{
  "event_type": "FINISH_MATCH",
  "match_id": "<uuid>",
  "result": { ... }
}
```

- `scoring_processor` puntúa predicciones, actualiza `points_earned`, `result_processed=true`.
- **Opcional catch-up schedule** `scoring-catchup-{match_id}` en `kickoff+120 min` si existe RESULT y `result_processed=false` (red de seguridad).

- Desglose de puntos al usuario: cola notify o `--telegram-direct` en dev (SPEC-021 flujo 11); **fuera** del schedule de scoring salvo producto futuro.

## 5. Nombres de schedules (idempotencia)

Prefijo recomendado: `prode-{env}-` + sufijo determinístico.

| Evento | Schedule name (sufijo) | `ScheduleExpression` (one-time) |
|--------|------------------------|----------------------------------|
| 1 Trivia | `trivia-pre-{match_id}` | `at(yyyy-mm-ddThh:mm:ss)` UTC |
| 2 Reminder | `remind-60-{match_id}` | kickoff − 60 min |
| 3 Reminder | `remind-30-{match_id}` | kickoff − 30 min |
| 4 Reminder | `remind-15-{match_id}` | kickoff − 15 min |
| 5 Veda | `veda-{match_id}` | kickoff − 30 min |
| 6 Resultado | `result-{match_id}` | kickoff + 110 min |
| 7 Scoring catch-up | `scoring-catchup-{match_id}` | kickoff + 120 min (opcional) |

- `match_id` = UUID completo (Scheduler admite hasta 64 chars en name; validar límite AWS).
- Si el nombre excede límite: hash estable `match-{sha256(match_id)[:16]}-{event}` manteniendo tabla de mapeo en Dynamo `JOB_CTRL#SCHEDULE#<match_id>`.

## 6. Componente central: `scheduler_manager`

```python
# src/services/scheduler_manager.py (nuevo)

class MatchScheduleManager:
    def provision_match(self, match: dict) -> ProvisionResult:
        """Create or update los 7 schedules para match_id."""

    def update_kickoff(self, match_id: str, old_kickoff: datetime, new_kickoff: datetime) -> None:
        """Delete + recreate si cambió kickoff_utc."""

    def deprovision_match(self, match_id: str) -> None:
        """Delete todos los schedules del partido (cancelación / replace fixture)."""
```

### 6.1 Puntos de enganche

| Acción | Dónde |
|--------|--------|
| Alta partido | `MatchDAO.put_match` → hook post-write **o** final de `ingest_matches` por registro |
| Sync API fixture | `scripts/sync_fixture_from_api.py` si cambia `kickoff_utc` |
| Baja / replace | `MatchDAO.delete_all_matches` / delete single → `deprovision_match` |
| Partido ya pasado | Si `kickoff_utc + 110min < now()`, **no** crear schedules pre-partido; solo catch-up result/scoring si aplica |

### 6.2 IAM

Rol `scheduler_manager` (o Lambda ingest con permisos):

- `scheduler:CreateSchedule`, `UpdateSchedule`, `DeleteSchedule`, `GetSchedule`
- `iam:PassRole` → rol de ejecución de las Lambdas destino

## 7. Payload estándar de schedule

Todas las invocaciones one-time envían:

```json
{
  "event_type": "MATCH_TRIVIA | MATCH_REMINDER | MATCH_VEDA | MATCH_RESULT | MATCH_SCORING_CATCHUP",
  "match_id": "<uuid>",
  "schedule_name": "<nombre determinístico>",
  "reminder_tier": 1
}
```

`reminder_tier`: 1, 2 o 3 para eventos 2–4.

## 8. Estado actual vs objetivo

| # | Evento | ¿Schedule al alta? | Código Lambda | Gap |
|---|--------|-------------------|---------------|-----|
| 1 | Trivia −2 h | No | `trivia_pre_match_dispatcher` (stub) | Scheduler + cambiar −1 h → −2 h |
| 2–4 | Reminders | No | No existe `match_reminder_dispatcher` | Lambda + 3 schedules |
| 5 | Veda −30 min | No | No existe `veda_activator` | Lambda + schedule |
| 6 | Resultado +110 min | No (solo rate 5 min global) | `result_collector` | Schedule `match_ended` por partido |
| 7 | Scoring | Parcial (SQS si URL set) | `scoring_processor` | Encadenar siempre; catch-up schedule |

## 9. Tasks de implementación

| TASK | Descripción | Est. |
|------|-------------|------|
| TASK-032-001 | `MatchScheduleManager` + cliente EventBridge Scheduler | 6h |
| TASK-032-002 | Hook en `put_match` / ingest / sync fixture | 3h |
| TASK-032-003 | Lambda `veda_activator` | 4h |
| TASK-032-004 | Lambda `match_reminder_dispatcher` (tiers 1–3) | 6h |
| TASK-032-005 | Ajustar `trivia_pre_match_dispatcher` a −2 h + schedule | 3h |
| TASK-032-006 | Schedule `result-{match_id}` → `result_collector` | 2h |
| TASK-032-007 | Garantizar encadenamiento RESULT → ScoringQueue + catch-up | 2h |
| TASK-032-008 | Terraform: rol Scheduler + variables `enable_match_schedules` | 4h |
| TASK-032-009 | Tests unitarios `scheduler_manager` + integración dev | 4h |
| TASK-032-010 | Script `scripts/provision_match_schedules.py` (backfill 104 partidos) | 2h |

## 10. Gherkin — criterios de aceptación

```gherkin
Feature: Provisionamiento de schedules por partido

  Background:
    Dado que EventBridge Scheduler está habilitado en el entorno dev
    Y existe un partido MEX vs RSA con kickoff_utc en el futuro

  Scenario SC-01 — Alta de partido crea 7 schedules
    Cuando se ejecuta ingest_matches o put_match para ese partido
    Entonces existen schedules trivia-pre, remind-60, remind-30, remind-15, veda, result
    Y opcionalmente scoring-catchup
    Y cada schedule tiene trigger_time correcto en UTC

  Scenario SC-02 — Idempotencia
    Dado que los schedules ya existen
    Cuando se vuelve a llamar provision_match con el mismo kickoff
    Entonces no se duplican schedules (update in-place)

  Scenario SC-03 — Cambio de kickoff
    Dado un partido con kickoff movido +2 horas
    Cuando se actualiza MATCH#/DETAILS
    Entonces los schedules se recrean con las nuevas horas

  Scenario SC-04 — Reminder solo sin predicción
    Dado un usuario sin predicción ACTIVE para el partido
    Cuando dispara remind-60-{match_id}
    Entonces recibe Telegram Reminder #1
    Dado que luego guarda predicción
    Cuando dispara remind-30 y remind-15
    Entonces NO recibe Reminder #2 ni #3

  Scenario SC-05 — Veda a los 30 minutos
    Cuando dispara veda-{match_id}
    Entonces veda_active es true
    Y los usuarios reciben notificación de veda

  Scenario SC-06 — Resultado y scoring
    Cuando dispara result-{match_id} y el partido tiene RESULT en DynamoDB
    Entonces se encola FINISH_MATCH
    Y scoring_processor marca predicciones SCORED
    Y result_processed es true

  Scenario SC-07 — Partido en el pasado
    Dado kickoff_utc hace 3 días
    Cuando se intenta provision_match
    Entonces no se crean schedules pre-partido
    Y solo se evalúa catch-up de result/scoring si aplica
```

## 11. Reglas NUNCA

- NO crear schedules con nombres aleatorios (rompe idempotencia).
- NO enviar reminders a usuarios con predicción ACTIVE.
- NO permitir `PutItem` de predicción si `veda_active=true` (ya existe en DAO).
- NO reprocesar scoring si `result_processed=true`.
- NO loguear `platform_id` en payloads de reminder.
- NO crear schedules pre-partido si `kickoff_utc` ya pasó.

## 12. Migración / backfill

```bash
# Propuesto
python scripts/provision_match_schedules.py --env dev --profile asap_dev
python scripts/provision_match_schedules.py --env dev --from-date 2026-06-11 --dry-run
```

Procesar los 104 partidos del fixture; omitir partidos ya finalizados.

## 13. Referencias

- [SPEC-2026-041 — Match Lifecycle Dev Sandbox (4 min, solo dev)](SPEC-2026-041-match-lifecycle-dev-sandbox.md) — comprime los mismos 7 eventos sin alterar este SPEC
- `.cursor/rules/11-predictions.mdc` — flujos 8–9 (veda, reminders; actualizar offsets)
- `.cursor/rules/15-trivias.mdc` — trivia pre-partido (actualizar a −2 h)
- `.cursor/rules/21-result-collector.mdc` — resultado +110 min
- `.cursor/rules/04-scoring-daily.mdc` — motor de puntos
- ADR-005 — `veda-{match_id}`
