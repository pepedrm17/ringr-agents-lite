"""Agente de atención al cliente: resuelve dudas y registra solicitudes para un compañero.

Regla determinista (sin LLM): un mensaje del usuario es una solicitud si pide algo
con «quiero», «quisiera», «necesito», «me gustaría» o «solicito», incluido «quiero
saber...». Si el último de esos verbos del mensaje va negado («no quiero», «ya no
necesito», «tampoco quiero»), el usuario rechaza algo: no es una solicitud y anula
las anteriores. Vale la última solicitud de la conversación, así que si el registro
falla se reintenta en el siguiente turno aunque el usuario ya hable de otra cosa.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import ClassVar

from ringr_agents.agent import Agent, Decision
from ringr_agents.conversation import Conversation, Role
from ringr_agents.http import HttpClient, SimulatedHttpClient

ASSISTANCE_URL = "https://api.ringr.assistance/v1/request"

_REQUEST_VERB = re.compile(
    r"\b(?:(?P<negation>no|nunca|tampoco)\s+)?"
    r"(?:quiero|quisiera|necesito|me gustar[ií]a|solicito)\b",
    re.IGNORECASE,
)


class AssistanceParser:
    """ParserModel del agente de atención al cliente."""

    def parse_data(self, conversation: Conversation) -> dict[str, object]:
        for text in reversed(conversation.user_texts()):
            normalized = " ".join(text.split())
            verbs = list(_REQUEST_VERB.finditer(normalized))
            if not verbs:
                continue
            if verbs[-1].group("negation"):
                break  # rechaza algo: no hay solicitud y se anulan las anteriores
            return {"request": normalized}
        return {"request": None}


def decide_request(parsed: Mapping[str, object]) -> Decision:
    request = parsed.get("request")
    if not isinstance(request, str) or not request.strip():
        return Decision.wait("No hay ninguna solicitud que registrar")
    return Decision.act({"request": request.strip()})


class AssistanceConversationModel:
    """ConversationModel del agente de atención al cliente."""

    def __init__(self, parser: AssistanceParser) -> None:
        self._parser = parser

    def answer_user(self, conversation: Conversation) -> str:
        decision = decide_request(self._parser.parse_data(conversation))
        if decision.payload is None:
            return (
                "Te ayudo con tu duda. "
                "Si necesitas que un compañero gestione algo, dime qué quieres."
            )
        confirmation = f"Registro tu solicitud: «{decision.payload['request']}»."
        # Si ya se confirmó esa misma solicitud, no se repite la confirmación.
        if any(m.role is Role.AGENT and m.text == confirmation for m in conversation.messages):
            return "Esa solicitud ya está en curso; un compañero te contactará."
        return confirmation


class AssistanceAgent(Agent):
    action: ClassVar[str] = "register_request"
    endpoint: ClassVar[str] = ASSISTANCE_URL

    def decide(self, parsed: Mapping[str, object]) -> Decision:
        return decide_request(parsed)


def build_assistance_agent(http_client: HttpClient | None = None) -> AssistanceAgent:
    parser = AssistanceParser()
    client = http_client if http_client is not None else SimulatedHttpClient()
    return AssistanceAgent(AssistanceConversationModel(parser), parser, client)
