"""Agente de cobros: registra compromisos de pago.

Reglas deterministas para leer lo que dice el usuario (sin LLM):
- Importe: un número con su signo si lo tiene. La moneda por defecto es el euro, así que
  «200 euros», «150,50 €» y «200» a secas son lo mismo; un número que forma parte de una
  fecha («el 4») no es un importe. Un separador seguido de tres cifras son millares
  («5.570» son 5570) y de una o dos, céntimos («55,70»). Un importe negativo se lee tal
  cual y la validación lo rechaza.
- Fecha: «el 4» o «el día 4», según ``dates.resolve_day_of_month``; «el 4 de octubre»,
  con año opcional («el 4 de octubre de 2027»), según ``dates.resolve_month_day``; o una
  fecha completa «2026-10-04».
- Si el usuario menciona un dato varias veces, vale lo último que dijo, también dentro
  de un mismo mensaje («el 4, mejor el 5»).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from datetime import date
from typing import ClassVar, cast

from ringr_agents.agent import RINGR_TOKEN, Agent, Decision
from ringr_agents.conversation import Conversation, ConversationModel, ParserModel, Role
from ringr_agents.dates import date_in_month, resolve_day_of_month, resolve_month_day
from ringr_agents.http import HttpClient, SimulatedHttpClient

DEBT_URL = "https://api.ringr.debt/v1/commitment"

_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# Un separador seguido de tres cifras son millares («5.570»); de una o dos, céntimos («55,70»).
_NUMBER_CORE = r"(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
_DECIMALS = re.compile(r"[.,](\d{1,2})$")

_AMOUNT = re.compile(rf"(?<![\d.,])([-+]?{_NUMBER_CORE})\s*(?:€|euros?\b)", re.IGNORECASE)
# Número suelto, sin moneda: se lee como euros si no forma parte de una fecha.
# «el N» / «el día N» siempre es una referencia a un día, resuelva o no a una fecha.
_NUMBER = re.compile(rf"(?<![\d.,])([-+]?{_NUMBER_CORE})(?![\d.,])")
_DAY_REFERENCE = re.compile(r"\bel\s+(?:d[ií]a\s+)?(\d{1,2})\b", re.IGNORECASE)
_FULL_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DAY = re.compile(r"\bel\s+(?:d[ií]a\s+)?(\d{1,2})\b(?!\s*(?:€|euros?\b|de\s+\w))", re.IGNORECASE)
# «el 4 de octubre», «día 4 de octubre», «4 de octubre», con año opcional: «... de 2027».
_MONTH_DATE = re.compile(
    r"\b(?:el\s+)?(?:d[ií]a\s+)?(\d{1,2})\s+de\s+"
    rf"({'|'.join(_MONTHS)})\b"
    r"(?:\s+de\s+(\d{4})\b)?",
    re.IGNORECASE,
)
_ISO_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")

type Today = Callable[[], date]


def _to_amount(raw: str) -> float:
    """«5.570» son 5570 euros; «55,70» son 55 euros con 70 céntimos."""
    sign = -1.0 if raw.startswith("-") else 1.0
    digits = raw.lstrip("+-")
    if decimals := _DECIMALS.search(digits):
        whole = digits[: decimals.start()].replace(".", "").replace(",", "")
        return sign * float(f"{whole}.{decimals.group(1)}")
    return sign * float(digits.replace(".", "").replace(",", ""))


class DebtParser:
    """ParserModel del agente de cobros."""

    def __init__(self, today: Today = date.today) -> None:
        self._today = today

    def parse_data(self, conversation: Conversation) -> dict[str, object]:
        commitment_date: str | None = None
        committed_amount: float | None = None
        for text in conversation.user_texts():
            dates = self._dates_in(text)
            if (amount := self._last_amount_in(text, dates)) is not None:
                committed_amount = amount
            if dates:
                commitment_date = max(dates)[2]
        return {"commitment_date": commitment_date, "committed_amount": committed_amount}

    def _dates_in(self, text: str) -> list[tuple[int, int, str]]:
        """Fechas mencionadas y el tramo de texto que ocupa cada una."""
        found = [(m.start(), m.end(), m.group(1)) for m in _FULL_DATE.finditer(text)]
        found += [
            (m.start(), m.end(), resolve_day_of_month(int(m.group(1)), self._today()).isoformat())
            for m in _DAY.finditer(text)
            if 1 <= int(m.group(1)) <= 31
        ]
        found += [
            (m.start(), m.end(), mentioned.isoformat())
            for m in _MONTH_DATE.finditer(text)
            if (mentioned := self._month_date(m)) is not None
        ]
        return found

    def _last_amount_in(self, text: str, dates: list[tuple[int, int, str]]) -> float | None:
        """El importe más a la derecha. La moneda por defecto es el euro, así que un número
        suelto es un importe, salvo que forme parte de una fecha.
        """
        if with_currency := _AMOUNT.findall(text):
            return _to_amount(with_currency[-1])
        # «el 15 de cada mes» no da fecha, pero ese 15 sigue siendo un día, no un importe.
        taken = [(start, end) for start, end, _ in dates]
        taken += [(m.start(1), m.end(1)) for m in _DAY_REFERENCE.finditer(text)]
        loose = [
            m
            for m in _NUMBER.finditer(text)
            if not any(start <= m.start(1) < end for start, end in taken)
        ]
        return _to_amount(loose[-1].group(1)) if loose else None

    def _month_date(self, match: re.Match[str]) -> date | None:
        """«el 4 de octubre [de 2027]». Devuelve ``None`` si el día o el año no son válidos."""
        day, month = int(match.group(1)), _MONTHS[match.group(2).lower()]
        if not 1 <= day <= 31:
            return None
        if (year := match.group(3)) is None:
            return resolve_month_day(day, month, self._today())
        return date_in_month(int(year), month, day) if int(year) >= date.min.year else None


MISSING_DATE = "Falta la fecha"
MISSING_AMOUNT = "Falta el importe"


def _date_problem(raw_date: object, today: date) -> str | None:
    if raw_date is None:
        return MISSING_DATE
    if not isinstance(raw_date, str) or not _ISO_FORMAT.fullmatch(raw_date):
        return f"La fecha {raw_date} no es válida"
    try:
        payment_date = date.fromisoformat(raw_date)
    except ValueError:
        return f"La fecha {raw_date} no es válida"
    return f"La fecha {raw_date} ya ha pasado" if payment_date < today else None


def _amount_problem(amount: object) -> str | None:
    if amount is None:
        return MISSING_AMOUNT
    if isinstance(amount, bool) or not isinstance(amount, int | float) or not 0 < amount < math.inf:
        return "El importe debe ser mayor que cero"
    return None


def decide_commitment(parsed: Mapping[str, object], today: date) -> Decision:
    """Se registra con fecha válida no pasada e importe mayor que cero.

    Si no, el motivo reúne a la vez los problemas de la fecha y del importe.
    """
    raw_date, amount = parsed.get("commitment_date"), parsed.get("committed_amount")
    date_problem, amount_problem = _date_problem(raw_date, today), _amount_problem(amount)
    if date_problem == MISSING_DATE and amount_problem == MISSING_AMOUNT:
        return Decision.wait("Faltan la fecha y el importe")
    if date_problem or amount_problem:
        return Decision.wait(". ".join(p for p in (date_problem, amount_problem) if p))
    # Sin problemas, la fecha es un texto yyyy-mm-dd y el importe un número positivo.
    return Decision.act(
        {"commitment_date": cast(str, raw_date), "committed_amount": float(cast(float, amount))}
    )


def _follow_up_question(parsed: Mapping[str, object], today: date) -> str:
    """Pregunta solo por lo que falta o no es válido."""
    date_problem = _date_problem(parsed.get("commitment_date"), today)
    amount_problem = _amount_problem(parsed.get("committed_amount"))
    if date_problem and amount_problem:
        return "¿Qué día y cuánto podrás pagar?"
    if date_problem:
        return (
            "¿Qué día podrás pagar?"
            if date_problem == MISSING_DATE
            else "¿Qué otra fecha te viene bien?"
        )
    return (
        "¿Cuánto podrás pagar?"
        if amount_problem == MISSING_AMOUNT
        else "¿Qué importe podrás pagar?"
    )


def _euros(amount: float) -> str:
    """Formato español: 1200.0 → «1.200»; 150.5 → «150,50»."""
    whole, decimals = f"{amount:,.2f}".split(".")
    whole = whole.replace(",", ".")
    return whole if decimals == "00" else f"{whole},{decimals}"


class DebtConversationModel:
    """ConversationModel del agente de cobros: pide lo que falta y confirma el compromiso."""

    def __init__(self, parser: DebtParser, today: Today = date.today) -> None:
        self._parser = parser
        self._today = today

    def answer_user(self, conversation: Conversation) -> str:
        parsed = self._parser.parse_data(conversation)
        decision = decide_commitment(parsed, self._today())
        if decision.payload is None:
            return f"{decision.reason}. {_follow_up_question(parsed, self._today())}"
        payment_date = date.fromisoformat(str(decision.payload["commitment_date"]))
        amount = float(decision.payload["committed_amount"])
        confirmation = (
            f"Perfecto, anoto el pago de {_euros(amount)} € para el {payment_date:%d/%m/%Y}."
        )
        # Si ya se confirmó ese mismo compromiso, no se repite la confirmación.
        if any(m.role is Role.AGENT and m.text == confirmation for m in conversation.messages):
            return "Ese compromiso ya lo tengo anotado. Gracias."
        return confirmation


class DebtAgent(Agent):
    action: ClassVar[str] = "register_commitment"
    endpoint: ClassVar[str] = DEBT_URL

    def __init__(
        self,
        conversation_model: ConversationModel,
        parser_model: ParserModel,
        http_client: HttpClient,
        *,
        token: str = RINGR_TOKEN,
        today: Today = date.today,
    ) -> None:
        super().__init__(conversation_model, parser_model, http_client, token=token)
        self._today = today

    def decide(self, parsed: Mapping[str, object]) -> Decision:
        return decide_commitment(parsed, self._today())


def build_debt_agent(
    http_client: HttpClient | None = None, *, today: Today = date.today
) -> DebtAgent:
    parser = DebtParser(today)
    client = http_client if http_client is not None else SimulatedHttpClient()
    return DebtAgent(DebtConversationModel(parser, today), parser, client, today=today)
