"""Tests de las reglas que convierten «el día N» y «el N de <mes>» en una fecha concreta."""

from datetime import date

import pytest

from ringr_agents.dates import date_in_month, resolve_day_of_month, resolve_month_day


@pytest.mark.parametrize(
    ("today", "day", "expected"),
    [
        (date(2026, 9, 2), 4, date(2026, 9, 4)),  # el día aún no ha llegado: este mes
        (date(2026, 9, 4), 4, date(2026, 9, 4)),  # es hoy: este mes
        (date(2026, 9, 15), 4, date(2026, 10, 4)),  # ya ha pasado: el mes siguiente
        (date(2026, 12, 20), 4, date(2027, 1, 4)),  # diciembre pasa a enero del año siguiente
    ],
)
def test_usa_este_mes_si_el_dia_no_ha_pasado_y_si_no_el_siguiente(
    today: date, day: int, expected: date
) -> None:
    """«El día N» es este mes si ese día no ha pasado (hoy incluido) y, si ya pasó, el mes
    siguiente.
    """
    assert resolve_day_of_month(day, today) == expected


@pytest.mark.parametrize(
    ("today", "day", "expected"),
    [
        (date(2026, 9, 15), 31, date(2026, 9, 30)),  # septiembre tiene 30 días
        (date(2026, 1, 31), 30, date(2026, 2, 28)),  # febrero de 2026 tiene 28
        (date(2028, 1, 31), 30, date(2028, 2, 29)),  # 2028 es bisiesto
    ],
)
def test_si_el_dia_no_existe_en_ese_mes_usa_el_ultimo_dia(
    today: date, day: int, expected: date
) -> None:
    """Si ese mes no tiene ese día (el 31 en septiembre, el 30 en febrero), usa el último día del
    mes.
    """
    assert resolve_day_of_month(day, today) == expected


@pytest.mark.parametrize("day", [0, 32, -1])
def test_rechaza_dias_fuera_de_rango(day: int) -> None:
    """Un día fuera del rango 1-31 se rechaza en lugar de inventar una fecha."""
    with pytest.raises(ValueError, match="día"):
        resolve_day_of_month(day, date(2026, 9, 15))


@pytest.mark.parametrize(
    ("today", "day", "month", "expected"),
    [
        (date(2026, 9, 16), 4, 10, date(2026, 10, 4)),  # aún no ha llegado: este año
        (date(2026, 9, 16), 16, 9, date(2026, 9, 16)),  # es hoy: este año
        (date(2026, 9, 16), 4, 1, date(2027, 1, 4)),  # enero ya pasó: el año siguiente
        (date(2026, 9, 16), 15, 9, date(2027, 9, 15)),  # ayer: el año siguiente
        (date(2026, 9, 16), 31, 11, date(2026, 11, 30)),  # noviembre tiene 30 días
        (date(2026, 9, 16), 29, 2, date(2027, 2, 28)),  # 2027 no es bisiesto: último día
    ],
)
def test_el_n_de_un_mes_usa_este_ano_si_no_ha_pasado_y_si_no_el_siguiente(
    today: date, day: int, month: int, expected: date
) -> None:
    """«El N de <mes>» es este año si esa fecha no ha pasado (hoy incluido) y, si ya pasó, el año
    siguiente, con el mismo ajuste al último día del mes.
    """
    assert resolve_month_day(day, month, today) == expected


@pytest.mark.parametrize(("month", "day"), [(0, 4), (13, 4), (10, 0), (10, 32)])
def test_rechaza_mes_o_dia_fuera_de_rango(month: int, day: int) -> None:
    """Un mes fuera de 1-12 o un día fuera de 1-31 se rechazan en lugar de inventar una fecha."""
    with pytest.raises(ValueError, match=r"mes|día"):
        date_in_month(2026, month, day)
