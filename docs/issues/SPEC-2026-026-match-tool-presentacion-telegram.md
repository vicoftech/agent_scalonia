# SPEC-2026-026 — Presentación de `match_tool` (banderas, orden lógico, ficha vs lista)

| Campo | Valor |
|-------|--------|
| **SPEC-ID** | SPEC-2026-026 |
| **Tipo** | Mejora UX / formato de salida |
| **Severidad** | Media-alta (fixture es flujo core del Prode) |
| **Sprint sugerido** | Sprint 1–2 |
| **Modo** | IA-Assisted |
| **Dependencias** | Fixture en DynamoDB (`MATCH#*/DETAILS`), `match_tool`, `MatchService`, `fixture_prefetch` |
| **Estado** | Propuesto |

---

## 1. Objetivo

Mejorar la **interfaz textual** que ve el usuario en Telegram (y el contexto que recibe el LLM) cuando consulta partidos del Mundial 2026, sin cambiar la fuente de verdad (DynamoDB + `match_tool`).

La salida debe:

1. Mostrar **banderas** junto a cada selección (emoji Unicode, compatible con Telegram texto plano).
2. Ordenar la información en un **orden lógico y fijo**: identidad del partido → equipos → **día** → **horario** → **zona horaria** → **sede** (estadio + ciudad/país).
3. Elegir automáticamente entre:
   - **Ficha individual** (`view=card`) cuando el resultado es **un solo partido**.
   - **Lista agrupada** (`view=list`) cuando hay **varios** partidos.

---

## 2. Problema actual

Implementación en `src/services/match_service.py`:

```text
#12 ARG vs MEX (GROUP A) — 2026-06-21T19:00:00Z UTC · Ciudad · Estadio [SCHEDULED]
```

| Limitación | Impacto |
|------------|---------|
| Códigos FIFA crudos (`ARG`) sin bandera | Poco escaneable en móvil |
| `kickoff_utc` en ISO 8601 | El usuario piensa en hora local del partido |
| Orden campos mezclado (hora antes que sede, sede opcional al final) | Difícil leer de un vistazo |
| Misma línea compacta para 1 o N partidos | Un partido merece más detalle; muchos partidos necesitan agrupación por día |
| `fixture_prefetch` reutiliza `format_list` | Misma UX pobre en precarga Telegram |

**No** se pide cambiar acciones de `match_tool` (`search`, `get`, `next`, `group`, …) ni el esquema DynamoDB en esta spec (salvo campo opcional de timezone — ver §6).

---

## 3. Alcance

### En scope

- Módulo de presentación compartido (presenter) usado por `MatchService`, `match_tool` y `fixture_prefetch`.
- Banderas emoji para códigos FIFA del fixture 2026 (tabla de mapeo FIFA → ISO-3166-1 alpha-2 → regional indicators).
- Formato **card** (1 partido) y **list** (2+ partidos).
- Agrupación de listas por **fecha local del partido** (según timezone de la sede).
- Línea secundaria con hora **UTC** para evitar ambigüedad.
- Tests unitarios de formato (snapshots de strings).
- Documentación en docstring de `match_tool` para que el LLM no reformatee destructivamente.

### Fuera de scope (futuro)

- Telegram `parse_mode` Markdown/HTML (hoy el webhook envía texto plano).
- Adaptive Cards (Teams).
- Mapas, imágenes de estadios o links externos.
- Conversión a zona horaria del **usuario** vía geolocalización (solo sede + UTC en v1; ver §5.3).

---

## 4. Diseño de presentación

### 4.1 Orden lógico de campos (contrato)

Para **cada partido**, el orden semántico es siempre:

| # | Campo | Fuente DynamoDB | Ejemplo |
|---|--------|-----------------|--------|
| 1 | Encabezado | `match_number`, `phase`, `group_letter` | `Partido #12 · Fase de grupos · Grupo A` |
| 2 | Enfrentamiento | `home_team`, `away_team` + banderas | `🇦🇷 Argentina — 🇲🇽 México` |
| 3 | Día | derivado de `kickoff_utc` + TZ sede | `Sábado 21 de junio de 2026` |
| 4 | Horario local | derivado de `kickoff_utc` + TZ sede | `19:00` |
| 5 | Zona horaria | tabla sede/ciudad o campo `timezone` | `(Centro de México, UTC−6)` |
| 6 | Hora UTC | `kickoff_utc` | `02:00 UTC (día sig.)` si cruza medianoche |
| 7 | Sede | `venue`, `city`, `country` | `🏟 Estadio Azteca · Ciudad de México, México` |
| 8 | Estado | `status` | `Programado` / `En juego` / `Finalizado` |
| 9 | Meta (opcional) | `match_id` solo en `action=get` o debug | `id=…` al final, una línea |

Si `venue`/`city` son `"Por confirmar"`, mostrar **una sola línea** `Sede: por confirmar` (no omitir silenciosamente).

