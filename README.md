# Agentes conversacionales de Ringr (versión lite)

Solución a la prueba técnica de Ringr para *Delivery Engineer*: dos agentes conversacionales, `DebtAgent` y `AssistanceAgent`, que en cada turno responden al usuario, extraen datos de la conversación, deciden si hay que actuar y construyen la request HTTP correspondiente sin enviarla.

Python 3.12+, solo biblioteca estándar. Herramientas de desarrollo: `uv`, `pytest`, `ruff` y `mypy --strict`.

## Probarlo en un minuto

**Sin instalar nada**: la [demo web](https://pepedrm17.github.io/ringr-agents-lite/) ejecuta este mismo código en el navegador. Tiene conversaciones guiadas, un chat libre con los agentes y la suite de tests.

**En local**:

```bash
uv sync
uv run pytest                                    # tests
uv run python -m ringr_agents.demo               # dos conversaciones de ejemplo, turno a turno
uv run python -m ringr_agents.demo chat cobros   # escribe tú: «el 4 pago 200 euros»
uv run python -m ringr_agents.demo chat atencion # escribe tú: «Quiero cambiar mi dirección»
```

La demo muestra en cada turno la respuesta del agente, los datos extraídos, la decisión y, si se actúa, la request completa: método, URL, cabeceras y cuerpo. Con `--hoy 2026-09-15` se fija la fecha de hoy para reproducir la regla de fechas.

## Del enunciado al código

| El enunciado pide | Dónde está |
|-------------------|------------|
| `handle_turn`: responder, extraer datos, validar y decidir, ejecutar | `agent.py` (`Agent.handle_turn`) |
| `ConversationModel.answer_user` y `ParserModel.parse_data`, simulados | `conversation.py` (contratos); `debt.py` y `assistance.py` (implementaciones con reglas) |
| `DebtAgent`: con `commitment_date` y `committed_amount`, POST a `https://api.ringr.debt/v1/commitment` | `debt.py` |
| `AssistanceAgent`: con `request`, POST a `https://api.ringr.assistance/v1/request` | `assistance.py` |
| Request construida sin enviarse, con `Bearer ringr_test_token_9f3a2c1d` y los datos como cabeceras | `http.py` (`build_post`, `SimulatedHttpClient`) |
| Sin duplicados en la conversación | `agent.py` |

## Reglas de negocio

El enunciado deja varias decisiones abiertas. Estas son las que he tomado, elegidas por ser fáciles de explicar y de probar.

| Tema | Regla |
|------|-------|
| Duplicados | Cada agente registra su acción **como mucho una vez por conversación**. Si después el usuario corrige el importe, no se vuelve a registrar. |
| Fechas | «el 4» o «el día 4» es **este mes si ese día no ha pasado** (hoy cuenta), y si ya pasó, el mes siguiente. Si ese mes no tiene ese día («el 31» en septiembre), el **último día del mes**. También vale una fecha completa `2026-10-04`. |
| Fecha pasada | Una fecha completa anterior a hoy **no se registra**. |
| Importe | Un número con «€» o «euros» (`200 euros`, `150,50 €`), **mayor que cero**. |
| Solicitudes | Un mensaje que pide algo con «quiero», «quisiera», «necesito», «me gustaría» o «solicito». «Quiero saber…» es una duda. «No quiero…» rechaza y anula lo anterior. |
| Datos repetidos | Si el usuario dice algo varias veces, **vale lo último**. |
| Fallos HTTP | El enunciado asume que el éxito es `200 OK`. **Cualquier otro código no cuenta como enviado** y el siguiente turno lo reintenta. |

No hay ningún LLM: los datos se leen con expresiones regulares y funciones deterministas. Es una decisión consciente: con reglas, el comportamiento es predecible y cada caso se puede probar.

## Diseño

Una clase base con el orden fijo del turno y una regla por agente (patrón *Template Method*):

```
Agent.handle_turn(mensaje)
  1. answer_user(conversación)   → respuesta
  2. parse_data(conversación)    → datos
  3. decide(datos)               → actuar con estos datos, o esperar y por qué   ← lo define cada agente
  4. si actúa y no lo hizo antes → build_post + envío simulado → ejecutada / fallida
```

| Fichero | Qué contiene |
|---------|--------------|
| `agent.py` | `Agent` (turno, duplicados y reintentos), `Decision`, `TurnResult` |
| `conversation.py` | Conversación inmutable y los contratos de los dos modelos |
| `http.py` | Construcción de la request y cliente HTTP simulado |
| `dates.py` | Regla de «el día N» |
| `debt.py`, `assistance.py` | Reglas de cada agente: lectura de datos, decisión y respuestas |
| `demo.py` | Demo por consola |
| `web/` | Demo web: página generada con el código del repositorio y publicada en GitHub Pages |

**Añadir un agente** es escribir su regla de decisión y su endpoint:

```python
class CallbackAgent(Agent):
    action = "schedule_callback"
    endpoint = "https://api.ringr.callback/v1/callback"

    def decide(self, parsed: Mapping[str, object]) -> Decision:
        phone = parsed.get("phone")
        if not isinstance(phone, str):
            return Decision.wait("Falta el teléfono")
        return Decision.act({"phone": phone})
```

Una integración distinta es otra implementación de `HttpClient`, por ejemplo una que envíe de verdad.

## Límites deliberados

- Las reglas no entienden meses con nombre («el 4 de octubre»), importes sin moneda ni separadores de miles: en esos casos el agente pregunta en vez de adivinar.
- La conversación vive en la instancia del agente; no hay persistencia entre procesos.
- El modelo de conversación no conoce el resultado del envío, así que tras un fallo responde que el trámite está «en curso» mientras el agente lo reintenta.

## Tests

```bash
uv run pytest
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy
```

Cubren la regla de fechas (cambio de mes y de año, meses cortos, bisiestos), la lectura de datos, la validación, las requests exactas, los duplicados, los fallos con reintento y la demo. El CI los ejecuta en cada PR.

## Proceso

Lo he desarrollado dirigiendo agentes de IA. Claude Code implementó cada bloque en una PR, con tests primero. Codex (OpenAI) revisó las PRs de la base, el motor y los agentes, y sus hallazgos se corrigieron antes de fusionarlas: inyección de cabeceras, importes negativos, fechas repetidas en un mensaje, solicitudes negadas… Todo está en el historial de PRs.

La PR del README y la demo tuvo una primera revisión, pero su corrección y las PRs siguientes se fusionaron sin revisión de Codex, porque el plan de ChatGPT con el que se ejecutaba agotó su límite de uso. Esos cambios se verificaron con el CI, los tests y la demo. Las decisiones de negocio de la tabla anterior las he tomado yo, igual que el arbitraje cuando Codex rechazaba dos veces una PR.
