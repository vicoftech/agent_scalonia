# SPEC-2026-028 — Re-ejecución post-deploy (2026-05-20)

| Campo | Valor |
|-------|--------|
| **Commit desplegado** | `3ccc7b7` — fix(agent) SPEC-027 |
| **Runtime** | `prode_mundial_dev` v**47**, READY (`2026-05-20T00:58:58Z`) |
| **Lambda Telegram** | `2026-05-20T00:59:24Z` |
| **Veredicto** | **APTO con reservas** — P0 agente OK; fixture sin datos; manual Telegram pendiente |

---

## Comparativa vs run anterior (mismo día, pre-deploy v46)

| Check | Antes | Ahora |
|-------|-------|-------|
| Invoke `hola` | ❌ init &gt; 30s | ✅ ~4 KB respuesta |
| Invoke pregunta KB | — | ✅ stream 41 KB, invoca `kb_retrieval_tool` |
| `ModuleNotFoundError` en runtime | sospechado | ✅ no en respuesta |
| Smoke SPEC-027 | ✅ | ✅ 4/4 |
| Tests in-scope | 108 passed | 108 passed |
| `MATCH#` en DDB | 0 | **0** (sin cambio) |

---

## 1. Tests automatizados

| Suite | Resultado |
|-------|-----------|
| In-scope (§6 spec) | **108 passed**, 1 skipped |
| Completa | **158 passed**, 45 failed (35 scoring stub + 10 tests desactualizados) |

---

## 2. AWS dev — P0 agente (R-00 / R-16)

```
invoke_agent_runtime(prompt="hola")     → OK, len=4139
invoke_agent_runtime(prompt=historia…) → OK, len=41335, tool=kb_retrieval_tool
has_init_error=False, has_module_error=False
```

**Escenarios 0.1 / 16.1 / 16.2:** ✅ (vía API directa)

CloudWatch Lambda (últimas 6 h): ~5 eventos `invoke_agent_runtime error` — probablemente **previos al deploy 00:58 UTC**; revalidar en Telegram tras uso real.

---

## 3. Pendientes

| ID | Sev. | Item | Acción |
|----|------|------|--------|
| REG-028-02 | **P1** | 0 partidos `MATCH#` | `py scripts/ingest_matches.py` en dev |
| REG-028-05 | P2 | Tests obsoletos (start_handler, tools list, guardrails) | PR de mantenimiento |
| §5 manual | P0/P1 | Telegram E2E | Admin: `hola`, KB, `/trivia`, `/invitar` |

---

## 4. Criterios de salida §8

| Criterio | Cumple |
|----------|--------|
| P0 agente responde sin error genérico | ✅ (API) |
| pytest in-scope | ✅ |
| SPEC-027 desplegado | ✅ v47 |
| P0 manual Telegram | ⏸ usuario |
| Fixture en DDB | ❌ |

**Recomendación:** dar por cerrado **SPEC-027** en dev; ejecutar ingest fixture y checklist Telegram §5 para cerrar R-07.
