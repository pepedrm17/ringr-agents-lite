"""Agente de cobros: registra compromisos de pago.

Reglas deterministas para leer lo que dice el usuario (sin LLM):
- Importe: un número, con su signo si lo tiene, seguido de «€» o «euros» («200 euros»,
  «150,50 €»). Un importe negativo se lee tal cual y la validación lo rechaza.
- Fecha: «el 4» o «el día 4», según ``dates.resolve_day_of_month``, o una fecha
  completa «2026-10-04».
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
from ringr_agents.dates import resolve_day_of_month
from ringr_agents.http import HttpClient, SimulatedHttpClient

DEBT_URL = "https://api.ringr.debt/v1/commitment"
CONFIRMATION = "Perfecto, anoto"

_AMOUNT = re.compile(r"(?<![\d.,])([-+]?\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?\b)", re.IGNORECASE)
_FULL_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DAY = re.compile(r"\bel\s+(?:d[ií]a\s+)?(\d{1,2})\b(?!\s*(?:€|euros?\b|de\s+\w))", re.IGNORECASE)
_ISO_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")

type Today = Callable[[], date]


class DebtParser:
    """ParserModel del agente de cobros."""

    def __init__(self, today: Today = date.today) -> None:
        self._today = today

    def parse_data(self, conversation: Conversation) -> dict[str, object]:
        commitment_date: str | None = None
        committed_amount: float | None = None
        for text in conversation.user_texts():
            if amounts := _AMOUNT.findall(text):
                committed_amount = float(amounts[-1].replace(",", "."))
            if mentioned := self._last_date_in(text):
                commitment_date = mentioned
        return {"commitment_date": commitment_date, "committed_amount": committed_amount}

    def _last_date_in(self, text: str) -> str | None:
        """La fecha mencionada más a la derecha: completa (yyyy-mm-dd) o «el día N»."""
        found = [(m.start(), m.group(1)) for m in _FULL_DATE.finditer(text)]
        found += [
            (m.start(), resolve_day_of_month(int(m.group(1)), self._today()).isoformat())
            for m in _DAY.finditer(text)
            if 1 <= int(m.group(1)) <= 31
        ]
        return max(found)[1] if found else None


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


def follow_up_question(parsed: Mapping[str, object], today: date) -> str:
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
    return str(int(amount)) if amount.is_integer() else f"{amount:.2f}".replace(".", ",")


class DebtConversationModel:
    """ConversationModel del agente de cobros: pide lo que falta y confirma el compromiso."""

    def __init__(self, parser: DebtParser, today: Today = date.today) -> None:
        self._parser = parser
        self._today = today

    def answer_user(self, conversation: Conversation) -> str:
        parsed = self._parser.parse_data(conversation)
        decision = decide_commitment(parsed, self._today())
        if decision.payload is None:
            return f"{decision.reason}. {follow_up_question(parsed, self._today())}"
        payment_date = date.fromisoformat(str(decision.payload["commitment_date"]))
        amount = float(decision.payload["committed_amount"])
        confirmation = (
            f"{CONFIRMATION} el pago de {_euros(amount)} € para el {payment_date:%d/%m/%Y}."
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
