# Spec: FEATURE-013 — Sistema de Puntuación

sprint: Sprint-2 | modo: Humano (lógica crítica de negocio)
módulo: src/scoring/scoring_engine.py — funciones PURAS

## Requirements

- requirement_id: US-035
  title: Calcular puntos con 4 reglas priorizadas
  acceptance_criteria:
    - 'calculate_points(2,0,2,0,"GROUP") → (5, "EXACT_SCORE")'
    - 'calculate_points(2,0,3,1,"GROUP") → (3, "CORRECT_WINNER_AND_DIFF")'
    - 'calculate_points(2,0,1,0,"GROUP") → (1, "CORRECT_WINNER_ONLY")'
    - 'calculate_points(2,0,0,1,"GROUP") → (0, "INCORRECT")'
    - 'calculate_points(1,1,2,2,"GROUP") → (1, "CORRECT_WINNER_ONLY")'

- requirement_id: US-036
  title: Fases eliminatorias sobre 90 minutos
  acceptance_criteria:
    - 'calculate_points(0,0,0,0,"QF") → (5, "EXACT_SCORE") — penales ignorados'
    - 'Aplica a R16, QF, SF, FINAL, THIRD_PLACE'
    - 'El CALLER es responsable de pasar result_90min, no result_final'

## Tasks

- task_id: TASK-010
  title: src/scoring/scoring_engine.py — implementación completa
  agent_mode: manual
  estimate_hours: 6
  implementation_notes: |
    PointsResult dataclass frozen. _winner() helper.
    Prioridad: exact > winner+diff > winner > incorrect.
    23 tests en test_scoring_engine.py deben pasar.

- task_id: TASK-013
  title: agent/tools/scoring_tool.py — desglose puntos via Aurora v_user_score_summary
  agent_mode: assisted
  estimate_hours: 3

## Constraints
- scoring_engine.py PURO — sin boto3, sin side effects
- El agente llama a scoring_tool que lee de Aurora, no de DynamoDB directamente

---

# Spec: FEATURE-014 — Job Diario de Rankings

sprint: Sprint-3 | modo: Humano
schedule: cron(0 3 * * ? *) UTC | período: 2026-06-11 → 2026-07-20

## Requirements

- requirement_id: US-039
  title: Recalcular rankings + catch-up + snapshots
  acceptance_criteria:
    - 'Detecta partidos FINISHED + result_processed=false → los procesa (catch-up)'
    - 'Recalcula DynamoDB RANKING#GLOBAL y RANKING#GROUP#* desde cero'
    - 'Guarda snapshot DynamoDB RANKING_SNAP# + Aurora ranking_history'
    - 'Resetea trivia_rounds_today=0 para todos los usuarios'

- requirement_id: US-041
  title: Idempotencia total
  acceptance_criteria:
    - 'JOB_CTRL#DAILY_RANKING/<fecha> ya existe → return SKIPPED sin modificaciones'
    - 'Fuera de período mundial → return SKIPPED'

## Tasks

- task_id: TASK-021
  title: src/jobs/daily_ranking_job.py — flujo completo 9 pasos
  agent_mode: manual
  estimate_hours: 8
  implementation_notes: |
    Lambda timeout: 5 minutos (configurar en CDK).
    Digest via SQS NotificationQueue (no esperar confirmación).
    Todos los pasos son idempotentes individualmente.

- task_id: TASK-021b
  title: src/dao/aurora/ranking_repo.py — save_snapshot, get_history
  agent_mode: auto
  estimate_hours: 3

## Constraints
- NUNCA corre fuera de MUNDIAL_START–MUNDIAL_END
- Lambda timeout: 5 minutos
- Digest SQS es fire-and-forget
