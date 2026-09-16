"""Tests del agente de cobros: lectura de fecha e importe, validación y registro."""

from datetime import date

import pytest

from ringr_agents.agent import ActionStatus
from ringr_agents.conversation import Conversation, Role
from ringr_agents.debt import DebtParser, build_debt_agent, decide_commitment
from ringr_agents.http import SimulatedHttpClient

TODAY = date(2026, 9, 15)


def parse(*user_texts: str) -> dict[str, object]:
    conversation = Conversation()
    for text in user_texts:
        conversation = conversation.add(Role.USER, text).add(Role.AGENT, "respuesta")
    return DebtParser(lambda: TODAY).parse_data(conversation)


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["el 4 pago 200 euros"], {"commitment_date": "2026-10-04", "committed_amount": 200.0}),
        (["Pagaré el día 20"], {"commitment_date": "2026-09-20", "committed_amount": None}),
        (["Puedo pagar 150,50 €"], {"commitment_date": None, "committed_amount": 150.5}),
        (
            ["El 2026-12-01 pago 90 euros"],
            {"commitment_date": "2026-12-01", "committed_amount": 90.0},
        ),
        (
            ["Pagaré 200 euros", "el 31"],
            {"commitment_date": "2026-09-30", "committed_amount": 200.0},
        ),
        (
            ["Pagaré 200 euros", "mejor 250 euros"],
            {"commitment_date": None, "committed_amount": 250.0},
        ),
        (
            ["pagaré el 4, mejor el 5 y 200 euros"],
            {"commitment_date": "2026-10-05", "committed_amount": 200.0},
        ),
        (
            ["el 2026-10-01 o mejor el 2026-10-02, 80 €"],
            {"commitment_date": "2026-10-02", "committed_amount": 80.0},
        ),
        (
            ["el 2026-10-01, no, mejor el 20"],
            {"commitment_date": "2026-09-20", "committed_amount": None},
        ),
        (["pagaré -20 euros"], {"commitment_date": None, "committed_amount": -20.0}),
    ],
)
def test_el_parser_lee_fecha_e_importe_de_lo_que_dice_el_usuario(
    texts: list[str], expected: dict[str, object]
) -> None:
    """Lee importe y fecha del texto del usuario, incluidas «el día N», la fecha completa y el
    último dato repetido.
    """
    assert parse(*texts) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("el 4 de octubre", {"commitment_date": None, "committed_amount": None}),
        ("pago 200", {"commitment_date": None, "committed_amount": None}),
        ("pagaré 1.000 euros", {"commitment_date": None, "committed_amount": None}),
        ("el 45 pago 20 euros", {"commitment_date": None, "committed_amount": 20.0}),
    ],
)
def test_lo_que_no_encaja_en_las_reglas_no_se_inventa(
    text: str, expected: dict[str, object]
) -> None:
    """Lo que no encaja en las reglas (meses con nombre, importes sin moneda, días imposibles) se
    deja sin leer.
    """
    # Meses con nombre, importes sin moneda o con separador de miles y días imposibles
    # quedan sin leer: el agente pregunta en vez de adivinar.
    assert parse(text) == expected


@pytest.mark.parametrize(
    ("parsed", "reason"),
    [
        ({"commitment_date": None, "committed_amount": None}, "Faltan la fecha y el importe"),
        ({"commitment_date": "2026-10-04", "committed_amount": None}, "Falta el importe"),
        ({"commitment_date": None, "committed_amount": 200.0}, "Falta la fecha"),
        (
            {"commitment_date": "2026-09-14", "committed_amount": 200.0},
            "La fecha 2026-09-14 ya ha pasado",
        ),
        (
            {"commitment_date": "2026-02-30", "committed_amount": 200.0},
            "La fecha 2026-02-30 no es válida",
        ),
        (
            {"commitment_date": "04/10/2026", "committed_amount": 200.0},
            "La fecha 04/10/2026 no es válida",
        ),
        (
            {"commitment_date": "2026-10-04", "committed_amount": 0},
            "El importe debe ser mayor que cero",
        ),
        (
            {"commitment_date": "2026-10-04", "committed_amount": "200"},
            "El importe debe ser mayor que cero",
        ),
    ],
)
def test_no_se_registra_con_datos_incompletos_o_no_validos(
    parsed: dict[str, object], reason: str
) -> None:
    """No se registra con datos incompletos o no válidos, y el motivo nombra el campo."""
    decision = decide_commitment(parsed, TODAY)
    assert decision.payload is None
    assert decision.reason == reason


