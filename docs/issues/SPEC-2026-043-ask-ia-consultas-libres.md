# SPEC-2026-043 — Ask IA: consultas al agente con créditos diarios y modo comando estricto

| Campo | Valor |
|-------|--------|
| **Tipo** | Feature — UX Telegram + cuotas + AgentCore |
| **Sprint** | Post SPEC-011 (Telegram) / SPEC-019 (onboarding) |
| **Estado** | **Implementado** (MVP) — deploy + `BOT_COMMANDS_VERSION=7` |
| **Depende de** | SPEC-011 (`handler` + `invoke_agent_runtime`), SPEC-018 (auth), AgentCore Runtime |
| **Reemplaza** | Atajo **«🏁 Resultados»** / `/resultados` por **«🤖 Ask IA»** / `/ask_ia` |
| **Rompe** | Comportamiento actual: **cualquier texto libre** invoca al agente (líneas 573–602 de `handler.py`) |
| **Relacionado** | SPEC-042 (Mi ranking reemplaza Mi puntaje); `/resultados` queda disponible solo por comando escrito o se depreca |
| **Componentes** | `handler.py`, `bot_commands.py`, `telegram_keyboards.py`, `shortcut_commands.py`, nuevo `ask_ia_commands.py`, `ask_ia_service.py`, `user_dao`, (opcional) `ia_credit_purchase_dao` |

---

## 0. Prerrequisitos

| Requisito | Obligatorio |
|-----------|-------------|
| AgentCore Runtime + Lambda Telegram (SPEC-011) | Sí |
| Auth / usuarios ACTIVE en DynamoDB (SPEC-018) | Sí |
| Cuenta **Cafecito** o API Mercado Pago | **No** |
| **Alias de cobro** para transferencias | Sí — valor producto: **`Scalonia2026.mp`** |

El upgrade de consultas se cobra por **transferencia** al alias configurado. El usuario queda identificado por el **chat de Telegram** desde el que envía el comprobante (no hace falta escribir @usuario si paga desde la misma cuenta).

---

## 1. Problema (as-built)

| # | Comportamiento actual | Impacto |
|---|----------------------|---------|
| P1 | Texto libre → prefetch fixture/KB → **AgentCore** siempre | Costo IA impredecible; usuarios escriben sin intención de consulta |
| P2 | No hay cuota diaria de consultas | Riesgo de abuso y factura Bedrock |
| P3 | Sesión AgentCore derivada de `platform_id_hash` fija por chat | Conversación “fantasma” mezclada con cualquier mensaje |
| P4 | Atajo «Resultados» duplica información ya accesible por fixture | Teclado ocupado; poco valor vs consulta IA |
| P5 | Sin flujo de **upgrade** de créditos | No hay monetización ni compensación operativa |

---

## 2. Objetivos

1. **Modo comando estricto:** solo `/ask_ia` (o botón «🤖 Ask IA») inicia o habilita el canal al agente; el resto de entradas deben resolver a un comando conocido o responder **«Comando no válido»**.
2. **Conversación guiada:** tras cada respuesta del agente, ofrecer **callback inline** para continuar la sesión IA (no asumir texto libre encadenado).
3. **Créditos diarios:** cada usuario tiene **5 consultas/día** (~5 intercambios usuario→agente con respuesta exitosa).
4. **Reemplazar** shortcut Resultados por Ask IA en teclado fijo y menú `/`.
5. **Reset diario** a las **00:01** del día siguiente (zona horaria definida en §5.2).
6. **Upgrade por transferencia:** mínimo **6.999 ARS** al alias **`Scalonia2026.mp`**; el usuario envía el **comprobante** en el chat de Telegram y el sistema **acredita los créditos automáticamente** al perfil vinculado a ese chat.
7. **Admin:** comando para otorgar consultas extra manualmente (soporte, excepciones, reembolsos).

---

## 3. Modelo de créditos (decisión de producto)

### 3.1 Unidad expuesta al usuario: **consulta**

