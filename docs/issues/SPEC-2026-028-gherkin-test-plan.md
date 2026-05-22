# Plan de testeo Gherkin — Prode Mundial 2026 (dev)

| Campo | Valor |
|-------|--------|
| **Versión** | 2026-05-20 |
| **Canal** | Telegram (`@scalonia_bot` / dev) |
| **Entorno** | `ProdeTable-dev`, AWS `asap_dev`, Lambda webhook + AgentCore desplegados |
| **Referencia** | [SPEC-2026-028](SPEC-2026-028-regression-suite-features-implementadas.md) |

---

## Cómo usar este plan

1. **Pre-requisitos** (sección 2): deploy, fixture, usuarios de prueba.
2. Ejecutá los escenarios por **tag** (`@p0` primero).
3. Marcá cada escenario: ✅ OK | ❌ Falla | ⏭️ Omitido (motivo).
4. Si falla, copiá la plantilla de **Reporte de issue** (sección 3) en un issue o mensaje al equipo.

**Orden sugerido (~60–90 min):** Infra → Menú/atajos → Auth/Invitaciones → Grupos → Predicciones → Onboarding → Agente/KB → Trivias.

---

## 2. Pre-requisitos (Background)

```gherkin
# language: es
@infra
Feature: Pre-requisitos de entorno dev

  Background:
    Dado que la tabla DynamoDB "ProdeTable-dev" tiene partidos cargados
    Y que existe un usuario admin bootstrap en el sistema
    Y que la Lambda "telegram_webhook" está desplegada con el último commit de "dev"
    Y que AgentCore runtime está desplegado

  @p0
  Scenario: Fixture de partidos en DynamoDB
    Cuando el operador ejecuta el ingest del fixture
    Entonces existen al menos 72 partidos con fase "GROUP" en MATCH#

  @p0
  Scenario: Comandos registrados en Telegram
    Cuando el admin envía "/menu" al bot
    Entonces el bot responde confirmando menú actualizado
    Y aparece el teclado fijo con botones "Partidos", "Mi puntaje", "Grupos" y "Resultados"
    Y el menú "/" del chat lista "/partidos" entre los primeros comandos
```

**Comandos operador:**

```bash
py scripts/ingest_matches.py --env dev --profile asap_dev --execute
py scripts/register_telegram_commands.py --profile asap_dev --admin-chat-id <CHAT_ID_ADMIN>
# Rebuild + apply Lambda webhook y AgentCore según runbook del repo
```

---

## 3. Plantilla — Reporte de issue

Copiá y completá:

```markdown
## Issue de testeo

- **Escenario Gherkin:** (id, ej. PRED-07)
- **Tag:** @p0 / @p1
- **Rol:** Admin | Owner | Invitado
- **Pasos realizados:** (qué tocaste/escribiste exacto)
- **Esperado:** (del plan)
- **Actual:** (mensaje del bot, captura, error CloudWatch si hay)
- **Commit / deploy:** (fecha deploy Lambda, hash git si sabés)
- **Severidad:** Bloqueante | Importante | Menor
```

---

## 4. Menú Telegram y atajos fijos

```gherkin
@telegram @ui @p0
Feature: Menú de comandos y teclado fijo (ReplyKeyboard)

  Background:
    Dado un usuario "Owner" con cuenta ACTIVE
    Y que "Owner" es dueño de un grupo privado "Los Pibes"
    Y que el grupo activo de predicción es "Los Pibes"

  @p0
  Scenario: Teclado fijo envía el comando equivalente
    Cuando "Owner" toca el botón "⚽ Partidos"
    Entonces el bot muestra la lista paginada de fase de grupos
    Y no responde con mensaje de guardrail del agente

  @p0
  Scenario: Atajo Mi puntaje
    Cuando "Owner" toca el botón "📊 Mi puntaje"
    Entonces el bot muestra "Mi puntuación" con totales del perfil

  @p0
  Scenario: Atajo Grupos
    Cuando "Owner" toca el botón "👥 Grupos"
    Entonces el bot lista los grupos del usuario incluyendo "Los Pibes"

  @p0
  Scenario: Atajo Resultados
    Cuando "Owner" toca el botón "🏁 Resultados"
    Entonces el bot muestra partidos finalizados o mensaje claro si no hay ninguno

  @p1
  Scenario: Menu slash refresca comandos
    Cuando "Owner" envía "/menu"
    Entonces el bot confirma menú actualizado
    Y el teclado fijo permanece visible

  @p1
  Scenario: Help lista atajos
    Cuando "Owner" envía "/help"
    Entonces la respuesta menciona "/partidos", "/mi_puntuacion", "/grupos" y "/menu"
```

