# SPEC-2026-044 — Ampliación de grupos y cupos de miembros (pago por transferencia)

| Campo | Valor |
|-------|--------|
| **Tipo** | Feature — monetización + límites plan Free |
| **Sprint** | Post SPEC-026 (grupos) / SPEC-043 (pagos) |
| **Estado** | **Especificado** — pendiente implementación |
| **Depende de** | SPEC-026, SPEC-018 (tiers), SPEC-020 (invitaciones), SPEC-043 (alias `Scalonia2026.mp`) |
| **Relacionado** | Plan Free actual: **1 grupo propio**, **5 miembros** por grupo (`max_members=5`) |
| **Partido referencia promo** | **MEX vs RSA** — veda del primer partido de prueba / apertura sandbox |

---

## 1. Problema (as-built)

| # | Situación | Comportamiento actual |
|---|-----------|------------------------|
| P1 | Usuario FREE ya tiene 1 grupo | `/crear-grupo` → límite + «Pedir al admin» (`LIMIT_REQ#`) |
| P2 | Grupo con 5/5 miembros | No puede invitar al 6.º; sin upsell claro |
| P3 | Sin precios publicados | Admin debe intervenir caso a caso |
| P4 | Mismo medio de pago que Ask IA | Debe reutilizar alias **`Scalonia2026.mp`** y comprobante en Telegram |

---

## 2. Objetivos

1. Ofrecer **ampliación pagada** con el **mismo procedimiento** que SPEC-043: transferencia + comprobante en Telegram.
2. Permitir comprar en **unidades** canjeables por:
   - **+1 grupo nuevo** (derecho a crear un grupo adicional con cupo base de **5 miembros**), o
   - **+5 cupos de miembros** en un **grupo existente** (`max_members` += 5).
3. Aplicar **matriz de precios** con descuentos por volumen hasta la **veda de MEX vs RSA**; después **precio lista (full price)**.
4. Guiar al usuario: ¿más **grupos**, más **integrantes**, o **combinación**?
5. Comandos **admin** para aplicar o corregir cupos/grupos según comprobante y wizard del usuario.

---

## 3. Unidad de compra (U)

| Canje de 1 U | Efecto en el sistema |
|--------------|----------------------|
| **Grupo nuevo** | `extra_owned_group_slots += 1` en PROFILE; el usuario puede ejecutar `/crear-grupo` una vez más (cada grupo creado sigue con `max_members=5` inicial) |
| **Pack de miembros** | En un `group_id` elegido por el owner: `max_members += 5` (ej. 5→10, 10→15) |

**Equivalencias (referencia comercial):**

| U compradas | Equivalente ilustrativo |
|-------------|-------------------------|
| 1 U | 1 grupo nuevo **o** +5 integrantes en un grupo |
| 2 U | 2 grupos nuevos **o** +10 integrantes (2×5) **o** 1 grupo + 5 integrantes |
| N U | Combinación libre que sume **N** al asignar en el wizard post-pago |

El usuario **debe** completar el wizard de asignación (o el admin replica la misma lógica) para que cada U quede aplicada.

---

## 4. Matriz de precios (ARS)

**Precio unitario lista:** **$14.999** por U.

**Promoción «pre-MEX/RSA»** (vigente mientras el partido **MEX vs RSA** **no** tenga `veda_active=true` en DynamoDB):

| Cantidad U | Precio lista (sin descuento) | **Precio promocional** | Descuento sobre lista |
|------------|------------------------------|-------------------------|------------------------|
| 1 | $14.999 | **$14.999** | — |
| 2 | $29.998 | **$27.000** | 10 % |
| 3 | $44.997 | **$29.997** | ~33 % sobre total lista* |
| 4 | $59.996 | **$49.999** | ~17 % sobre total lista / ~20 % redondeo comercial |

\*El caso 3 usa el **monto acordado de producto** ($29.997). Implementación: tabla fija (no fórmula) para evitar desvíos de redondeo.

**Full price (post-promo):** desde la **veda** de MEX vs RSA (`MATCH#…` con `home_team=MEX`, `away_team=RSA`, `veda_active=true`):

| Cantidad U | Precio a cobrar |
|------------|-----------------|
| N | **N × $14.999** (sin descuentos) |

**Detección promo:**

```python
def is_group_upgrade_promo_active(match_dao) -> bool:
    m = match_dao.find_by_teams("MEX", "RSA")  # o match_id fijo sandbox
    return m is not None and not bool(m.get("veda_active"))
```

Mostrar en UI: «Precio promocional hasta el inicio del Mundial (veda MEX vs RSA)».

---

## 5. User stories

| ID | Como | Quiero | Para |
|----|------|--------|------|
| US-44-01 | Owner FREE | Comprar otro grupo | Tener ligas separadas con amigos distintos |
| US-44-02 | Owner | Comprar +5 cupos en mi grupo | Invitar al 6.º, 7.º… integrante |
| US-44-03 | Owner | Comprar combinación grupo + cupos | Una sola transferencia con descuento |
| US-44-04 | Owner | Ver precio según cantidad de U | Saber cuánto transferir antes de pagar |
| US-44-05 | Admin | Aplicar U a un usuario por alias | Resolver comprobantes y soporte |
| US-44-06 | Owner | Enviar comprobante en Telegram | No depender de email u otro canal |