| Término UI | Significado técnico |
|------------|---------------------|
| **1 consulta** | 1 invocación exitosa a AgentCore tras un mensaje del usuario en sesión Ask IA |
| **Paquete diario gratis** | **5 consultas** / día calendario |
| **Créditos bonus** | Consultas adicionales por transferencia acreditada o por admin (no expiran al reset diario) |

**No** exponer “tokens” al usuario en MVP (complejidad). Internamente se puede loguear `input_tokens` / `output_tokens` en CloudWatch para costeo futuro.

### 3.2 Cuándo se descuenta

| Evento | Descuenta consulta |
|--------|-------------------|
| Respuesta del agente **exitosa** (texto no vacío, sin error de runtime) | **Sí** (1) |
| Error de AgentCore / timeout | **No** |
| Usuario cancela antes de enviar (`/cancel` en sesión IA) | **No** |
| Admin otorga bonus | Suma a `ai_bonus_credits` |

### 3.3 Orden de consumo

1. `ai_daily_remaining` (máx 5, se repone con reset)
2. `ai_bonus_credits` (compras / admin)

### 3.4 Reset diario

- **Zona horaria:** `America/Argentina/Buenos_Aires` (Mundial + usuarios objetivo).
- **Momento:** `00:01` — al primer uso del día o job ligero, si `ai_credits_reset_date < hoy_AR`, entonces `ai_daily_remaining = 5` y `ai_credits_reset_date = hoy_AR`.
- Los **bonus** no se resetean.

---

## 4. User stories

| ID | Como | Quiero | Para |
|----|------|--------|------|
| US-43-01 | Jugador | Pulsar «🤖 Ask IA» | Hacer una pregunta sobre el Mundial con IA |
| US-43-02 | Jugador | Ver cuántas consultas me quedan hoy | Administrar mi uso |
| US-43-03 | Jugador | Seguir la charla con un botón después de cada respuesta | Saber cuándo estoy en modo IA |
| US-43-04 | Jugador sin créditos | Saber cuándo vuelven y cómo obtener más | No quedarme bloqueado sin salida |
| US-43-05 | Jugador | Transferir al alias y enviar comprobante en Telegram | Recibir créditos al instante sin esperar admin |
| US-43-06 | Admin | Otorgar consultas a un alias | Resolver soporte, excepciones o fraudes |
| US-43-07 | Usuario | Escribir «hola» suelto | Recibir «Comando no válido» y ver atajos |

---

## 5. Criterios de aceptación

### 5.1 Modo comando estricto (US-43-07)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-01 | Usuario ACTIVE, **sin** sesión IA esperando texto | Envía «¿Quién ganó el 86?» | **No** invoca AgentCore; responde `Comando no válido` + hint de `/help` o atajos |
| AC-02 | Usuario ACTIVE | Envía `/partidos` | Flujo predicciones (sin cambio) |
| AC-03 | Usuario ACTIVE | Envía `/ask_ia` | Inicia flujo Ask IA (§5.2) |
| AC-04 | Usuario ACTIVE | Toca «🤖 Ask IA» | Equivalente a `/ask_ia` |
| AC-05 | Texto mapeado por teclado | Tap en atajo válido | Ejecuta comando, no «Comando no válido» |

**Excepciones obligatorias** (no son “comando inválido” ni Ask IA libre):

| Contexto | Entrada | Handler existente |
|----------|---------|-------------------|
| Onboarding `M1_PENDING` | alias / botones `onb:` | `onboarding_handler` |
| Wizard predicción activo | marcador, callbacks `prd:` | `prediction_wizard` |
| Grupo en creación/edición | texto pendiente | `group_commands.handle_group_pending_message` |
| Trivia activa | A/B/C/D o `/trivia` | `trivia_commands` |
| Sesión IA: `ai_awaiting_prompt=true` | **un** mensaje de texto | Ask IA → AgentCore (§5.3) |
| Upgrade: `ai_purchase_pending=true` | **foto o documento** (comprobante) | Acreditación automática (§5.6) |