---

## 5. Autenticación y acceso

```gherkin
@auth @p0
Feature: Control de acceso Telegram

  @p0
  Scenario: Usuario sin registro no usa el agente libremente
    Dado un chat de Telegram sin perfil en el sistema
    Cuando ese chat envía "contame del mundial"
    Entonces el bot no invoca una respuesta larga del agente sin invitación
    Y muestra mensaje de acceso o invitación requerida

  @p0
  Scenario: Usuario ACTIVE tras invitación válida
    Dado un link de invitación válido con cupos disponibles
    Cuando el invitado abre "/start <invite_id>"
    Entonces se crea perfil ACTIVE
    Y el bot muestra bienvenida u onboarding M1
```

---

## 6. Invitaciones (SPEC-020 + SPEC-029)

```gherkin
@invitations @p0
Feature: Invitaciones y membresías

  Background:
    Dado un usuario "Admin" con rol admin global
    Y un usuario "Vic" con cuenta ACTIVE y alias "vic"
    Y un usuario "Nuevo" sin cuenta previa

  @p0
  Scenario: Admin crea invitación GLOBAL por defecto
    Cuando "Admin" envía "/invitar 2"
    Entonces el bot muestra teclado con opción GLOBAL y "Elegir otro grupo"
    Cuando "Admin" elige GLOBAL
    Entonces el bot devuelve link con 2 cupos y código de invitación

  @p0
  Scenario: Usuario nuevo usa deep link
    Dado una invitación ACTIVE con cupo disponible
    Cuando "Nuevo" abre "/start <invite_id>"
    Entonces "Nuevo" queda ACTIVE
    Y no recibe solo "Ya estás registrado" sin alta

  @p0
  Scenario: Usuario existente se une con deep link
    Dado una invitación a un grupo "Torneo"
    Cuando "Vic" abre "/start <invite_id>" sin ser miembro de "Torneo"
    Entonces "Vic" es agregado a "Torneo"
    Y el bot confirma suma al grupo

  @p0
  Scenario: Usuario existente ya miembro — idempotente
    Dado que "Vic" ya es miembro de "Torneo"
    Cuando "Vic" abre "/start <invite_id>" del mismo grupo
    Entonces el bot indica que ya forma parte del grupo
    Y no consume cupo de invitación

  @p0
  Scenario: Unirme con código para existente
    Dado una invitación ACTIVE con id "abc12345"
    Cuando "Vic" envía "/unirme abc12345"
    Entonces el bot confirma unión al grupo destino

  @p1
  Scenario: Mis invitaciones admin
    Cuando "Admin" envía "/mis_invitaciones"
    Entonces el bot lista invitaciones creadas por "Admin" con estado y link
```

---

## 7. Grupos (SPEC-026)

```gherkin
@groups @p0
Feature: Grupos privados y administración

  Background:
    Dado un usuario "Owner" ACTIVE sin grupo propio previo

  @p0
  Scenario: Crear grupo con avatar
    Cuando "Owner" envía "/crear-grupo"
    Y completa nombre "Los Pibes"
    Y elige avatar "⚽" en el teclado inline
    Entonces el bot confirma grupo creado
    Y muestra link de invitación inicial

  @p0
  Scenario: Editar grupo y contexto de invitación
    Dado que "Owner" es dueño de "Los Pibes"
    Cuando "Owner" envía "/editar-grupo"
    Entonces el bot muestra menú "Nueva invitación", "Usuario existente (alias)", etc.

  @p0
  Scenario: Invitar desde menú de edición sin re-preguntar grupo
    Dado que "Owner" está en menú editar de "Los Pibes"
    Cuando "Owner" toca "🔗 Nueva invitación"
    Entonces el bot genera link para "Los Pibes" directamente
    Y no pide "elegir grupo destino" genérico

  @p0
  Scenario: Agregar miembro existente por alias desde menú
    Dado que "Vic" existe con alias "vic"
    Y que "Owner" editando "Los Pibes" tocó "➕ Usuario existente (alias)"
    Cuando "Owner" escribe "vic"
    Entonces "Vic" queda miembro de "Los Pibes"
    Y el bot confirma sin pasar por el agente LLM

  @p0
  Scenario: Agregar miembro por comando
    Cuando "Owner" envía "/agregar-miembro vic"
    Entonces "Vic" queda en el grupo activo de "Owner"
    O el bot pide elegir grupo si "Owner" es admin con varios grupos

  @p1
  Scenario: Admin crea grupo para otro usuario
    Cuando "Admin" envía "/crear-grupo-para vic"
    Y completa nombre y avatar del grupo
    Entonces el grupo tiene owner "Vic" y no "Admin"

  @p1
  Scenario: Owner no puede crear segundo grupo Free
    Dado que "Owner" ya tiene un grupo propio
    Cuando "Owner" envía "/crear-grupo"
    Entonces el bot rechaza con mensaje de límite plan Free

  @p2
  Scenario: Cancelar flujo pendiente
    Dado que "Owner" está agregando miembro por alias
    Cuando "Owner" envía "/cancel"
    Entonces vuelve al menú de edición del grupo
```

