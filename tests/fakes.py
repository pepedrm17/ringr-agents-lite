"""Dobles de prueba mínimos para probar el motor del agente sin reglas de negocio reales."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from ringr_agents.agent import Agent, Decision
from ringr_agents.conversation import Conversation


@dataclass
class RecordingModels:
    """ConversationModel y ParserModel a la vez: responde fijo y devuelve los datos indicados."""

    parsed: dict[str, object] = field(default_factory=dict)
    answered: list[Conversation] = field(default_factory=list)
    parsed_from: list[Conversation] = field(default_factory=list)

    def answer_user(self, conversation: Conversation) -> str:
        self.answered.append(conversation)
        return "respuesta"

    def parse_data(self, conversation: Conversation) -> dict[str, object]:
        self.parsed_from.append(conversation)
        return dict(self.parsed)


class PingAgent(Agent):
    """Agente de prueba: registra un ping cuando el parser devuelve un ``target``."""

    action: ClassVar[str] = "ping"
    endpoint: ClassVar[str] = "https://api.example.test/v1/ping"

    def decide(self, parsed: Mapping[str, object]) -> Decision:
        target = parsed.get("target")
        if not isinstance(target, str):
            return Decision.wait("Falta el destino del ping")
        return Decision.act({"target": target})