**Eliminar en `handler.py`:** bloque que invoca agente para texto genérico (`fixture_prefetch` directo, `kb_prefetch`, `_invoke_agent` al final) salvo vía `AskIaService`.

### 5.2 Inicio de sesión Ask IA (US-43-01, US-43-02)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-10 | Créditos disponibles (daily+bonus > 0) | `/ask_ia` | Mensaje: «Tenés N consultas hoy. Escribí tu pregunta sobre el Mundial 2026.» + `ai_awaiting_prompt=true` + sesión nueva `ai_session_id` |
| AC-11 | Sin créditos | `/ask_ia` | Mensaje de agotado (§5.6) + teclado solicitud upgrade |
| AC-12 | Primera consulta del día | Tras reset implícito | `ai_daily_remaining` repuesto a 5 si corresponde |

### 5.3 Conversación y callbacks (US-43-03)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-20 | `ai_awaiting_prompt=true` | Usuario envía pregunta | Invoca AgentCore con `runtimeSessionId` estable por `ai_session_id`; respuesta en texto plano |
| AC-21 | Tras respuesta exitosa | Fin de turno | `ai_awaiting_prompt=false`; mensaje incluye **inline keyboard** obligatorio |
| AC-22 | Teclado post-respuesta | Botones mínimos | «💬 Otra consulta» (`ia:more`) si créditos > 0; «🛑 Terminar» (`ia:end`); si sin créditos solo «☕ Más consultas» |
| AC-23 | Usuario toca `ia:more` | Callback | Si hay crédito → «Escribí tu siguiente pregunta» + `ai_awaiting_prompt=true` |
| AC-24 | Usuario toca `ia:end` | Callback | Limpia flags IA; «Sesión de IA cerrada. Usá los atajos del menú.» |
| AC-25 | Respuesta mostrada | Sin tocar `ia:more` | Texto suelto posterior → **Comando no válido** (no continúa IA) |
| AC-26 | Cada respuesta IA | Markup | Siempre incluye al menos un botón de continuación o de cierre (AC-21) |

### 5.4 Créditos y reset (US-43-02, US-43-04)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-30 | 5 consultas usadas en el día (daily=0, bonus=0) | Intenta `ia:more` o `/ask_ia` | Mensaje: agotaste consultas; próximo reset **00:01** (fecha local AR) |
| AC-31 | Día nuevo 00:01 AR | Primera acción del día | `ai_daily_remaining = 5` |
| AC-32 | Tras consulta exitosa | Contador | Resta 1 de daily; si daily=0 resta de bonus |
| AC-33 | Footer opcional | Tras cada respuesta | «Consultas restantes hoy: N» (N = daily+bonus) |

### 5.5 UI — reemplazo Resultados (US-43-01)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-40 | Teclado fijo | Render | Botón **«🤖 Ask IA»** reemplaza «🏁 Resultados» |
| AC-41 | Menú `/` | setMyCommands | `ask_ia` en lugar de `resultados` |
| AC-42 | `/resultados` escrito | Handler | Deprecación: redirige a `/ask_ia` **o** mensaje «Usá /ask_ia» (elegir una; recomendado: mensaje + no invocar resultados) |

