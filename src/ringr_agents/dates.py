"""Regla de negocio para interpretar «el día N» como fecha de pago.

- Si el día N de este mes todavía no ha pasado (o es hoy), es este mes.
- Si ya ha pasado, es el mes siguiente.
- Si ese mes no tiene día N (por ejemplo, el 31 en septiembre), es el último día del mes.
"""

import calendar
from datetime import date


def resolve_day_of_month(day: int, today: date) -> date:
    """Devuelve la próxima fecha que corresponde a «el día ``day``» a partir de ``today``."""
    if not 1 <= day <= 31:
        raise ValueError(f"El día debe estar entre 1 y 31, no {day}")
    year, month = today.year, today.month
    if day < today.day:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))