---

## 8. Predicciones (SPEC-021 — MVP actualizado)

```gherkin
@predictions @p0
Feature: Predicciones por grupo

  Background:
    Dado un usuario "Player" ACTIVE
    Y que "Player" es miembro del grupo privado "Los Pibes"
    Y que el grupo activo de predicción es "Los Pibes"
    Y que hay partidos GROUP en fixture con veda abierta

  @p0
  Scenario: Sin grupo privado no puede predecir
    Dado un usuario "SoloGlobal" solo en grupo GLOBAL
    Cuando "SoloGlobal" envía "/partidos"
    Entonces el bot indica que necesita un grupo privado
    Y ofrece crear o unirse

  @p0
  Scenario: Listado paginado fase de grupos
    Cuando "Player" envía "/partidos"
    Entonces el bot muestra encabezado "Fase de grupos"
    Y muestra "Página 1/N" con hasta 8 partidos
    Y cada línea incluye banderas emoji junto a códigos FIFA
    Y hay botones "Siguiente" si N mayor que 1

  @p0
  Scenario: Navegar página de partidos
    Dado que "Player" está en página 1 de "/partidos"
    Cuando "Player" toca "Siguiente ▶️"
    Entonces el bot muestra página 2 con otros partidos
    Y el botón "◀️ Anterior" vuelve a página 1

  @p0
  Scenario: Predicción rápida con botón de marcador
    Dado que "Player" abrió un partido con veda abierta
    Cuando "Player" toca marcador "2-0"
    Entonces el bot confirma "Predicción rápida guardada"
    Y muestra banderas y marcador en el mensaje
    Y ofrece botones "Listo (solo resultado)" y "Predicción completa"

  @p0
  Scenario: Otro marcador con texto libre corto
    Dado que "Player" abrió el mismo partido
    Cuando "Player" toca "✏️ Otro marcador"
    Entonces el bot pide escribir marcador ej. "3:1" o "0-1"
    Cuando "Player" escribe "3-1"
    Entonces la predicción "3-1" queda guardada
    Y no pide comando "/predecir ARG ..."

  @p0
  Scenario: Predecir por comando con equipos
    Dado un partido abierto MEX vs RSA en fixture
    Cuando "Player" envía "/predecir MEX 2-0 RSA"
    Entonces el bot guarda la predicción para el grupo activo

  @p0
  Scenario: Veda cerrada bloquea guardar
    Dado un partido con veda activa o ya finalizado sin predicción previa
    Cuando "Player" intenta guardar marcador desde "/partidos"
    Entonces el bot no ofrece botón numérico
    O muestra estado "veda" o "Finalizado"

  @p1
  Scenario: Cambiar grupo activo para predecir
    Dado que "Player" pertenece a "Los Pibes" y "Amigos"
    Cuando "Player" usa "Cambiar grupo" en "/partidos"
    Y elige "Amigos"
    Entonces las predicciones siguientes se guardan en "Amigos"

  @p1
  Scenario: Actualizar predicción existente
    Dado que "Player" ya predijo 1-0 en un partido abierto
    Cuando "Player" vuelve a abrir ese partido y confirma cambiar
    Y elige "2-1"
    Entonces el bot indica predicción actualizada

  @p2
  Scenario: Empate en fase eliminatoria requiere definición
    Dado un partido KO con veda abierta
    Cuando "Player" elige marcador "1-1"
    Entonces el bot pide tiempo extra o penales y ganador
    Cuando "Player" completa ET/PEN y ganador
    Entonces la predicción queda guardada con playoff_via y playoff_winner
```

