"""Tests de la demo por consola."""

import io

import pytest

from ringr_agents.demo import main


def run(argv: list[str], typed: str = "") -> str:
    out = io.StringIO()
    assert main(argv, stdin=io.StringIO(typed), stdout=out) == 0
    return out.getvalue()


def test_el_guion_muestra_las_dos_conversaciones_con_sus_requests() -> None:
    output = run(["guion", "--hoy", "2026-09-15"])

    assert "POST https://api.ringr.debt/v1/commitment" in output
    assert "Authorization: Bearer ringr_test_token_9f3a2c1d" in output
    assert "commitment_date: 2026-10-04" in output
    assert "Acción:  duplicada" in output
    assert "POST https://api.ringr.assistance/v1/request" in output
    assert "request: Quiero cambiar mi dirección postal" in output


def test_el_chat_usa_lo_que_escribe_el_usuario_hasta_salir() -> None:
    output = run(["chat", "cobros", "--hoy", "2026-09-15"], "el 4 pago 200 euros\nsalir\n")

    assert "Perfecto, anoto el pago de 200 € para el 04/10/2026." in output
    assert "Acción:  ejecutada" in output


def test_una_fecha_de_hoy_mal_escrita_es_un_error_de_uso() -> None:
    with pytest.raises(SystemExit) as error:
        main(["guion", "--hoy", "15/09/2026"], stdout=io.StringIO())
    assert error.value.code == 2