### 5.6 Upgrade por transferencia — alias `Scalonia2026.mp` (US-43-04, US-43-05)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-50 | Sin créditos (o quiere más) | Toca «☕ Más consultas» (`ia:upgrade`) | Mensaje con alias **`Scalonia2026.mp`**, monto mínimo **$6.999 ARS**, instrucciones; `ai_purchase_pending=true` |
| AC-51 | Instrucciones | Texto upgrade | Indica transferir al alias y **enviar el comprobante en este mismo chat** (foto o PDF) |
| AC-52 | `ai_purchase_pending=true` | Usuario envía **foto o documento** | **Acreditación automática** al `user_id` del chat (sin `/ia_confirmar` admin) |
| AC-53 | Tras acreditar | Confirmación | «✅ Se acreditaron {pack} consultas. Total disponible: {n}. Podés usar /ask_ia.»; `ai_purchase_pending=false` |
| AC-54 | Pack mínimo | Monto referencia | **$6.999 ARS** → **`+20` consultas bonus** (default `IA_PACK_BONUS_CREDITS=20`) |
| AC-55 | Auditoría | Cada acreditación auto | Registro `IA_PURCHASE#<uuid>/DETAILS` con `user_id`, alias Telegram, timestamp, `file_id` Telegram; notificación opcional al admin (solo log, no bloquea) |
| AC-56 | Anti-abuso | Misma cuenta | Máximo **1 acreditación automática por compra** cada **24 h** por `user_id` (`ai_last_auto_purchase_at`); si ya acreditó hoy → mensaje «Ya procesamos un comprobante hoy; si pagaste de nuevo escribinos al admin» |
| AC-57 | Comprobante sin pending | Foto suelta | **Comando no válido** o mensaje «Usá primero «Más consultas»» — no acreditar fuera de contexto |

**Identificación del usuario:** el `user_id` y alias del **perfil Telegram** que envía el comprobante son la fuente de verdad. No se exige que el usuario escriba su @ en el caption (opcional para soporte).

**Mensaje tipo upgrade (producto):**

```
☕ Consultas adicionales

Transferí $6.999 ARS (mínimo) al alias:
Scalonia2026.mp

Luego enviá acá el comprobante (captura o PDF).
Te acreditamos las consultas automáticamente en esta cuenta de Telegram.

Las 5 consultas gratis vuelven mañana a las 00:01 (hora Argentina).
```

**Nota de implementación:** la acreditación es automática al recibir el archivo, **sin** validar el monto en el comprobante vía OCR (MVP). Revisión manual queda para `/ia_otorgar` o reversión admin si hay fraude.

**Futuro (P2, fuera de MVP):** link Mercado Pago, webhook MP, o Cafecito como medios alternativos.

### 5.7 Admin — otorgar créditos (US-43-06)

| AC | Dado | Cuando | Entonces |
|----|------|--------|----------|
| AC-60 | Admin global | `/ia_otorgar <alias> <cantidad>` | Suma `cantidad` a `ai_bonus_credits` del usuario; confirma alias y nuevo saldo |
| AC-61 | No admin | `/ia_otorgar` | «Solo el administrador puede usar este comando.» |
| AC-62 | Alias inexistente | Comando | Error claro |
| AC-63 | Admin | `/ia_otorgar vic 10` | Usuario `vic` recibe +10 bonus; opcional notificación Telegram si `tg_chat_id` |
| AC-64 | Fraude / excepción | Admin | `/ia_otorgar` suma o resta bonus; puede notificar al usuario por Telegram |

Comandos admin **solo** en `ADMIN_COMMANDS` (scope chat admin), no en menú global. El flujo estándar de compra **no** requiere intervención admin.

---

## 6. Diseño técnico

### 6.1 Estado en DynamoDB (`USER# / PROFILE`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ai_daily_remaining` | N (0–5) | Consultas gratis del día |
| `ai_bonus_credits` | N (≥0) | Consultas compradas/otorgadas |
| `ai_credits_reset_date` | S `YYYY-MM-DD` | Último día AR repuesto |
| `ai_session_id` | S | `runtimeSessionId` AgentCore (≥33 chars, ej. `ask-{user_id}-{uuid}`) |
| `ai_awaiting_prompt` | BOOL | Usuario puede enviar **un** texto a IA |
| `ai_purchase_pending` | BOOL | Esperando comprobante de transferencia |
| `ai_last_auto_purchase_at` | S ISO | Última acreditación automática (límite 24 h) |

Registro de auditoría: `IA_PURCHASE#<uuid>/DETAILS` (`user_id`, `alias`, `amount_ars`, `credits_granted`, `telegram_file_id`, `created_at`, `source=AUTO`).

### 6.2 Servicio `AskIaService`

