"""Tests de la regla que convierte «el día N» en una fecha concreta."""

from datetime import date

import pytest

from ringr_agents.dates import resolve_day_of_month


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