### 4.2 Vista ficha (`view=card`) — exactamente 1 partido

Usar cuando:

- `match_tool` `action=get` devuelve un partido.
- Cualquier búsqueda que retorne **len(rows) == 1**.

Ejemplo objetivo (texto plano Telegram):

```text
⚽ Partido #12 · Fase de grupos · Grupo A

🇦🇷 Argentina  vs  🇲🇽 México

📅 Sábado 21 de junio de 2026
🕐 19:00 (Ciudad de México, UTC−6)
🌐 01:00 UTC (domingo)

🏟 Estadio Azteca
📍 Ciudad de México, México

Estado: Programado
```

Reglas:

- Separadores en blanco entre bloques (legibilidad móvil).
- Nombre legible del país además del código (tabla `TEAM_DISPLAY_NAMES` junto a `TEAM_ALIASES`).
- `vs` centrado conceptualmente; en monospace no hace falta alinear columnas.

### 4.3 Vista lista (`view=list`) — 2 o más partidos

Usar cuando:

- `next`, `group`, `search`, `list` con múltiples filas.
- `fixture_prefetch` con varios partidos.

Estructura:

1. **Título** con contexto (`Próximos partidos`, `Grupo A`, `Argentina — fixture`).
2. **Agrupación por día** (fecha en TZ de la sede): encabezado de día una sola vez.
3. Cada ítem = **una línea compacta** + datos esenciales en orden: hora local → banderas + códigos → `#n` → sede abreviada.

Ejemplo:

```text
📋 Próximos partidos · horarios en zona de la sede

── Sábado 21 jun 2026 ──
  19:00 (UTC−6)  🇦🇷 ARG — 🇲🇽 MEX  ·  #12  ·  CDMX
  22:00 (UTC−6)  🇺🇸 USA — 🇨🇦 CAN  ·  #13  ·  Los Angeles

── Domingo 22 jun 2026 ──
  16:00 (UTC−5)  🇧🇷 BRA — 🇪🇸 ESP  ·  #14  ·  Nueva York
```

Reglas:

- Máximo **15** ítems por mensaje en lista (ya existe `limit`); si hay más, pie de lista: `… y N partidos más. Pedí con más filtros o group_letter.`
- Orden cronológico ascendente por `kickoff_utc` dentro de cada día.
- En listas, **no** repetir estadio completo si no cabe; usar `city` o abreviatura de 3–20 caracteres.

### 4.4 Selección automática card vs list

| Condición | Vista |
|-----------|--------|
| `len(matches) == 0` | Mensaje vacío (sin cambio semántico) |
| `len(matches) == 1` | `card` |
| `len(matches) >= 2` | `list` |

Parámetro opcional para debugging / agente: `presentation: "card" | "list" | "auto"` (default `auto`) en `MatchService.format_matches(...)`.

---

## 5. Banderas y zonas horarias

### 5.1 Banderas (emoji)

Nuevo módulo sugerido: `src/formatting/team_flags.py`

```python
def flag_emoji(fifa_code: str) -> str:
    """ARG → 🇦🇷 vía mapeo FIFA-3 → ISO-3166-1 alpha-2 → regional indicators."""
```

- Tabla `FIFA_TO_ISO2: dict[str, str]` para los 48+ equipos del Mundial 2026 y códigos especiales:
  - `ENG` → `GB` (bandera 🇬🇧; aceptable en v1; documentar excepción).
  - `USA` → `US`, `MEX` → `MX`, etc.
- Si código desconocido: **sin bandera**, solo `ARG` en mayúsculas (no fallar).
- Función `format_team(fifa_code: str, *, with_name: bool = False) -> str` → `🇦🇷 Argentina` o `🇦🇷 ARG`.

**Restricción Telegram:** solo texto UTF-8; los regional indicators funcionan en iOS/Android/Desktop.

### 5.2 Zona horaria de la sede (v1)

Prioridad de resolución TZ:

1. Campo `timezone` en `MATCH#/DETAILS` si existe (ej. `America/Mexico_City`).
2. Tabla estática `CITY_COUNTRY_TO_TZ` en `src/fixtures/worldcup2026_venues.py` (MVP).
3. Fallback `UTC` + mostrar solo hora UTC con aviso `(zona local no disponible)`.

Formateo con `zoneinfo` (stdlib Python 3.12):

- Día y hora local desde `kickoff_utc`.
- Etiqueta corta `UTC−6` o nombre IANA abreviado legible.

### 5.3 Zona horaria del usuario (v2 — opcional)

- Parámetro futuro `user_timezone` (ej. desde perfil Dynamo `USER#/PROFILE`).
- En listas, prefijo: `Horarios en America/Argentina_Buenos_Aires`.
- **No bloquea** v1.

---

## 6. Cambios de datos (opcionales)

