"""Conversación: historial inmutable de mensajes y contratos de los dos modelos."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Role(StrEnum):
    USER = "user"
    AGENT = "agent"


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    text: str


@dataclass(frozen=True, slots=True)
class Conversation:
    """Historial ordenado. ``add`` devuelve una conversación nueva."""

    messages: tuple[Message, ...] = ()

    def add(self, role: Role, text: str) -> Conversation:
        return Conversation((*self.messages, Message(role, text)))

    def user_texts(self) -> list[str]:
        return [m.text for m in self.messages if m.role is Role.USER]


class ConversationModel(Protocol):
    """Genera la respuesta al usuario (``answer_user`` en el enunciado)."""

    def answer_user(self, conversation: Conversation) -> str: ...


class ParserModel(Protocol):
    """Extrae los datos estructurados de la conversación (``parse_data`` en el enunciado)."""

    def parse_data(self, conversation: Conversation) -> dict[str, object]: ...
