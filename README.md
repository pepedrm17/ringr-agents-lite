# Agentes conversacionales de Ringr (versión lite)

Muy buenas! 

En este proyecto vais a ver la solución que he hecho para la prueba técnica que recibí el lunes. En este archivo vais a ver las decisiones que he tomado para llevar a cabo lo que pedíais en el pdf y un poco de la estructura del proyecto (que eso lo explica abajo Claude).

Además, ya que era poco visible la solución, me he tomado la libertad de añadir un apartado /web con una pequeña mini demo, hay muchas cosas que se salen del scope de la demo porque no he implementado agentes de IA, simplemente decisiones deterministas y expresiones regulares. Pero por hacernos una idea más visual de lo que se ha hecho aquí. 

Para verlo funcionar: **[cómo probarlo](PROBARLO.md)**, en el navegador o en local.

Sin más dilación, os sigo contando.

## Decisiones tomadas

El enunciado fija el esqueleto y deja abierto el comportamiento. Estas son las decisiones que he tomado.

| Tema | Decisión |
|------|----------|
| **Sin LLM** | Los datos se leen con expresiones regulares y funciones deterministas. El enunciado permite simular los modelos; con reglas, el comportamiento es predecible y cada caso se puede probar. |
| **Duplicados** | No se repite una acción **con los mismos datos** en la misma conversación. Si el usuario cambia de opinión, se registra otra vez con los datos actualizados. |
| **Fechas** | «el 4» o «el día 4» es **este mes si ese día no ha pasado** (hoy cuenta), y si ya pasó, el mes siguiente. «El 4 de octubre» es **este año si esa fecha no ha pasado**, y si ya pasó, el siguiente; con año explícito («de 2027») manda el año dicho. Si el mes no tiene ese día («el 31» en septiembre), el **último día del mes**. También vale una fecha completa `2026-10-04`. |
| **Fecha pasada** | Una fecha completa anterior a hoy **no se registra**: el agente pide otra. |
| **Importe** | Un número **mayor que cero**. La moneda por defecto es el euro, así que `200 euros`, `150,50 €` y `200` a secas son lo mismo; el número de una fecha («el 4») no es un importe. Un separador seguido de **tres cifras son millares** (`5.570` son 5570 €) y de **una o dos, céntimos** (`55,70`). |
| **Solicitudes** | Un mensaje pide algo si usa «quiero», «quisiera», «necesito», «me gustaría» o «solicito». Si viniera precedido por un 'no' «No quiero…» se rechaza y anula la solicitud anterior. |
| **Datos repetidos** | Si el usuario dice algo varias veces, **vale lo último**, incluso dentro del mismo mensaje («el 4, o no, mejor el 5»). |
| **Fallos HTTP** | El enunciado fija que el éxito es `200 OK`. **Cualquier otro código no cuenta como enviado** y el siguiente turno lo reintenta. |

## Estructura y diseño

### El turno, en un solo sitio

`Agent` es una clase abstracta que fija el orden del turno (patrón *Template Method*). Cada agente concreto solo aporta su `action`, su `endpoint` y `decide`, que es su regla de negocio:

```
Agent.handle_turn(mensaje)
  1. answer_user(conversación)   → respuesta para el usuario
  2. parse_data(conversación)    → datos estructurados
  3. decide(datos)               → actuar con estos datos, o esperar y por qué   ← cada agente
  4. si actúa y no lo hizo ya    → build_post + envío simulado
```

El turno devuelve un `TurnResult` con la respuesta, los datos, el estado de la acción y, si la hubo, la request y la respuesta. El estado es uno de cuatro: `sin_accion`, `ejecutada`, `duplicada` o `fallida`.

| Paso | Quién lo hace | Qué garantiza |
|------|---------------|---------------|
| Responder | `ConversationModel.answer_user` | El usuario siempre recibe respuesta, se actúe o no |
| Extraer | `ParserModel.parse_data` | Los datos salen de **toda** la conversación, no solo del último mensaje |
| Validar y decidir | `decide` de cada agente | Sin datos válidos no se construye ninguna request |
| Ejecutar | `build_post` + `HttpClient` | La request se construye completa y no sale del proceso |

### Del enunciado al código

| El enunciado pide | Dónde está |
|-------------------|------------|
| `handle_turn`: responder, extraer, validar y decidir, ejecutar | `agent.py` (`Agent.handle_turn`) |
| `ConversationModel.answer_user` y `ParserModel.parse_data`, simulados | `conversation.py` (contratos); `debt.py` y `assistance.py` (implementaciones) |
| `DebtAgent`: con `commitment_date` y `committed_amount`, POST a `https://api.ringr.debt/v1/commitment` | `debt.py` |
| `AssistanceAgent`: con `request`, POST a `https://api.ringr.assistance/v1/request` | `assistance.py` |
| Request construida sin enviarse, con `Bearer ringr_test_token_9f3a2c1d` y los datos como cabeceras | `http.py` (`build_post`, `SimulatedHttpClient`) |
| No enviar duplicados durante la conversación | `agent.py` (`Agent.handle_turn`) |

### Ficheros

