# Plan de test manual paso a paso — Prode Mundial 2026 (dev)

| Campo | Valor |
|-------|--------|
| **Versión** | 2026-05-20 |
| **Basado en** | [SPEC-2026-028-gherkin-test-plan.md](SPEC-2026-028-gherkin-test-plan.md) |
| **Duración estimada** | 90–120 min (recorrido completo + admin) |
| **Canal** | Telegram — bot dev (`@scalonia_bot` o el configurado en dev) |

---

## Cómo usar este documento

- Cada paso tiene **número**, **acción exacta** y **resultado esperado**.
- Marcá al final de cada bloque: `[ ] OK` `[ ] Falla` `[ ] N/A`.
- Necesitás **2 cuentas Telegram** (o 2 dispositivos): una **Admin** y una **Invitado/Player**.
- Si algo falla, usá la plantilla de reporte al final.

**Leyenda de roles**

| Rol | Quién | Teléfono / chat |
|-----|--------|-----------------|
| **Operador** | DevOps / quien despliega | PC con AWS CLI |
| **Admin** | Usuario bootstrap admin | Chat A |
| **Player** | Usuario nuevo o limpio post-purge | Chat B |

---

## Parte 0 — Preparación (Operador, antes de abrir Telegram)

| # | Acción | Resultado esperado |
|---|--------|-------------------|
| 0.1 | Confirmar deploy reciente de Lambda `telegram_webhook` y AgentCore en dev | Sin errores en último apply |
| 0.2 | Ejecutar ingest de partidos: `py scripts/ingest_matches.py --env dev --profile asap_dev --execute` | Partidos `MATCH#` en `ProdeTable-dev` |
| 0.3 | Ejecutar bootstrap admin si aplica: `py scripts/bootstrap_admin.py` | Admin existe en DynamoDB |
| 0.4 | Registrar comandos: `py scripts/register_telegram_commands.py --profile asap_dev --admin-chat-id <CHAT_ID_ADMIN>` | Sin error HTTP |
| 0.5 | (Opcional limpio) `py scripts/purge_non_admin_users.py --env dev --profile asap_dev --execute` | Solo queda admin |
| 0.6 | Anotar en una hoja: `INVITE_ID`, `GROUP_NAME`, `MATCH_PREDICTED`, `PRED_SCORE` | Para pasos finales de puntuación |

**Checklist Parte 0:** `[ ] OK` `[ ] Falla`

---

## Parte 1 — Admin: verificación del bot y menú (Chat A)

> **Objetivo:** Confirmar que el entorno responde y que el admin ve comandos extra.