```text
ensure_daily_reset(user_id) -> None
credits_available(profile) -> int
start_session(user_id) -> tuple[str, dict | None]   # mensaje + markup
handle_user_prompt(user_id, text) -> tuple[str, dict | None]
callback(user_id, data) -> tuple[str, dict | None]
end_session(user_id) -> str
request_upgrade(user_id) -> tuple[str, dict]
handle_purchase_proof(user_id, file_meta) -> str  # acredita automático + auditoría
admin_grant(admin_id, alias, amount) -> str
```

### 6.3 Callbacks `ia:*`

| Callback | Acción |
|----------|--------|
| `ia:more` | Habilitar siguiente pregunta (`ai_awaiting_prompt=true`) |
| `ia:end` | Cerrar sesión IA |
| `ia:upgrade` | Instrucciones transferencia a `Scalonia2026.mp`; `ai_purchase_pending=true` |

### 6.4 Sesión AgentCore

- Crear `ai_session_id` nuevo en cada `/ask_ia` (conversación fresca) **o** reutilizar hasta `ia:end` — **recomendado:** reutilizar dentro del mismo “día de charla” hasta Terminar, para coherencia multi-turn.
- Payload igual que hoy: `{ prompt, user_id, platform, session_id }`.
- Prefijo prompt sistema (en Lambda, no agente): «Respondé en español rioplatense, breve, solo fútbol Mundial 2026.»

### 6.5 Cambio en `handler.py` (orden de routing)

```text
1. /start, callbacks (trv, onb, prd, grp, inv, ia, rnk)
2. /help, atajos mapeados (incl. /ask_ia)
3. onboarding M1
4. comandos grupo / predicción / trivia / invitación (slash)
5. ask_ia: si ai_awaiting_prompt → AskIaService.handle_user_prompt
6. ask_ia: si ai_purchase_pending + photo/document → handle_purchase_proof (auto-acreditar)
7. wizards / pending grupos / trivia
8. DEFAULT → "Comando no válido"
```

**Quitar:** `try_direct_fixture_reply`, `try_direct_knowledge_reply`, `_invoke_agent` genérico del final.

### 6.6 Variables de entorno

| Variable | Ejemplo | Uso |
|----------|---------|-----|
| `IA_DAILY_FREE_CREDITS` | `5` | Cupo diario |
| `IA_PACK_BONUS_CREDITS` | `20` | Por comprobante acreditado |
| `IA_MIN_PACK_ARS` | `6999` | Monto mínimo indicado en UI |
| `IA_PAYMENT_ALIAS` | `Scalonia2026.mp` | Alias de transferencia (Mercado Pago u otro medio con alias) |
| `IA_AUTO_PURCHASE_COOLDOWN_H` | `24` | Mínimo horas entre acreditaciones auto por usuario |
| `ADMIN_TELEGRAM_CHAT_ID` | (opcional) | Copia de auditoría al admin (no bloquea acreditación) |

---

## 7. Archivos a tocar

| Archivo | Cambio |
|---------|--------|
| `telegram_keyboards.py` | «🤖 Ask IA» → `/ask_ia` |
| `bot_commands.py` | Menú, help, `BOT_COMMANDS_VERSION=7`, admin `ia_otorgar` |
| `shortcut_commands.py` | Quitar `resultados`; no handler libre |
| `ask_ia_commands.py` | **Nuevo** — slash + callbacks |
| `src/services/ask_ia_service.py` | **Nuevo** — créditos + sesión |
| `src/dao/dynamo/user_dao.py` | Campos IA + helpers reset/grant |
| `handler.py` | Routing estricto + rama `ia:` |
| `tests/unit/test_telegram/test_ask_ia*.py` | **Nuevo** |

---

## 8. Mensajes estándar