| Fichero | Qué contiene |
|---------|--------------|
| `agent.py` | `Agent` (el turno, los duplicados y los reintentos), `Decision`, `TurnResult`, `ActionStatus` |
| `conversation.py` | `Conversation` inmutable y los contratos `ConversationModel` y `ParserModel` |
| `http.py` | `build_post` (la request) y `SimulatedHttpClient` (el envío simulado) |
| `dates.py` | Las reglas de «el día N» y «el N de <mes>» |
| `debt.py` | Agente de cobros: lectura de fecha e importe, validación y respuestas |
| `assistance.py` | Agente de atención: detección de solicitudes y negaciones, y respuestas |
| `demo.py` | Demo por consola, con guion y con chat |
| `tests/` | 117 casos de prueba (ver [Tests](#tests)) |
| `web/` | Demo web: página generada con el código del repositorio y publicada en GitHub Pages |

### Los contratos son `Protocol`, no herencia

`ConversationModel` y `ParserModel` son `typing.Protocol`: definen la firma (`answer_user`, `parse_data`) sin obligar a heredar. Cada agente trae sus propias implementaciones, que se inyectan por constructor:

```python
agent = DebtAgent(DebtConversationModel(parser, today), parser, SimulatedHttpClient(), today=today)
```

Así, los tests sustituyen cualquier pieza por un doble sin tocar el motor, y la fecha de hoy se inyecta como función (`today`), que es lo que permite probar la regla de fechas en cualquier día del calendario. Las funciones `build_debt_agent` y `build_assistance_agent` montan la combinación por defecto en una línea.

La única herencia del proyecto es `DebtAgent(Agent)` y `AssistanceAgent(Agent)`, y existe para compartir el turno, no para reutilizar reglas: **cada agente tiene su parser y su modelo de conversación propios**, porque sus reglas son código (fechas e importes en cobros; solicitudes y negaciones en atención), no un prompt configurable. Un objeto genérico con una tabla de reglas era posible, pero para dos casos añade una capa de indirección y hace que las reglas se lean peor.

### La integración HTTP

`build_post` construye el POST completo y `SimulatedHttpClient` lo guarda sin abrir red:

- **URL**: el `endpoint` del agente.
- **Cabeceras**: `Authorization: Bearer <token>`, `Content-Type: application/json` y **un campo por cada dato** del payload, con el mismo nombre.
- **Cuerpo**: el payload en JSON.

Como los datos viajan también en cabeceras, `build_post` valida antes de construir nada: rechaza nombres de campo que no sean un *token* HTTP válido (RFC 9110) o que pisen `Authorization` o `Content-Type`, y aplana los espacios de los valores para que un salto de línea del usuario no pueda partir una cabecera.

Cambiar el envío simulado por uno real es escribir otra implementación de `HttpClient` e inyectarla; el motor no cambia.

### Duplicados y reintentos

Al decidir actuar, el agente calcula la huella del payload —su JSON con las claves ordenadas— y la busca entre las de esta conversación. Si ya está, el turno acaba en `duplicada` y no se envía nada. **La huella se guarda solo cuando la respuesta es `200`**, y de ahí salen las dos garantías:

- Un fallo (cualquier código distinto de `200`) deja el turno en `fallida` y, como no se guardó nada, el siguiente turno lo vuelve a intentar.
- Un cambio de opinión produce un payload distinto, con otra huella, así que sí se envía con los datos nuevos.

### Añadir un agente

Un agente nuevo es su regla de decisión y su endpoint:

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

El turno, los duplicados, los reintentos y la construcción de la request los hereda de `Agent`.

## Límites deliberados

En todos ellos el agente **pregunta en vez de adivinar**, que es la conducta segura cuando lo que está en juego es un POST.

- Las fechas relativas no se interpretan: «el próximo martes», «mañana» o «a final de mes» no se leen, y el agente pregunta qué día. (el martes que viene puede ser el martes que entra o el siguiente del que entra según cada uno)
- La conversación vive en la instancia del agente: no hay persistencia entre procesos.
- El modelo de conversación no sabe si el envío funcionó, así que tras un fallo responde como si el trámite estuviera hecho mientras el agente lo reintenta por detrás.

## Tests

```bash
uv run pytest
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy
```

**117 casos** repartidos en 41 funciones parametrizadas:

| Fichero | Casos | Qué cubre |
|---------|-------|-----------|
| `test_debt.py` | 54 | Lectura de fecha e importe, validación, conversación completa y registro |
| `test_assistance.py` | 21 | Detección de solicitudes, preguntas sueltas, negaciones y reintento tras un fallo |
| `test_dates.py` | 20 | «El día N» y «el N de <mes>»: cambio de mes y de año, meses cortos, bisiestos |
| `test_http.py` | 11 | Request exacta, nombres de cabecera inválidos o reservados, estados programados |
| `test_agent.py` | 8 | Secuencia del turno, duplicados, reintentos y estados |
| `test_demo.py` | 3 | Demo por consola, en guion y en chat |

Cada test lleva una frase que describe su caso, y esas frases son las que aparecen en la demo web al ejecutar la suite. El CI ejecuta lint, formato, tipos y tests en cada PR y en cada push a `main`.

## Proceso

Lo he desarrollado dirigiendo agentes de IA. Claude Code implementó cada bloque en una PR, con tests primero. Codex (OpenAI) revisó las PRs de la base, el motor y los agentes, y sus hallazgos se corrigieron antes de fusionarlas. Todo está en el historial de PRs.

Pensé en usar SDD por tener trazabilidad sobre las decisiones que se iban tomando, pero al ser el proyecto del tamaño que es, vi lo que estaba haciendo y me parecía matar moscas a cañonazos. Terminé haciendo un repositorio nuevo sin tanto lío y de ahí el nombre 'lite' en este proyecto.

Las decisiones de negocio de la tabla de arriba las he tomado yo, igual que el arbitraje cuando Codex y Claude no se ponían de acuerdo en una PR. Lo tengo montado de tal forma que claude corrige PR según lo que diga Codex hasta 2 veces. Y si no se ponen de acuerdo me llega un correo con la discrepancia entre uno y otro. (para poder usar la suscripción de codex y no tener que tirar de tokens lo hice solo en local con el CLI de codex, de ahí que no se vea nada en el repo de gh).