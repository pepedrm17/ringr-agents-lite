# Cómo probarlo

Dos formas: sin instalar nada, en el navegador, o en local con `uv`.

## Sin instalar nada

La [demo web](https://pepedrm17.github.io/ringr-agents-lite/) ejecuta **este mismo código** en el navegador, sin servidor: el repositorio va embebido en la página y corre sobre Python compilado a WebAssembly. Tiene tres partes:

- **Conversaciones guiadas**: casos preparados, turno a turno, con lo que se espera en cada uno.
- **Chat libre**: escribe tú los mensajes y mira cómo reacciona cada agente.
- **Tests**: la suite completa, ejecutada en el momento y con el resultado de cada caso.

## En local

Requisitos: [`uv`](https://docs.astral.sh/uv/) y Python 3.12+ (`uv` lo instala si hace falta).

```bash
git clone https://github.com/pepedrm17/ringr-agents-lite.git
cd ringr-agents-lite
uv sync
```

**Los tests**:

```bash
uv run pytest
```

**Las dos conversaciones de ejemplo**, turno a turno:

```bash
uv run python -m ringr_agents.demo
```

**Un chat con el agente que quieras** (escribe `salir` para terminar):

```bash
uv run python -m ringr_agents.demo chat cobros     # prueba: «el 4 pago 200 euros»
uv run python -m ringr_agents.demo chat atencion   # prueba: «Quiero cambiar mi dirección»
```

**Fijar la fecha de hoy** para reproducir la regla de fechas cualquier día del año:

```bash
uv run python -m ringr_agents.demo --hoy 2026-09-15
```

## Qué mirar en cada turno

La demo imprime las cuatro cosas que hace el agente en un turno:

```
Usuario: Pagaré 200 euros
Agente:  Falta la fecha. ¿Qué día podrás pagar?          ← la respuesta al usuario
Datos:   commitment_date=None, committed_amount=200.0    ← lo que ha extraído
Acción:  sin_accion (Falta la fecha)                     ← la decisión, con su motivo

Usuario: el 4
Agente:  Perfecto, anoto el pago de 200 € para el 04/10/2026.
Datos:   commitment_date='2026-10-04', committed_amount=200.0
Acción:  ejecutada
  POST https://api.ringr.debt/v1/commitment              ← la request completa
  Authorization: Bearer ringr_test_token_9f3a2c1d
  Content-Type: application/json
  commitment_date: 2026-10-04
  committed_amount: 200.0
  {"commitment_date": "2026-10-04", "committed_amount": 200.0}
```

Cuando faltan datos, la acción es `sin_accion` y el agente pregunta por lo que falta. Cuando están todos, la acción es `ejecutada` y se ve la request entera: URL, cabeceras y cuerpo. **Ninguna request sale del proceso**: el cliente HTTP es simulado.

Los otros dos estados posibles son `duplicada`, cuando esa acción ya se registró con esos mismos datos, y `fallida`, cuando el endpoint simulado responde algo distinto de `200` y el siguiente turno lo reintenta.

## Cosas que merece la pena probar en el chat

| Escribe | Qué deberías ver |
|---------|------------------|
| `el 31` (en un mes de 30 días) | La fecha se ajusta al último día del mes |
| `el 4, mejor el 5` | Vale el último dato: día 5 |
| `el 4 de diciembre pago 50 euros` | Entiende el mes por su nombre |
| `el 4 pago 200` | La moneda por defecto es el euro |
| `el 4 pago 5.570` / `el 4 pago 55.70` | Tres cifras tras el punto son millares; dos, céntimos |
| `4 de enero` (dicho en septiembre) | Enero ya pasó: lo lleva al año siguiente |
| `pagaré -20 euros` | No se registra: el importe debe ser mayor que cero |
| `2020-01-01 pago 100 euros` | No se registra: la fecha ya ha pasado |
| Repetir el mismo compromiso | La acción sale como `duplicada` |
| Cambiar el importe después de registrar | Se registra otra vez, con el dato nuevo |
| `No quiero cambiar mi dirección` (atención) | No se registra nada: es un rechazo, no una solicitud |
| `Quiero saber vuestro horario` (atención) | Se registra: pedir información también es una solicitud |

Las reglas completas y el porqué de cada una están en el [README](README.md).

## Verificar la calidad del código

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy
```

Es lo mismo que ejecuta el CI en cada PR y en cada push a `main`.
