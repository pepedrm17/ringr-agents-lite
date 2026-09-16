"""Tests del motor común de los agentes: secuencia del turno, duplicados y reintentos."""

from ringr_agents.agent import ActionStatus
from ringr_agents.conversation import Role
from ringr_agents.http import SimulatedHttpClient
from tests.fakes import PingAgent, RecordingModels


def make_agent(
    models: RecordingModels, client: SimulatedHttpClient | None = None
) -> tuple[PingAgent, SimulatedHttpClient]:
    client = client or SimulatedHttpClient()
    return PingAgent(models, models, client, token="token"), client


def test_responde_antes_de_parsear_y_el_parser_ve_la_respuesta() -> None:
    """El turno responde primero y el parser recibe la conversación con esa respuesta.

    Comprueba el orden que fija el enunciado: answer_user y después parse_data.
    """
    models = RecordingModels()
    agent, _ = make_agent(models)

    result = agent.handle_turn("hola")

    assert result.answer == "respuesta"
    assert [(m.role, m.text) for m in models.answered[0].messages] == [(Role.USER, "hola")]
    assert [(m.role, m.text) for m in models.parsed_from[0].messages] == [
        (Role.USER, "hola"),
        (Role.AGENT, "respuesta"),
    ]


def test_sin_datos_suficientes_no_hay_accion_y_se_explica_por_que() -> None:
    """Sin datos suficientes no se ejecuta ninguna acción y el resultado dice por qué."""
    agent, client = make_agent(RecordingModels())

    result = agent.handle_turn("hola")

    assert result.status is ActionStatus.NOT_NEEDED
    assert result.reason == "Falta el destino del ping"
    assert client.requests == []


def test_con_datos_suficientes_construye_y_envia_la_request() -> None:
    """Con datos suficientes construye la request con su URL y su Bearer token, y la entrega al
    cliente.
    """
    agent, client = make_agent(RecordingModels(parsed={"target": "servidor"}))

    result = agent.handle_turn("haz ping")

    assert result.status is ActionStatus.EXECUTED
    assert result.request is not None
    assert result.request.url == "https://api.example.test/v1/ping"
    assert result.request.headers["Authorization"] == "Bearer token"
    assert client.requests == [result.request]


def test_la_accion_se_registra_una_sola_vez_por_conversacion_aunque_cambien_los_datos() -> None:
    """La acción se registra una sola vez por conversación, aunque después cambien los datos."""
    models = RecordingModels(parsed={"target": "servidor-1"})
    agent, client = make_agent(models)
    agent.handle_turn("haz ping al 1")

    models.parsed = {"target": "servidor-2"}
    result = agent.handle_turn("mejor al 2")

    assert result.status is ActionStatus.DUPLICATE
    assert result.request is None
    assert len(client.requests) == 1


def test_un_fallo_no_cuenta_como_enviado_y_el_siguiente_turno_reintenta() -> None:
    """Una respuesta distinta de 200 no cuenta como enviada y el siguiente turno la reintenta."""
    agent, client = make_agent(
        RecordingModels(parsed={"target": "servidor"}), SimulatedHttpClient(statuses=[503])
    )

    failed = agent.handle_turn("haz ping")
    retried = agent.handle_turn("¿ya está?")

    assert failed.status is ActionStatus.FAILED
    assert "503" in failed.reason
    assert retried.status is ActionStatus.EXECUTED
    assert len(client.requests) == 2


def test_cada_agente_es_una_conversacion_independiente() -> None:
    """Cada instancia de agente es una conversación independiente, con su propio registro."""
    first, first_client = make_agent(RecordingModels(parsed={"target": "servidor"}))
    second, second_client = make_agent(RecordingModels(parsed={"target": "servidor"}))

    first.handle_turn("haz ping")
    second.handle_turn("haz ping")

    assert len(first_client.requests) == len(second_client.requests) == 1