| Campo | Tabla | Obligatorio v1 |
|--------|--------|----------------|
| `timezone` | `MATCH#/DETAILS`, Aurora `matches` | No (tabla estática alcanza) |
| `home_team_name` / `away_team_name` | No | No — derivar de catálogo FIFA |

Si se agrega `timezone` al ingest del fixture, actualizar:

- `src/fixtures/match_fixture_builder.py`
- `MatchDAO.put_match`
- `sync_dynamo_to_aurora` mapping
- Alembic (solo CI/CD)

---

## 7. Arquitectura de código

```
src/formatting/
  team_flags.py          # FIFA → emoji + nombre display
  match_presenter.py     # format_card, format_list, pick_view

src/services/match_service.py
  format_match()         # delega a presenter (deprecar lógica inline)
  format_list()          # delega a presenter
  format_matches()       # nuevo: auto card/list

agent/tools/match_tool.py
  sin cambios de firma; retorna strings del presenter

infrastructure/lambdas/telegram_webhook/fixture_prefetch.py
  usar format_matches(..., presentation="auto")  # mismo aspecto que tool
```

**Regla DRY:** una sola implementación de presentación; prohibido duplicar formatos en prefetch vs tool.

### 7.1 Contrato para el LLM

`match_tool` docstring y bloque `[Fixture oficial]` en prefetch deben indicar:

> La salida ya viene formateada con banderas y horarios. **Repetí el contenido al usuario sin reordenar campos ni quitar banderas.** Podés añadir una frase introductorio corta.

En `agent/main.py` (línea fixture): reforzar que no “simplifique” `#12 ARG vs MEX` perdiendo emojis.

---

## 8. Criterios de aceptación (Gherkin)

```gherkin
Feature: Presentación match_tool SPEC-026

  Scenario: Un solo partido en formato ficha
    Given el usuario pregunta por el partido #12
    When match_tool action=get match_number=12
    Then la respuesta incluye banderas de ambos equipos
    And muestra día, hora local con zona, hora UTC y sede en ese orden
    And no usa viñetas de lista

  Scenario: Varios partidos en formato lista por día
    Given hay 5 partidos programados en 2 fechas distintas
    When match_tool action=next limit=5
    Then la respuesta agrupa por día con encabezado de fecha
    And cada línea muestra hora local, banderas, número de partido y ciudad
    And los partidos están ordenados cronológicamente

  Scenario: Búsqueda con un único resultado usa ficha
  Scenario: Grupo con 6 partidos usa lista
  Scenario: Código FIFA sin bandera en catálogo muestra solo código sin error
  Scenario: fixture_prefetch usa el mismo formato que match_tool
```

---

## 9. Plan de tareas

| ID | Tarea | Est. | Modo |
|----|--------|------|------|
| TASK-026-001 | `team_flags.py` + tests mapeo FIFA→emoji | 2h | auto |
| TASK-026-002 | `worldcup2026_venues.py` (TZ por ciudad/sede) | 2h | assisted |
| TASK-026-003 | `match_presenter.py` card + list + auto | 4h | assisted |
| TASK-026-004 | Integrar en `MatchService` + deprecar format inline | 1h | auto |
| TASK-026-005 | `fixture_prefetch` usa presenter | 1h | auto |
| TASK-026-006 | Actualizar docstrings `match_tool` + prompt agente | 1h | assisted |
| TASK-026-007 | Tests snapshot + E2E manual Telegram | 2h | manual |

**Total estimado:** ~13h

---

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Mensaje > 4096 chars en grupos completos | Paginación: `format_list` retorna `list[str]` y `match_tool` envía primer chunk + “pedí grupo X página 2” o truncar con contador |
| Banderas no se ven en cliente antiguo | Fallback a códigos FIFA; rare en Telegram 2026 |
| ENG/GB bandera incorrecta | Documentar; opción texto `🏴 Inglaterra` sin regional indicator |
| LLM reformatea y rompe emojis | Instrucción en prefetch + system prompt |
| TZ incorrecta para sede “Por confirmar” | Mostrar solo UTC explícito |

---

## 11. Métricas de éxito

- En prueba manual con 3 usuarios, **≥90%** identifica correctamente día y hora local sin preguntar “¿en qué zona?”.
- Longitud promedio de ida y vuelta para “¿cuándo juega Argentina?” **no aumenta** (el agente no necesita re-explicar UTC).
- Cero regresiones en tests existentes de `MatchService` / ingest fixture.

---

## 12. Referencias

- `agent/tools/match_tool.py`
- `src/services/match_service.py`
- `infrastructure/lambdas/telegram_webhook/fixture_prefetch.py`
- `src/dao/dynamo/match_dao.py` (campos `kickoff_utc`, `venue`, `city`, `country`)
- `.cursor/rules/02-features.mdc` — SC fixture / match_tool
