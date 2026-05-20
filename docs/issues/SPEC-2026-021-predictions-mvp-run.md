# SPEC-2026-021 — Predicciones MVP (implementación)

| Campo | Valor |
|-------|--------|
| **Estado** | MVP en repo — deploy Lambda Telegram + fixture `MATCH#` |
| **Tests** | `tests/unit/test_predictions/` |

## Implementado en este MVP

| Flujo spec | Estado |
|------------|--------|
| `check_can_predict` (grupo no GLOBAL) | ✅ |
| SK `PRED#<match>#GROUP#<group>` | ✅ |
| `/partidos` + botones `prd:o` | ✅ |
| Tap marcador `prd:s` | ✅ |
| KO empate `prd:k` (ET/PEN + ganador) | ✅ |
| `/predecir ARG 2-0 ALG` | ✅ |
| `/completo` (expulsión básica) | ✅ |
| Cambiar grupo activo `prd:cg` / `prd:sg` | ✅ |
| Veda bloquea escritura | ✅ |
| SUPERSEDED al cambiar | ✅ |

## Pendiente (spec completa)

- Reminders EventBridge (flujo 9)
- Mensaje proactivo veda (flujo 8)
- Goleador / MVP sub-flujos completos
- Texto libre vía agente + `prediction_tool`
- Desglose post-resultado (flujo 11)
- GSI-2 con `match_id#group_id` (hoy filtro en app)

## Deploy

```bash
py scripts/ingest_matches.py --env dev --profile asap_dev --execute
# rebuild Lambda telegram + apply
py scripts/register_telegram_commands.py --profile asap_dev
```

## Prueba manual

1. Usuario en grupo privio (no solo GLOBAL)
2. `/partidos` → elegir partido → marcador
3. Usuario existente abre link de otro grupo — N/A aquí
4. `/predecir MEX 1-0 RSA` si hay partido abierto
5. `/completo` tras predicción
