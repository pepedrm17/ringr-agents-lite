"""Motor común de los agentes.

``Agent.handle_turn`` sigue la secuencia del enunciado: responder, parsear,
validar y decidir, y ejecutar la acción. Cada agente concreto solo define su
endpoint y ``decide``, la regla que dice si con los datos parseados se actúa.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from ringr_agents.conversation import Conversation, ConversationModel, ParserModel, Role
from ringr_agents.http import HttpClient, HttpRequest, HttpResponse, Payload, build_post

RINGR_TOKEN = "ringr_test_token_9f3a2c1d"


class ActionStatus(StrEnum):
    NOT_NEEDED = "sin_accion"
    EXECUTED = "ejecutada"
    DUPLICATE = "duplicada"
    FAILED = "fallida"


@dataclass(frozen=True, slots=True)
class Decision:
    """Resultado de ``decide``: los datos a enviar, o el motivo para no actuar todavía."""

    payload: Payload | None
    reason: str = ""

    @classmethod
    def act(cls, payload: Payload) -> Decision:
        return cls(payload)

    @classmethod
    def wait(cls, reason: str) -> Decision:
        return cls(None, reason)


@dataclass(frozen=True, slots=True)
class TurnResult:
    answer: str
    parsed: dict[str, object]
    status: ActionStatus
    reason: str = ""
    request: HttpRequest | None = None
    response: HttpResponse | None = None


class Agent(ABC):
    action: ClassVar[str]
    endpoint: ClassVar[str]

    def __init__(
        self,
        conversation_model: ConversationModel,
        parser_model: ParserModel,
        http_client: HttpClient,
        *,
        token: str = RINGR_TOKEN,
    ) -> None:
        self._conversation_model = conversation_model
        self._parser_model = parser_model
        self._http_client = http_client
        self._token = token
        self._conversation = Conversation()
        self._registered = False

    @abstractmethod
    def decide(self, parsed: Mapping[str, object]) -> Decision:
        """Valida los datos parseados y decide si hay que ejecutar la acción."""

    def handle_turn(self, user_message: str) -> TurnResult:
        conversation = self._conversation.add(Role.USER, user_message)
        answer = self._conversation_model.answer_user(conversation)
        self._conversation = conversation.add(Role.AGENT, answer)
        parsed = self._parser_model.parse_data(self._conversation)

        decision = self.decide(parsed)
        if decision.payload is None:
            return TurnResult(answer, parsed, ActionStatus.NOT_NEEDED, decision.reason)
        if self._registered:
            reason = f"«{self.action}» ya se registró en esta conversación"
            return TurnResult(answer, parsed, ActionStatus.DUPLICATE, reason)

        request = build_post(self.endpoint, self._token, decision.payload)
        response = self._http_client.send(request)
        if response.status != 200:
            reason = (
                f"El endpoint respondió {response.status}; se reintentará en el siguiente turno"
            )
            return TurnResult(answer, parsed, ActionStatus.FAILED, reason, request, response)
        self._registered = True
        return TurnResult(answer, parsed, ActionStatus.EXECUTED, "", request, response)
