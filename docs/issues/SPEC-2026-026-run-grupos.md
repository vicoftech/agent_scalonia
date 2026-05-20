# SPEC-2026-026 — Ejecución / implementación MVP

| Campo | Valor |
|-------|--------|
| **Fecha** | 2026-05-20 |
| **Estado** | MVP implementado en repo — **pendiente deploy** Lambda Telegram |
| **Tests** | `tests/unit/test_groups/` — 5 passed |

---

## Antes de esta ejecución

| Componente | Estado |
|------------|--------|
| `group_tool.py` | `NotImplementedError` |
| `group_dao.py` | Solo membresías básicas |
| Comandos Telegram `/grupos` | No existían |

---

## Implementado (MVP)

| Flujo spec | Implementación |
|------------|----------------|
| SC-01 Crear grupo | `/crear-grupo` o `/crear_grupo` → nombre → avatar → GROUP# + invitación |
| SC-02 Límite FREE | Teclado «Pedir al admin» → `LIMIT_REQ#` |
| SC-03–04 Renombrar / avatar | `/editar-grupo` + callbacks `grp:ren`, `grp:avpick` |
| SC-05–06 Eliminar miembro | Parcial — `/miembros` lista; eliminar vía callback `grp:rm:yes` (falta botones por miembro en UI) |
| SC-07 Eliminar grupo | `grp:del:ask` → confirmar |
| SC-08–09 Admin | `/admin-grupos` lista; suspender `grp:susp:ask` |
| SC-10 GLOBAL protegido | Hardguard en `delete_group` / `suspend_group` |
| `/grupos` lista | ✅ |

### Archivos nuevos / tocados

- `src/dao/dynamo/group_dao.py` — CRUD, `member_count` atómico, status
- `src/dao/dynamo/limit_request_dao.py`
- `src/services/group_service.py`
- `src/services/group_telegram_ui.py`
- `infrastructure/lambdas/telegram_webhook/group_commands.py`
- `handler.py`, `bot_commands.py`
- `agent/tools/group_tool.py` — redirect a comandos Telegram
- `tests/unit/test_groups/test_group_service.py`

---

## Pendiente vs spec completa

- Eliminar miembro con botón 🚫 por fila (hoy solo texto en `/miembros`)
- Paginación admin «Anterior / Siguiente»
- Notificaciones a ex-miembros al borrar grupo
- Revocar invitaciones ACTIVE al eliminar grupo
- `group_tool` en `agent/main.py` (opcional)
- Agente conversacional `/crear-grupo` (spec) — sustituido por flujo Lambda + teclado (más fiable)

---

## Deploy y prueba manual

```bash
# Terraform rebuild Lambda telegram + apply
py scripts/register_telegram_commands.py --profile asap_dev
```

Checklist Telegram:

1. `/grupos` — ver GLOBAL + grupos propios
2. `/crear-grupo` — flujo completo + link invitación
3. `/editar-grupo` — renombrar, avatar, invitar
4. Admin: `/admin-grupos`
