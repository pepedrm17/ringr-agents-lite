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
    ],
)
def test_una_solicitud_es_un_mensaje_que_pide_algo(text: str, expected: str | None) -> None:
    assert parse(text) == {"request": expected}


def test_solo_cuenta_el_ultimo_mensaje_del_usuario() -> None:
    assert parse("Quiero cambiar mi dirección", "Gracias") == {"request": None}


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
    assert (
        another.answer
        == "Ya he registrado una solicitud en esta conversación; un compañero te contactará."
    )
    assert len(client.requests) == 1