@pytest.mark.parametrize(
    ("parsed", "reason"),
    [
        (
            {"commitment_date": None, "committed_amount": -20.0},
            "Falta la fecha. El importe debe ser mayor que cero",
        ),
        (
            {"commitment_date": "2026-09-14", "committed_amount": -20.0},
            "La fecha 2026-09-14 ya ha pasado. El importe debe ser mayor que cero",
        ),
        (
            {"commitment_date": "2026-02-30", "committed_amount": None},
            "La fecha 2026-02-30 no es válida. Falta el importe",
        ),
    ],
)
def test_se_informa_de_los_problemas_de_fecha_e_importe_a_la_vez(
    parsed: dict[str, object], reason: str
) -> None:
    """Cuando fallan los dos campos, el motivo reúne el problema de la fecha y el del importe."""
    assert decide_commitment(parsed, TODAY).reason == reason


def test_hoy_es_una_fecha_valida() -> None:
    """Un pago comprometido para hoy es válido y se registra."""
    decision = decide_commitment({"commitment_date": "2026-09-15", "committed_amount": 50}, TODAY)
    assert decision.payload == {"commitment_date": "2026-09-15", "committed_amount": 50.0}


def test_conversacion_completa_registra_una_vez_con_la_request_del_enunciado() -> None:
    """Conversación completa: registra una vez y la request lleva URL, Bearer token y los datos
    como cabeceras.
    """
    client = SimulatedHttpClient()
    agent = build_debt_agent(client, today=lambda: TODAY)

    first = agent.handle_turn("Hola, tengo una deuda pendiente")
    second = agent.handle_turn("Pagaré 200 euros")
    third = agent.handle_turn("el 4")
    fourth = agent.handle_turn("mejor 250 euros")

    assert [first.status, second.status] == [ActionStatus.NOT_NEEDED, ActionStatus.NOT_NEEDED]
    assert second.reason == "Falta la fecha"
    assert third.status is ActionStatus.EXECUTED
    assert third.request is not None
    assert third.request.url == "https://api.ringr.debt/v1/commitment"
    assert third.request.headers["Authorization"] == "Bearer ringr_test_token_9f3a2c1d"
    assert third.request.headers["commitment_date"] == "2026-10-04"
    assert third.request.headers["committed_amount"] == "200.0"
    assert third.answer == "Perfecto, anoto el pago de 200 € para el 04/10/2026."
    assert fourth.status is ActionStatus.DUPLICATE
    assert len(client.requests) == 1


def test_una_fecha_completa_ya_pasada_no_se_registra() -> None:
    """Una fecha completa anterior a hoy no se registra."""
    client = SimulatedHttpClient()
    agent = build_debt_agent(client, today=lambda: TODAY)

    result = agent.handle_turn("Pagué 100 euros el 2026-01-10")

    assert result.status is ActionStatus.NOT_NEEDED
    assert result.reason == "La fecha 2026-01-10 ya ha pasado"
    assert client.requests == []


def test_si_el_endpoint_falla_el_siguiente_turno_reintenta() -> None:
    """Si el endpoint falla, el siguiente turno reintenta el mismo compromiso."""
    client = SimulatedHttpClient(statuses=[500])
    agent = build_debt_agent(client, today=lambda: TODAY)

    failed = agent.handle_turn("el 4 pago 200 euros")
    retried = agent.handle_turn("¿Ha quedado registrado?")

    assert failed.status is ActionStatus.FAILED
    assert retried.status is ActionStatus.EXECUTED
    assert len(client.requests) == 2


def test_un_importe_negativo_no_se_registra() -> None:
    """Un importe negativo («-20 euros») se lee con su signo y no se registra."""
    client = SimulatedHttpClient()
    agent = build_debt_agent(client, today=lambda: TODAY)

    result = agent.handle_turn("el 4 pagaré -20 euros")

    assert result.status is ActionStatus.NOT_NEEDED
    assert result.reason == "El importe debe ser mayor que cero"
    assert client.requests == []


@pytest.mark.parametrize(
    ("message", "question"),
    [
        ("Hola", "¿Qué día y cuánto podrás pagar?"),
        ("Pagaré 200 euros", "¿Qué día podrás pagar?"),
        ("el 4", "¿Cuánto podrás pagar?"),
        ("el 2026-01-10 pago 90 euros", "¿Qué otra fecha te viene bien?"),
        ("el 4 pagaré -5 euros", "¿Qué importe podrás pagar?"),
        ("Pagaré -20 euros", "¿Qué día y cuánto podrás pagar?"),
        ("el 2026-01-10 pagaré -20 euros", "¿Qué día y cuánto podrás pagar?"),
    ],
)
def test_el_agente_pregunta_solo_por_lo_que_falta(message: str, question: str) -> None:
    """El agente pregunta solo por lo que falta o no es válido: el día, el importe o ambos."""
    answer = build_debt_agent(today=lambda: TODAY).handle_turn(message).answer
    assert answer.endswith(question)
