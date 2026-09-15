"""Tests del agente de atención al cliente: detección de solicitudes y registro."""

import pytest

from ringr_agents.agent import ActionStatus
from ringr_agents.assistance import AssistanceParser, build_assistance_agent, decide_request
from ringr_agents.conversation import Conversation, Role
from ringr_agents.http import SimulatedHttpClient


def parse(*user_texts: str) -> dict[str, object]:
    conversation = Conversation()
    for text in user_texts:
        conversation = conversation.add(Role.USER, text).add(Role.AGENT, "respuesta")
    return AssistanceParser().parse_data(conversation)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Quiero cambiar mi dirección postal", "Quiero cambiar mi dirección postal"),
        ("  necesito   dar de baja mi línea ", "necesito dar de baja mi línea"),
        ("Me gustaría hablar con un comercial", "Me gustaría hablar con un comercial"),
        ("¿Cuál es vuestro horario?", None),
        ("Quiero saber vuestro horario", None),
        ("No quiero cambiar mi dirección", None),
        ("Ya no necesito nada, gracias", None),
        ("No me gustaría darme de baja", None),
        ("Tampoco quiero hablar con un comercial", None),
        ("No, quiero cambiar mi dirección", "No, quiero cambiar mi dirección"),
        (
            "No quiero cambiar la dirección, quiero darme de baja",
            "No quiero cambiar la dirección, quiero darme de baja",
        ),
    ],
)
def test_una_solicitud_es_un_mensaje_que_pide_algo(text: str, expected: str | None) -> None:
    assert parse(text) == {"request": expected}


def test_cuenta_la_ultima_solicitud_de_la_conversacion() -> None:
    assert parse("Quiero cambiar mi dirección", "Gracias") == {
        "request": "Quiero cambiar mi dirección"
    }
    assert parse("Quiero A", "¿Y el horario?", "Necesito B") == {"request": "Necesito B"}


@pytest.mark.parametrize("parsed", [{"request": None}, {"request": "   "}, {"request": 42}, {}])
def test_sin_solicitud_no_hay_accion(parsed: dict[str, object]) -> None:
    decision = decide_request(parsed)
    assert decision.payload is None
    assert decision.reason == "No hay ninguna solicitud que registrar"


def test_conversacion_completa_registra_la_solicitud_una_vez() -> None:
    client = SimulatedHttpClient()
    agent = build_assistance_agent(client)

    doubt = agent.handle_turn("¿Cuál es vuestro horario?")
    request = agent.handle_turn("Quiero cambiar mi dirección postal")
    another = agent.handle_turn("Y también quiero dar de baja mi línea")

    assert doubt.status is ActionStatus.NOT_NEEDED
    assert request.status is ActionStatus.EXECUTED
    assert request.request is not None
    assert request.request.url == "https://api.ringr.assistance/v1/request"
    assert request.request.headers["request"] == "Quiero cambiar mi dirección postal"
    assert request.answer == "Registro tu solicitud para que la gestione un compañero."
    assert another.status is ActionStatus.DUPLICATE
    assert another.answer == "Tu solicitud ya está en curso; un compañero te contactará."
    assert len(client.requests) == 1


def test_si_el_registro_falla_el_siguiente_mensaje_lo_reintenta() -> None:
    client = SimulatedHttpClient(statuses=[500])
    agent = build_assistance_agent(client)

    failed = agent.handle_turn("Quiero cambiar mi dirección postal")
    retried = agent.handle_turn("¿Ha quedado registrado?")

    assert failed.status is ActionStatus.FAILED
    assert retried.status is ActionStatus.EXECUTED
    assert retried.answer == "Tu solicitud ya está en curso; un compañero te contactará."
    assert len(client.requests) == 2


def test_rechazar_algo_no_crea_ninguna_request() -> None:
    client = SimulatedHttpClient()
    agent = build_assistance_agent(client)

    result = agent.handle_turn("No quiero cambiar mi dirección")

    assert result.status is ActionStatus.NOT_NEEDED
    assert client.requests == []


def test_retirar_una_solicitud_fallida_evita_el_reintento() -> None:
    client = SimulatedHttpClient(statuses=[500])
    agent = build_assistance_agent(client)

    failed = agent.handle_turn("Quiero cambiar mi dirección postal")
    withdrawn = agent.handle_turn("No, ya no quiero cambiarla")

    assert failed.status is ActionStatus.FAILED
    assert withdrawn.status is ActionStatus.NOT_NEEDED
    assert len(client.requests) == 1