| # | Acción (Chat Admin) | Resultado esperado |
|---|---------------------|-------------------|
| 1.1 | Abrí el chat del bot en Telegram | Chat vacío o historial previo |
| 1.2 | Enviá `/start` | Mensaje de bienvenida; si ya registrado, menciona tu alias |
| 1.3 | Enviá `/menu` | Texto "Menú actualizado" + atajos listados |
| 1.4 | Verificá **teclado fijo** abajo del chat | Botones: Partidos, Mi puntaje, Grupos, Resultados (texto puede variar con emoji) |
| 1.5 | Tocá el botón **/** (menú de comandos de Telegram) | Aparecen primero `/partidos`, `/mi_puntuacion`, `/grupos`, `/resultados` |
| 1.6 | Enviá `/help` | Lista de comandos + sección **"Solo admin"** con `/trivia-admin`, `/admin-grupos`, `/crear_grupo_para` |
| 1.7 | Enviá `/mis_invitaciones` | Lista (puede estar vacía) sin error |

**Checklist Parte 1:** `[ ] OK` `[ ] Falla`

---

## Parte 2 — Admin: crear invitación para el Player (Chat A)

> **Objetivo:** Generar el deep link que usará el Player en Parte 3.  
> **Gherkin ref:** INV-01, INV-02, R-29.

| # | Acción (Chat Admin) | Resultado esperado |
|---|---------------------|-------------------|
| 2.1 | Enviá `/invitar 3` | Mensaje con link/código; teclado inline (GLOBAL u "Elegir otro grupo") |
| 2.2 | Tocá **GLOBAL** (o el grupo que quieras probar) | Link `t.me/...?start=<invite_id>` y cupos restantes |
| 2.3 | **Copiá el link** y el `invite_id` (parte después de `start=`) | Guardado para Chat B |
| 2.4 | Enviá `/mis_invitaciones` de nuevo | Aparece la invitación recién creada, estado ACTIVE |

**Checklist Parte 2:** `[ ] OK` `[ ] Falla`  
**Anotá:** `invite_id = _______________`

---

## Parte 3 — Player: onboarding completo (Chat B) — RECORRIDO PRINCIPAL

> **Objetivo:** Usuario nuevo desde cero hasta M3 (puede usar el agente).  
> **Gherkin ref:** AUTH-02, ONB-01 a ONB-04.  
> **Requisito:** Chat B **nunca** usó el bot, o fue purgado.

| # | Acción (Chat Player) | Resultado esperado |
|---|----------------------|-------------------|
| 3.1 | Abrí el **link copiado** en 2.3 (o enviá `/start <invite_id>`) | Bienvenida Prode; **no** dice solo "necesitás invitación" |
| 3.2 | Leé el mensaje de alias | Pide alias o `/listo` para saltear |
| 3.3 | Escribí un alias válido, ej. `testplayer01` | Confirma alias; pasa a elegir **selección favorita** (botones) |
| 3.4 | Tocá un país en el teclado inline (ej. Argentina) | Pasa a elegir **idioma** |
| 3.5 | Tocá un idioma (ej. Español) | Tarjeta resumen de perfil o mensaje de etapa completada |
| 3.6 | Esperá hasta 20 s si pide primera pregunta al agente | Sin "Hubo un error. Por favor intentá de nuevo" |
| 3.7 | Enviá `/menu` | Menú y teclado fijo visibles (como admin pero **sin** comandos admin en `/help`) |
| 3.8 | Enviá `/help` | Lista comandos **sin** bloque "Solo admin" |

**Checklist Parte 3:** `[ ] OK` `[ ] Falla`  
**Anotá:** `alias_player = _______________`

---

## Parte 4 — Player: unirse a grupo privado para predecir (Chat B)

> Sin grupo privado, `/partidos` falla con "necesitás un grupo".  
> **Opción A (recomendada):** Admin invita a un grupo concreto. **Opción B:** Player crea su grupo.

### Opción A — Admin invita al grupo del torneo (Chat A + B)

| # | Acción | Resultado esperado |
|---|--------|-------------------|
| 4A.1 | **Admin:** `/invitar 2` → elegir grupo **no GLOBAL** (o crear grupo antes con 4B) | Link al grupo "Torneo QA" |
| 4A.2 | **Player:** abrir ese link o `/start <invite_id_grupo>` | Mensaje "Te uniste a …" / confirmación de grupo |
| 4A.3 | **Player:** `/grupos` | Lista incluye el grupo privado (no solo GLOBAL) |

### Opción B — Player crea su propio grupo (solo Chat B)

| # | Acción (Chat Player) | Resultado esperado |
|---|----------------------|-------------------|
| 4B.1 | Enviá `/crear-grupo` | Pide nombre del grupo |
| 4B.2 | Escribí `Los Pibes QA` | Pide elegir avatar (teclado inline) |
| 4B.3 | Tocá un avatar (ej. ⚽) | "Grupo creado" + link de invitación |
| 4B.4 | Enviá `/grupos` | Aparece "Los Pibes QA" como owner |

**Checklist Parte 4:** `[ ] OK` `[ ] Falla`  
**Anotá:** `grupo_activo = _______________`

---

## Parte 5 — Player: predecir un partido (Chat B)

> **Gherkin ref:** PRED-02 a PRED-06.  
> **Objetivo:** Tener al menos 1 predicción ACTIVE guardada.

| # | Acción (Chat Player) | Resultado esperado |
|---|----------------------|-------------------|
| 5.1 | Tocá teclado **⚽ Partidos** (o enviá `/partidos`) | Encabezado **"Fase de grupos"**, "Página 1/N", partidos con banderas |
| 5.2 | Si N > 1, tocá **Siguiente ▶️** | Página 2 con otros partidos |
| 5.3 | Tocá **◀️ Anterior** (si apareció) | Vuelve a página 1 |
| 5.4 | Tocá el **número** de un partido con veda abierta (no "Finalizado") | Pantalla del partido + botones de marcador (0-0, 1-0, 2-0, etc.) |
| 5.5 | Tocá **2-0** (o otro marcador) | "Predicción rápida guardada" + banderas; botones "Listo" y "Predicción completa" |
| 5.5b | Tocá un partido **finalizado** (🔒 en el botón) | Desglose: tu predicción vs resultado + puntos (5/3/1/0) y motivo si no sumaste |
| 5.6 | Tocá **⚡ Listo (solo resultado)** | Confirmación; no obliga wizard |
| 5.7 | Anotá número de partido y equipos del paso 5.4 | Para verificar después |
| 5.8 | (Opcional) Repetí 5.4–5.5 en otro partido: tocá **✏️ Otro marcador** → escribí `3-1` | Guarda 3-1; **no** pide `/predecir`; **no** guardrail del agente |
| 5.9 | (Opcional) Enviá `/predecir MEX 2-0 RSA` (si existe ese partido abierto) | Guardada o mensaje claro si no encuentra partido |

**Checklist Parte 5:** `[ ] OK` `[ ] Falla`  
**Anotá:** `match #___ = ______ vs ______ predicción ___-___`

---

## Parte 6 — Player: predicción completa (opcional, Chat B)

> **Gherkin ref:** COMP-01 a COMP-03. Goleador/MVP = "próximamente" → no fallar.

| # | Acción (Chat Player) | Resultado esperado |
|---|----------------------|-------------------|
| 6.1 | Enviá `/completo` | Abre wizard (tarjeta roja) del partido con predicción ACTIVE |
| 6.2 | Tocá **🟥 Sí habrá roja** (o "No" / "Saltar") | Confirma y cierra wizard |
| 6.3 | Si no hay predicción previa, verificá mensaje claro | Indica que primero hay que predecir en `/partidos` |

**Checklist Parte 6:** `[ ] OK` `[ ] Falla` `[ ] N/A`

---

## Parte 7 — Player: consultar puntuación (Chat B) — CIERRE DEL RECORRIDO

> **Objetivo del recorrido:** Ver estado de puntos tras predecir.  
> **Importante:** El **scoring automático** al finalizar un partido en dev puede **no estar activo** vía Telegram. Este bloque tiene **7A** (siempre) y **7B** (si hay resultado cargado).

### 7A — Verificación inmediata (siempre ejecutar)

| # | Acción (Chat Player) | Resultado esperado |
|---|----------------------|-------------------|
| 7A.1 | Tocá **📊 Mi puntaje** o enviá `/mi_puntuacion` | Bloque "📊 Mi puntuación" con Total, Partidos, Trivia |
| 7A.2 | Leé línea **Predicciones activas** | Número ≥ 1 (la de Parte 5) |
| 7A.3 | Leé **Predicciones ya puntuadas** | Puede ser 0 (normal si ningún partido fue puntuado aún) |
| 7A.4 | Si hay puntuadas, verificá listado "Últimas puntuadas" | Muestra partido, predicción y pts (ej. `→ 3 pts`) |
| 7A.5 | Enviá `/resultados` | Lista de finalizados **o** mensaje "Aún no hay partidos marcados como finalizados" |

**Criterio OK Parte 7A:** El bot refleja la predicción en **activas**; totales coherentes (trivia suma si jugó trivia).

**Checklist 7A:** `[ ] OK` `[ ] Falla`

### 7B — Puntuación del partido predecido (solo si hay resultado + scoring en dev)

> Si en dev **no** corre el job de scoring, marcá 7B como **N/A** y documentá. No es falla del flujo de predicción.

| # | Acción (Operador + Player) | Resultado esperado |
|---|---------------------------|-------------------|
| 7B.0 | **Operador:** Confirmar en DynamoDB que el partido de 5.7 tiene `RESULT` y scoring aplicado (`points_earned` en predicción), **o** esperar pipeline daily si está programado | Predicción con `points_earned` = 0, 1, 3 o 5 según reglas |
| 7B.1 | **Player:** `/mi_puntuacion` de nuevo | "Predicciones ya puntuadas" ≥ 1 |
| 7B.2 | **Player:** Buscar en listado el partido de 5.7 | Línea `pred X-Y → N pts` coincide con reglas SPEC-013 |
| 7B.3 | **Player:** `/resultados` | Aparece ese partido con marcador final |

**Reglas de puntos (referencia manual)**

| Caso | Puntos |
|------|--------|
| Resultado exacto | 5 |
| Ganador + diferencia de goles | 3 |
| Solo ganador (empate cuenta) | 1 |
| Incorrecto | 0 |

**Checklist 7B:** `[ ] OK` `[ ] Falla` `[ ] N/A (sin scoring en dev)`

---

## Parte 8 — Player: agente y conocimiento (Chat B, post-onboarding)

> **Gherkin ref:** FIX-01, KB-01. Ejecutar con M3 completo.

| # | Acción (Chat Player) | Resultado esperado |
|---|----------------------|-------------------|
| 8.1 | Enviá `¿A qué hora juega Argentina en el Mundial 2026?` | Respuesta con horario/fecha o mensaje honesto sin dato |
| 8.2 | Enviá `partidos del grupo A` | Lista de partidos legible |
| 8.3 | Enviá `historia de los trofeos del mundial` | Texto factual; no error genérico |
| 8.4 | Enviá `receta de pizza napolitana` | Rechazo amable (guardrail), no receta larga |

**Checklist Parte 8:** `[ ] OK` `[ ] Falla`

---

## Parte 9 — Player: trivia personal (Chat B)

> **Gherkin ref:** TRIV-01, TRIV-02.

| # | Acción (Chat Player) | Resultado esperado |
|---|----------------------|-------------------|
| 9.1 | Enviá `/trivia` | Pregunta + botones A B C D |
| 9.2 | Tocá una opción | Mensaje de acierto/error + puntos; texto legible (no JSON crudo) |
| 9.3 | Enviá `/mi_puntuacion` | **Trivia (perfil)** puede haber subido si hubo acierto |
| 9.4 | (Opcional) Repetí `/trivia` hasta 6 veces en el día | La 6.ª muestra límite diario |

**Checklist Parte 9:** `[ ] OK` `[ ] Falla` `[ ] N/A`

---

## Parte 10 — Admin: funcionalidades exclusivas (Chat A)

> Ejecutar después del recorrido Player o en paralelo con segundo dispositivo.

### 10.1 Invitaciones avanzadas (SPEC-029)

| # | Acción (Chat Admin) | Resultado esperado |
|---|---------------------|-------------------|
| 10.1.1 | `/invitar 1` → **Elegir otro grupo** → seleccionar un grupo | Link apunta a ese grupo, no GLOBAL |
| 10.1.2 | `/agregar-miembro <alias_player>` (alias del Parte 3) | Miembro agregado al grupo activo/admin |
| 10.1.3 | Si el alias no existe, probá alias inventado | Mensaje claro "no encontrado" |

### 10.2 Crear grupo para otro usuario

| # | Acción (Chat Admin) | Resultado esperado |
|---|---------------------|-------------------|
| 10.2.1 | `/crear-grupo-para <alias_player>` | Pide nombre del grupo |
| 10.2.2 | Escribí `Grupo Admin Para Player` | Pide avatar |
| 10.2.3 | Elegí avatar | Grupo creado; **owner** es el Player, no el Admin |
| 10.2.4 | **Player:** `/grupos` | Ve el nuevo grupo |

### 10.3 Panel admin de grupos

| # | Acción (Chat Admin) | Resultado esperado |
|---|---------------------|-------------------|
| 10.3.1 | `/admin-grupos` | Lista/panel de grupos del sistema (formato admin) |
| 10.3.2 | **Player:** `/admin-grupos` | "Solo el admin global puede usar este comando" |

### 10.4 Trivia admin (broadcast)

| # | Acción (Chat Admin) | Resultado esperado |
|---|---------------------|-------------------|
| 10.4.1 | `/trivia-admin` | Publica trivia; Admin ve pregunta en su chat |
| 10.4.2 | **Player:** revisar chat del bot | Llega la misma trivia (broadcast) |
| 10.4.3 | **Player:** responder con botón de la trivia | Puntos según nivel; cuenta como ronda |
| 10.4.4 | **Admin:** `/trivia-admin` otra vez | Pregunta **distinta** a la del Player en `/trivia` reciente |
| 10.4.5 | **Player:** `/trivia-admin` | Permiso denegado |

### 10.5 Help y menú admin

| # | Acción (Chat Admin) | Resultado esperado |
|---|---------------------|-------------------|
| 10.5.1 | `/help` | Incluye sección admin con trivia-admin, admin-grupos, crear_grupo_para |
| 10.5.2 | Menú `/` | Comandos admin visibles **solo** en chat del admin (scope personal) |

**Checklist Parte 10:** `[ ] OK` `[ ] Falla`

---

## Parte 11 — Owner: editar grupo e invitar en contexto (Chat B si es owner)

> Si el Player creó grupo en 4B; si solo es miembro, usar cuenta owner alternativa.

| # | Acción (Chat Owner) | Resultado esperado |
|---|---------------------|-------------------|
| 11.1 | `/editar-grupo` | Menú: Nueva invitación, Usuario existente, etc. |
| 11.2 | Tocá **🔗 Nueva invitación** | Link del grupo **sin** pedir elegir grupo otra vez |
| 11.3 | Tocá **➕ Usuario existente (alias)** | Pide escribir alias |
| 11.4 | Escribí alias de otro usuario existente | Lo agrega; **no** respuesta de guardrail/LLM |
| 11.5 | `/miembros` | Lista miembros del grupo |
| 11.6 | En medio de flujo pendiente, enviá `/cancel` | Vuelve al menú de edición |

**Checklist Parte 11:** `[ ] OK` `[ ] Falla` `[ ] N/A`

---

## Parte 12 — Regresiones rápidas (ambos roles)

| # | Acción | Resultado esperado |
|---|--------|-------------------|
| 12.1 | **Player** sin grupo privado (solo GLOBAL): `/partidos` | Pide crear/unirse a grupo |
| 12.2 | **Player** toca **👥 Grupos** | Lista grupos |
| 12.3 | **Player** toca **🏁 Resultados** | Ver 12.1 en 7A.5 |
| 12.4 | Reenviar mismo mensaje 2 veces rápido | Sin duplicar usuario en DB (operador verifica si puede) |

**Checklist Parte 12:** `[ ] OK` `[ ] Falla`

---

## Resumen del recorrido “feliz” (historia de usuario)

```text
Admin prepara entorno → Admin /invitar → Player abre link
  → Onboarding alias/equipo/idioma → Player en grupo privado
  → /partidos → elige partido → predice 2-0 → Listo
  → /mi_puntuacion (activas ≥ 1)
  → [si scoring en dev] /mi_puntuacion muestra pts del partido
  → [opcional] /trivia suma puntos trivia
Admin en paralelo: /trivia-admin, /admin-grupos, /crear-grupo-para
```

---

## Registro de ejecución

| Parte | Tester | Fecha | OK | Falla | N/A |
|-------|--------|-------|-----|-------|-----|
| 0 Preparación | | | | | |
| 1 Menú admin | | | | | |
| 2 Invitación | | | | | |
| 3 Onboarding | | | | | |
| 4 Grupo privado | | | | | |
| 5 Predicción | | | | | |
| 6 Completo | | | | | |
| 7A Puntuación vista | | | | | |
| 7B Puntuación partido | | | | | |
| 8 Agente/KB | | | | | |
| 9 Trivia | | | | | |
| 10 Admin | | | | | |
| 11 Owner grupo | | | | | |
| 12 Regresión | | | | | |

---

## Plantilla — Reporte de issue

```markdown
## Issue test manual

- **Parte / Paso:** (ej. 5.5)
- **Rol:** Admin | Player | Operador
- **Acción exacta:**
- **Esperado:**
- **Actual:** (texto del bot / captura)
- **Entorno:** dev, fecha deploy, commit si se conoce
- **Severidad:** Bloqueante | Importante | Menor
```

---

## Fuera de alcance (no marcar como bug)

| Funcionalidad | Notas |
|---------------|--------|
| Ranking detallado en `/grupos` | Mensaje "próximamente" |
| Goleador / MVP en `/completo` | "Próximamente" |
| Scoring automático E2E | Puede requerir job/manual en DynamoDB — Parte 7B N/A |
| Microsoft Teams | No implementado |
| Predicción vía lenguaje natural al agente | Usar comandos `/partidos` y `/predecir` |

---

*Actualizar este documento cuando cambien flujos de predicción, invitaciones o comandos admin.*
