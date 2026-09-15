"""Integración HTTP simulada: las requests se construyen completas pero no salen del proceso."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

type Payload = Mapping[str, str | float]


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: str


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int


class HttpClient(Protocol):
    def send(self, request: HttpRequest) -> HttpResponse: ...


def build_post(url: str, token: str, payload: Payload) -> HttpRequest:
    """POST con Bearer token, los datos como cabeceras (mismo nombre) y como cuerpo JSON."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # " ".join(split()) evita que un salto de línea del usuario rompa las cabeceras.
    headers.update({name: " ".join(str(value).split()) for name, value in payload.items()})
    return HttpRequest("POST", url, headers, json.dumps(dict(payload), ensure_ascii=False))


class SimulatedHttpClient:
    """No abre red: guarda cada request y responde 200, salvo los estados programados."""

    def __init__(self, statuses: Iterable[int] = ()) -> None:
        self.requests: list[HttpRequest] = []
        self._statuses = list(statuses)

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(self._statuses.pop(0) if self._statuses else 200)
