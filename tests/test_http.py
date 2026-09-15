"""Tests de la construcción de requests y del cliente HTTP simulado."""

import json

import pytest

from ringr_agents.http import SimulatedHttpClient, build_post


def test_build_post_incluye_bearer_cabeceras_con_los_datos_y_cuerpo_json() -> None:
    request = build_post(
        "https://api.ringr.debt/v1/commitment",
        "ringr_test_token_9f3a2c1d",
        {"commitment_date": "2026-10-04", "committed_amount": 200.0},
    )

    assert request.method == "POST"
    assert request.url == "https://api.ringr.debt/v1/commitment"
    assert dict(request.headers) == {
        "Authorization": "Bearer ringr_test_token_9f3a2c1d",
        "Content-Type": "application/json",
        "commitment_date": "2026-10-04",
        "committed_amount": "200.0",
    }
    assert json.loads(request.body) == {"commitment_date": "2026-10-04", "committed_amount": 200.0}


def test_los_saltos_de_linea_no_llegan_a_las_cabeceras() -> None:
    request = build_post("https://x.test", "t", {"request": "cambiar\r\ndirección"})
    assert request.headers["request"] == "cambiar dirección"
    assert json.loads(request.body) == {"request": "cambiar\r\ndirección"}


def test_el_cliente_simulado_registra_y_responde_200_salvo_estados_programados() -> None:
    client = SimulatedHttpClient(statuses=[500])
    request = build_post("https://x.test", "t", {"a": "b"})

    assert client.send(request).status == 500
    assert client.send(request).status == 200
    assert client.requests == [request, request]


@pytest.mark.parametrize("name", ["campo\r\nX-Inyectada", "con espacio", "", "dos:puntos"])
def test_rechaza_nombres_de_campo_que_no_son_nombres_de_cabecera_validos(name: str) -> None:
    with pytest.raises(ValueError, match="cabecera"):
        build_post("https://x.test", "t", {name: "valor"})
