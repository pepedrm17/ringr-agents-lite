"""Reglas de negocio para interpretar las fechas de pago que dice el usuario.

- «el día N»: este mes si el día N todavía no ha pasado (o es hoy); si ya pasó, el mes siguiente.
- «el N de <mes>»: este año si esa fecha todavía no ha pasado (o es hoy); si ya pasó, el año
  siguiente.
- En ambos casos, si ese mes no tiene día N (el 31 en septiembre, el 30 en febrero), es el último
  día del mes.
"""

import calendar
from datetime import date


def date_in_month(year: int, month: int, day: int) -> date:
    """Día ``day`` de ese mes, o el último del mes si no llega a ``day``."""
    if not 1 <= day <= 31:
        raise ValueError(f"El día debe estar entre 1 y 31, no {day}")
    if not 1 <= month <= 12:
        raise ValueError(f"El mes debe estar entre 1 y 12, no {month}")
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def resolve_day_of_month(day: int, today: date) -> date:
    """Devuelve la próxima fecha que corresponde a «el día ``day``» a partir de ``today``."""
    year, month = today.year, today.month
    if day < today.day:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return date_in_month(year, month, day)


def resolve_month_day(day: int, month: int, today: date) -> date:
    """Devuelve la próxima fecha que corresponde a «el ``day`` de <mes>» a partir de ``today``."""
    this_year = date_in_month(today.year, month, day)
    return this_year if this_year >= today else date_in_month(today.year + 1, month, day)