---

## 9. Predicción completa (wizard)

```gherkin
@predictions @completo @p1
Feature: Predicción completa — variables opcionales

  Background:
    Dado un usuario "Player" con predicción ACTIVE 2-0 en partido abierto del grupo "Los Pibes"

  @p0
  Scenario: Completar desde botón post-guardado
    Cuando "Player" toca "🎯 Predicción completa"
    Entonces el bot inicia wizard "Paso 1 — tarjeta roja"
    Y muestra opciones No/Sí/Saltar/Terminar

  @p0
  Scenario: Completar desde comando slash
    Cuando "Player" envía "/completo"
    Entonces el bot abre wizard del partido correcto
    Y no dice "no tenés predicciones" si hay una ACTIVE con veda abierta

  @p1
  Scenario: Guardar expulsión en wizard
    Dado el wizard de predicción completa abierto
    Cuando "Player" toca "🟥 Sí habrá roja"
    Entonces el bot confirma expulsión guardada
    Y cierra wizard con mensaje de predicción completa cerrada

  @p1
  Scenario: Listo solo resultado sin wizard
    Cuando "Player" toca "⚡ Listo (solo resultado)"
    Entonces el bot confirma sin exigir wizard
```

**Pendiente spec (marcar N/A en test):** goleador y MVP en wizard — esperado mensaje "próximamente".

---

## 10. Onboarding (SPEC-019)

```gherkin
@onboarding @p0
Feature: Onboarding M1 Telegram y M2/M3 agente

  Background:
    Dado un invitado "Nuevo" que acaba de usar deep link válido

  @p0
  Scenario: M1 alias inválido
    Cuando "Nuevo" envía alias "x"
    Entonces el bot rechaza y sugiere alternativas

  @p0
  Scenario: M1 flujo completo
    Cuando "Nuevo" elige alias válido "testuser01"
    Y elige equipo favorito
    Y elige idioma
    Entonces el onboarding avanza más allá de M1_PENDING
    Y muestra resumen de perfil

  @p0
  Scenario: Pregunta libre durante M1 no bloquea si es pregunta
    Dado "Nuevo" en M1_PENDING
    Cuando "Nuevo" envía "¿cuántos equipos hay en el mundial?"
    Entonces el bot no fuerza respuesta de alias como si fuera onboarding
    O deriva a agente/KB según implementación

  @p0
  Scenario: Post M3 pregunta concreta usa conocimiento
    Dado "Nuevo" en etapa M3 completada
    Cuando "Nuevo" pregunta "¿Cuándo juega Argentina?"
    Entonces la respuesta menciona fixture u horario
    Y no es solo mensaje genérico de bienvenida repetido
```

---

## 11. Fixture y agente (match_tool, KB, web)

```gherkin
@agent @fixture @kb @p0
Feature: Consultas al agente — fixture y conocimiento

  Background:
    Dado un usuario "Fan" ACTIVE en etapa M3

  @p0
  Scenario: Horario y rival desde fixture
    Cuando "Fan" pregunta "¿A qué hora juega México el primer partido?"
    Entonces la respuesta incluye fecha u hora coherente con fixture
    Y no inventa partido inexistente sin avisar

  @p0
  Scenario: Partidos de un grupo
    Cuando "Fan" pregunta "partidos del grupo A del mundial 2026"
    Entonces lista partidos del grupo A con formato legible

  @p0
  Scenario: Bracket u octavos
    Cuando "Fan" pregunta "¿A quién podría enfrentar Brasil en octavos?"
    Entonces responde con escenarios o bracket sin error genérico

  @p0
  Scenario: Historia desde knowledge base
    Cuando "Fan" pregunta "historia de los trofeos del mundial"
    Entonces contenido factual desde KB o web
    Y no solo "Hubo un error procesando tu mensaje"

  @p1
  Scenario: Comparativa jugadores no mezcla fixture inventado
    Cuando "Fan" pregunta "compará Messi y Ronaldo en mundiales"
    Entonces no lista horarios falsos de partidos del mundial 2026 como hechos
```

---

## 12. Trivias (SPEC-025)

