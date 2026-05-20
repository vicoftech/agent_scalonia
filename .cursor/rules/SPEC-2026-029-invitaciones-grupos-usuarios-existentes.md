# SPEC-2026-029 — Invitaciones avanzadas (cursor rule)

**Estado:** Abierto — ver spec completa en `docs/issues/SPEC-2026-029-invitaciones-grupos-usuarios-existentes.md`.

## Resumen para el agente

1. **Admin `/invitar`:** GLOBAL por defecto + teclado `inv:grp:*` para otro grupo.
2. **Usuario existente + deep link:** `accept_invitation_for_existing_user` — no duplicar USER#; arreglar `start_handler` líneas 43–56.
3. **Owner:** `/agregar-miembro <alias>` para usuarios ACTIVE ya en la plataforma.
4. **Admin:** `/crear-grupo-para <alias>` → flujo nombre/avatar con `owner_id` = target.

## Tests

`tests/unit/test_invitations/test_spec029_invitations_groups.py` — des-skip al implementar.

## Regresión

SPEC-2026-028 § R-29 (escenarios 29.1–29.8).
