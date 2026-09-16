"""Demo por consola.

uv run python -m ringr_agents.demo                      # dos conversaciones de ejemplo
uv run python -m ringr_agents.demo chat cobros          # escribe tú los mensajes
uv run python -m ringr_agents.demo chat atencion
uv run python -m ringr_agents.demo --hoy 2026-09-15     # fija la fecha de hoy
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from typing import TextIO

from ringr_agents.agent import Agent, TurnResult
from ringr_agents.assistance import build_assistance_agent
from ringr_agents.debt import build_debt_agent

AGENTS: dict[str, Callable[[date], Agent]] = {
    "cobros": lambda today: build_debt_agent(today=lambda: today),
    # El agente de atención no usa la fecha: el guion bajo lo declara.
    "atencion": lambda _today: build_assistance_agent(),
}
TITLES = {"cobros": "cobros", "atencion": "atención al cliente"}
SCRIPTS: dict[str, list[str]] = {
    "cobros": ["Hola, tengo una deuda pendiente", "Pagaré 200 euros", "el 4", "mejor 250 euros"],
    "atencion": ["¿Cuál es vuestro horario?", "Quiero cambiar mi dirección postal", "Gracias"],
}


def _print_turn(out: TextIO, message: str, result: TurnResult) -> None:
    parsed = ", ".join(f"{key}={value!r}" for key, value in result.parsed.items())
    print(f"Usuario: {message}", file=out)
    print(f"Agente:  {result.answer}", file=out)
    print(f"Datos:   {parsed}", file=out)
    reason = f" ({result.reason})" if result.reason else ""
    print(f"Acción:  {result.status.value}{reason}", file=out)
    if result.request is not None:
        print(f"  {result.request.method} {result.request.url}", file=out)
        for name, value in result.request.headers.items():
            print(f"  {name}: {value}", file=out)
        print(f"  {result.request.body}", file=out)
    print(file=out)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m ringr_agents.demo", description=__doc__)
    parser.add_argument("modo", nargs="?", choices=["guion", "chat"], default="guion")
    parser.add_argument("agente", nargs="?", choices=sorted(AGENTS), default="cobros")
    parser.add_argument(
        "--hoy", type=date.fromisoformat, default=date.today(), metavar="AAAA-MM-DD"
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None, *, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout
) -> int:
    args = _parse_args(argv)
    print(f"Hoy es {args.hoy:%d/%m/%Y}.\n", file=stdout)
    if args.modo == "guion":
        for name, messages in SCRIPTS.items():
            print(f"=== Agente de {TITLES[name]} ===", file=stdout)
            agent = AGENTS[name](args.hoy)
            for message in messages:
                _print_turn(stdout, message, agent.handle_turn(message))
        return 0

    agent = AGENTS[args.agente](args.hoy)
    print(
        f"Chat con el agente de {TITLES[args.agente]}. Escribe «salir» para terminar.", file=stdout
    )
    for line in stdin:
        message = line.strip()
        if message.lower() == "salir":
            break
        if message:
            _print_turn(stdout, message, agent.handle_turn(message))
    return 0


if __name__ == "__main__":
    sys.exit(main())