```gherkin
@trivia @p0
Feature: Trivias personal, grupo y admin

  Background:
    Dado un usuario "Fan" ACTIVE
    Y un usuario "Admin" admin global

  @p0
  Scenario: Trivia personal con botones
    Cuando "Fan" envía "/trivia"
    Entonces aparece pregunta con botones A B C D
    Cuando "Fan" responde con un botón
    Entonces mensaje legible con resultado
    Y puntos si corresponde

  @p0
  Scenario: Límite 5 trivias por día
    Dado que "Fan" ya jugó 5 trivias hoy
    Cuando "Fan" envía "/trivia"
    Entonces el bot informa límite diario alcanzado

  @p1
  Scenario: Admin trivia broadcast
    Cuando "Admin" envía "/trivia-admin"
    Entonces "Fan" recibe pregunta broadcast
    Cuando "Fan" responde con callback de trivia
    Entonces suma puntos y cuenta ronda

  @p1
  Scenario: Owner trivia a grupo
    Dado "Owner" dueño de grupo con miembros
    Cuando "Owner" envía "/trivia-grupo"
    Entonces miembros del grupo reciben trivia

  @p1
  Scenario: Preguntas distintas entre usuarios
    Cuando "Admin" envía "/trivia-admin"
    Y luego "Fan" envía "/trivia"
    Entonces las dos preguntas son distintas en la misma ventana temporal
```

---

## 13. Guardrails

```gherkin
@guardrails @p1
Feature: Guardrails del agente

  Background:
    Dado un usuario "Fan" ACTIVE M3

  @p1
  Scenario: Off-topic rechazado
    Cuando "Fan" pregunta "dame una receta de pizza napolitana"
    Entonces respuesta de rechazo amable o guardrail
    Y no respuesta larga de cocina

  @p1
  Scenario: Fútbol válido no bloqueado
    Cuando "Fan" pregunta "reglas del fuera de juego en el mundial"
    Entonces respuesta relacionada al fútbol
```

---

## 14. Regresión cruzada post-deploy

```gherkin
@regression @p0
Feature: Smoke post-deploy

  @p0
  Scenario: Mensaje libre no error genérico
    Cuando "Fan" envía "hola"
    Entonces responde en menos de 20 segundos
    Y no muestra "Hubo un error. Por favor intentá de nuevo"

  @p0
  Scenario: Predicción no cae en guardrail
    Dado "Player" en flujo "/partidos"
    Cuando "Player" escribe "2-1" tras "Otro marcador"
    Entonces guarda predicción
    Y no mensaje de guardrail del agente
```

---

## 15. Matriz de trazabilidad — Tags ↔ Specs

| Tag Gherkin | SPEC / área | Prioridad manual |
|-------------|------------|------------------|
| `@infra` | Deploy, ingest | P0 antes de todo |
| `@telegram @ui` | Menú `/`, ReplyKeyboard | P0 |
| `@auth` | SPEC-018 | P0 |
| `@invitations` | SPEC-020, SPEC-029 | P0 |
| `@groups` | SPEC-026 | P0 |
| `@predictions` | SPEC-021 | P0 |
| `@predictions @completo` | SPEC-021 wizard | P1 |
| `@onboarding` | SPEC-019, ISSUE-025 | P0 |
| `@fixture @kb @agent` | SPEC-026/017/023 | P0 |
| `@trivia` | SPEC-025 | P0–P1 |
| `@guardrails` | SPEC-015 | P1 |

---

## 16. Criterios de cierre del testeo

- [ ] 100 % escenarios `@p0` OK o issue documentado  
- [ ] ≥ 90 % `@p1` OK o issue documentado  
- [ ] Deploy verificado (Lambda + AgentCore + `register_telegram_commands`)  
- [ ] Al menos 2 roles probados: Admin + Owner + Invitado  
- [ ] Issues reportados con plantilla §3  

**Comando automatizado (complementario, no reemplaza Telegram E2E):**

```bash
py -m pytest tests/unit/ -q --no-cov
py -m pytest tests/smoke/ -q --no-cov
```

---

## 17. Issues conocidos / fuera de alcance (no fallar el test)

| Tema | Comportamiento esperado al testear |
|------|-----------------------------------|
| Rankings `/ranking` | No implementado — N/A |
| Scoring automático post-partido | Solo unit `scoring_engine` |
| Goleador/MVP en `/completo` | Wizard parcial — "próximamente" |
| Microsoft Teams | No implementado |
| `prediction_tool` en agente | Predicciones vía Lambda/Telegram solamente |

---

*Documento vivo: actualizar cuando se sumen features o cambie el flujo de predicciones/invitaciones.*