---

## 6. Criterios de aceptación

### 6.1 Disparadores del flujo

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-01 | Ya tiene 1 grupo propio | `/crear-grupo` o «➕ Crear grupo» | Pantalla de límite + **[💳 Ampliar plan]** (además de «Pedir admin» opcional) |
| AC-02 | Grupo 5/5 miembros | `/invitar` o menú invitar | Mensaje cupo lleno + **[💳 Ampliar cupos]** |
| AC-03 | Cualquier usuario | `/ampliar_plan` o `/grupo_ampliar` | Inicia wizard de compra (§6.2) |

### 6.2 Wizard pre-pago (US-44-03, US-44-04)

| AC | Paso | Contenido |
|----|------|-----------|
| AC-10 | Tipo | «¿Qué necesitás?» → [Solo grupos nuevos] [Solo más integrantes] [Combinación] |
| AC-11 | Grupos | Si grupos: «¿Cuántos grupos nuevos?» (1–4 en promo, o más con full price) |
| AC-12 | Integrantes | Si cupos: elegir **grupo existente** (lista owner) → «¿Cuántos packs de 5 integrantes?» (1 U = +5) |
| AC-13 | Combinación | Asignar U una a una: «Te quedan N U por asignar» + botones [+1 grupo] [+5 en \<grupo\>] hasta sumar N |
| AC-14 | Resumen | Muestra desglose U, precio lista vs promo, **total ARS**, alias **`Scalonia2026.mp`**, `upgrade_purchase_pending=true` |
| AC-15 | Post-pago | Tras comprobante válido (§6.3), wizard de **asignación obligatoria** si aún no se definió en pre-pago |

### 6.3 Pago — mismo procedimiento que SPEC-043 (US-44-06)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-20 | `upgrade_purchase_pending=true` | Usuario envía foto/PDF | Registra `GROUP_UPGRADE#<uuid>/DETAILS` con `user_id`, `units`, `amount_ars`, `promo`, `allocation_draft`, `file_id` |
| AC-21 | Comprobante OK | Auto (MVP) | Acredita **`units_purchased`** al perfil (`pending_group_upgrade_units`); habilita wizard asignación; confirma monto esperado en mensaje |
| AC-22 | Asignación completa | Usuario confirma | Aplica slots: crea cuota de grupo y/o `max_members+=5`; decrementa U pendientes; notifica resumen |
| AC-23 | Sin pending | Foto suelta | No procesar; indicar «Usá /ampliar_plan primero» |
| AC-24 | Cooldown | 24 h | Máx. 1 compra auto procesada / 24 h por usuario (mismo criterio que SPEC-043) |

**Mensaje de pago (plantilla):**

```
💳 Ampliar tu plan

Resumen: {N} unidades — {desglose}
Precio: ${total_ars} ARS {etiqueta_promo}

Transferí a alias:
Scalonia2026.mp

Enviá el comprobante en este chat.
Indicá en un mensaje si querés:
· grupos nuevos, o
· más integrantes (y en qué grupo),
por si el wizard no lo completaste antes.
```

### 6.4 Post-veda MEX vs RSA (full price)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-30 | `veda_active=true` en MEX vs RSA | Cotización en wizard | Total = U × 14.999; mensaje «Promoción finalizada» |
| AC-31 | Compra bajo full price | Misma mecánica | Sin descuentos por volumen |

### 6.5 Admin (US-44-05)

Comandos solo admin (menú scope admin, no global):

| Comando | Uso |
|---------|-----|
| `/grupo_otorgar_grupo <alias> [cantidad=1]` | Suma `extra_owned_group_slots` sin pago |
| `/grupo_otorgar_cupos <alias> <grupo_g8\|nombre> <packs>` | Suma `packs × 5` a `max_members` del grupo del owner |
| `/grupo_aplicar_u <alias> <N>` | Suma N U a `pending_group_upgrade_units` y abre wizard asignación al usuario vía mensaje |
| `/grupo_compras_pendientes` | Lista `GROUP_UPGRADE#` PENDING / AWAITING_ALLOCATION |
| `/grupo_ver_cuotas <alias>` | Muestra grupos propios, `max_members`, U pendientes, slots extra |

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-40 | Admin | `/grupo_otorgar_cupos toti abc12345 2` | Grupo resuelto por g8 o nombre; `max_members` += 10 |
| AC-41 | Admin | `/grupo_otorgar_grupo toti 1` | Usuario puede crear un segundo grupo |
| AC-42 | No admin | Cualquiera de los anteriores | Permiso denegado |

**Nota:** el admin puede corregir asignaciones erróneas; no duplicar U ya aplicadas (idempotencia por `purchase_id`).

---

## 7. Modelo de datos (DynamoDB)