```text
INVALID_COMMAND = "❌ Comando no válido.\n\nUsá el menú / o los botones de abajo. Ayuda: /help"

ASK_PROMPT = "🤖 Ask IA — Mundial 2026\n\nTenés {n} consultas disponibles.\nEscribí tu pregunta:"

ASK_REPLY_FOOTER = "\n\nConsultas restantes: {n}"

NO_CREDITS = "⛔ Usaste todas tus consultas de hoy.\n\nVolvé a tener consultas gratis mañana a las 00:01 (hora Argentina).\n¿Querés más ahora? Tocá el botón de abajo."

UPGRADE_TRANSFER = "☕ Consultas adicionales\n\nTransferí ${min_ars} ARS (mínimo) al alias:\n{payment_alias}\n\nEnviá el comprobante en este chat y te acreditamos las consultas automáticamente."

CREDITS_AUTO_GRANTED = "✅ Acreditamos {pack} consultas en tu cuenta (@{alias}).\nTotal disponible: {total}.\nUsá /ask_ia cuando quieras."
```

---

## 9. Seguridad y costos

- Rate limit por usuario: máximo **5 + bonus** invocaciones/día salvo admin.
- Acreditación auto: cooldown **24 h** por usuario; registro `IA_PURCHASE#` para auditoría.
- **Riesgo conocido (MVP):** no se valida el comprobante contra el banco; confianza en captura + cooldown. Admin puede revertir vía ajuste manual de bonus.
- Guardrail AgentCore existente sigue aplicando.
- Log: `user_id` truncado, **nunca** `platform_id` ni token.
- Alarmas CloudWatch: invocaciones Ask IA / día, acreditaciones auto / día, errores AgentCore.

---

## 10. Fuera de alcance (MVP)

- Validación OCR del monto en el comprobante o conciliación bancaria automática.
- Link de pago Mercado Pago / webhook MP (P2).
- Cafecito u otros medios distintos del alias `Scalonia2026.mp` (P2).
- Ask IA en grupos Telegram (solo chat privado bot).
- Historial de conversación exportable.
- Migrar fixture/KB prefetch al agente solo dentro de Ask IA (el agente ya tiene tools).

---

## 11. Plan de tareas

| ID | Tarea | Est. |
|----|--------|------|
| T-43-01 | `AskIaService` + campos PROFILE + reset diario AR | 4h |
| T-43-02 | `ask_ia_commands` + callbacks + tests unitarios | 4h |
| T-43-03 | Refactor `handler.py` (modo estricto, quitar agente libre) | 3h |
| T-43-04 | Teclado + menú + help + deprecar resultados | 1h |
| T-43-05 | Transferencia `Scalonia2026.mp` + comprobante + **acreditación auto** + auditoría | 4h |
| T-43-06 | `/ia_otorgar` admin + tests | 2h |
| T-43-07 | (P2) Link/webhook Mercado Pago o validación bancaria | 5h |

---

## 12. Pruebas manuales

1. Texto libre «quién es Messi» → Comando no válido.
2. `/ask_ia` → pregunta → respuesta + botón «Otra consulta» → segunda pregunta → agotar 5 → bloqueo.
3. Tras agotar → «Más consultas» → transferir (externo) → enviar comprobante en Telegram → acreditación auto → `/ask_ia` OK.
4. `/ia_otorgar alias 3` (admin) → saldo aumenta.
5. `ia:end` → texto libre → Comando no válido.
6. Onboarding M1 y wizard predicción siguen funcionando.

---

## 13. Coordinación con otras specs

| Spec | Coordinación |
|------|----------------|
| SPEC-2026-042 | Mi ranking reemplaza Mi puntaje; Ask IA reemplaza Resultados — teclado queda: Próximo, Partidos, **Ask IA**, Mi ranking, Grupos, Reglas (ajustar si 042 aún no está mergeado) |
| SPEC-2026-019 | Onboarding M1 exento de «Comando no válido» |
| SPEC-2026-011 | Sustituye invocación agente omnicanal por sesión acotada |

---

## 14. Referencias

- `infrastructure/lambdas/telegram_webhook/handler.py` — routing actual líneas 558–602.
- `src/services/trivia_service.py` — patrón `trivia_rounds_today` para cuotas diarias.
- `agent/main.py` — runtime AgentCore con tools KB/web.