### 7.1 PROFILE (campos nuevos)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `extra_owned_group_slots` | N | Grupos adicionales permitidos (suma a la cuota Free de 1) |
| `pending_group_upgrade_units` | N | U pagadas y aún no asignadas |
| `group_upgrade_purchase_pending` | BOOL | Esperando comprobante |
| `last_group_upgrade_purchase_at` | S ISO | Cooldown 24 h |

**Regla crear grupo:**

```text
puede_crear = groups_owned < (1 + extra_owned_group_slots)   # no admin
```

### 7.2 GROUP#/DETAILS

Sin cambio de esquema: solo **`max_members`** sube en múltiplos de 5 al canjear pack de integrantes.

### 7.3 GROUP_UPGRADE#<purchase_id>/DETAILS

| Campo | Descripción |
|-------|-------------|
| `user_id` | Comprador |
| `units` | N U compradas |
| `amount_ars` | Monto esperado |
| `promo_applied` | BOOL |
| `allocation_json` | Borrador: `[{type:"NEW_GROUP"}, {type:"MEMBER_PACK", group_id, packs:1}]` |
| `status` | `PENDING_PAYMENT` → `PAID` → `ALLOCATED` |
| `telegram_file_id` | Comprobante |
| `created_at` | ISO |

---

## 8. Diseño Telegram

### 8.1 Callbacks `gup:` (group upgrade)

| Callback | Acción |
|----------|--------|
| `gup:start` | Entrada desde límite alcanzado |
| `gup:type:groups` / `members` / `combo` | Rama wizard |
| `gup:ug:<n>` | Cantidad U (pre-pago) |
| `gup:grp:<g8>:<packs>` | Asignar packs a grupo |
| `gup:new:<n>` | Asignar n grupos nuevos |
| `gup:confirm_quote` | Muestra resumen + alias |
| `gup:alloc:confirm` | Aplica asignación post-pago |

### 8.2 Integración con flujos existentes

- Reemplazar o complementar `limit_reached_keyboard()` en `group_telegram_ui.py` con botón **Ampliar plan** → `gup:start`.
- `InvitationService` / `can_invite`: si `member_count >= max_members` → ofrecer ampliación.

---

## 9. Servicio `GroupUpgradeService`

```text
quote_units(user_id, allocation_plan) -> Quote  # total_ars, promo, breakdown
begin_purchase(user_id, quote) -> markup + pending flag
handle_payment_proof(user_id, file) -> units credited
apply_allocation(user_id, plan) -> effects on PROFILE + GROUP#
admin_grant_group_slot(admin_id, alias, n)
admin_grant_member_packs(admin_id, alias, group_ref, packs)
is_promo_period() -> bool
```

---

## 10. Relación con SPEC-043

| Aspecto | SPEC-043 Ask IA | SPEC-044 Grupos |
|---------|----------------|-----------------|
| Alias | `Scalonia2026.mp` | **Mismo** |
| Comprobante en Telegram | Sí | Sí |
| Acreditación auto MVP | Consultas bonus | **U** pendientes de asignar |
| Admin | `/ia_otorgar` | `/grupo_otorgar_*` |
| Cooldown 24 h | Sí | Sí |

Un mismo comprobante **no** debe canjearse dos veces: validar `file_id` o hash único en `GROUP_UPGRADE#` y `IA_PURCHASE#`.

---

## 11. Fuera de alcance (MVP)

- Validación bancaria / OCR del monto en comprobante.
- Plan PRO automático recurrente (suscripción).
- Transferir ownership de grupo vía compra.
- Ampliar grupo **GLOBAL**.
- Más de 4 U con tabla promo fija (5+ U: solo full price N×14999).

---

## 12. Plan de tareas

| ID | Tarea | Est. |
|----|--------|------|
| T-44-01 | `GroupUpgradeService` + tabla precios + promo MEX/RSA | 4h |
| T-44-02 | Wizard Telegram `gup:*` + hooks en crear-grupo / invitar | 5h |
| T-44-03 | Comprobante + `GROUP_UPGRADE#` + asignación | 4h |
| T-44-04 | Comandos admin + tests | 3h |
| T-44-05 | Integrar `can_create_group` con `extra_owned_group_slots` | 2h |

---

## 13. Pruebas manuales

1. Owner con 1 grupo → `/crear-grupo` → Ampliar → 1 U grupo → pagar (simulado) → comprobante → crear 2.º grupo OK.
2. Grupo 5/5 → invitar bloqueado → Ampliar → 1 U cupos → `max_members=10` → invitar 6.º OK.
3. Compra 2 U combo (1 grupo + 1 pack) → total promo $27.000 mostrado.
4. Tras veda MEX vs RSA → 2 U = $29.998.
5. Admin `/grupo_otorgar_cupos` sin pago.

---

## 14. Referencias

- `src/services/group_service.py` — `_FREE_MAX_OWNED_GROUPS = 1`, `max_members = 5`.
- `docs/issues/SPEC-2026-043-ask-ia-consultas-libres.md` — pago por alias.
- Partido sandbox: `MEX vs RSA` — `match_id` `7ec4c6ec-f11b-5a24-8fd8-7ba47082508b` (fixture JSON).
