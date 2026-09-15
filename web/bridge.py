"""Puente entre la demo web y el paquete ringr_agents. Se ejecuta dentro de Pyodide."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date

from ringr_agents.agent import Agent, TurnResult
from ringr_agents.demo import AGENTS, SCRIPTS

PROJECT_ROOT = "/home/pyodide/proyecto"
_sessions: dict[str, Agent] = {}


def _to_dict(result: TurnResult) -> dict[str, object]:
    request = result.request
    return {
        "answer": result.answer,
        # Texto JSON exacto de cada valor: 200.0 se muestra como 200.0.
        "parsed": {
            key: json.dumps(value, ensure_ascii=False) for key, value in result.parsed.items()
        },
        "status": result.status.value,
        "reason": result.reason,
        "request": None
        if request is None
        else {
            "method": request.method,
            "url": request.url,
            "headers": dict(request.headers),
            "body": request.body,
        },
        "response_status": None if result.response is None else result.response.status,
    }


def start(session: str, kind: str, today_iso: str) -> str:
    _sessions[session] = AGENTS[kind](date.fromisoformat(today_iso))
    return json.dumps({"script": SCRIPTS[kind]}, ensure_ascii=False)


def turn(session: str, message: str) -> str:
    return json.dumps(_to_dict(_sessions[session].handle_turn(message)), ensure_ascii=False)


class _Collector:
    def __init__(self) -> None:
        self.by_file: dict[str, list[bool]] = defaultdict(list)

    def pytest_runtest_logreport(self, report: object) -> None:
        nodeid = str(getattr(report, "nodeid", ""))
        if getattr(report, "failed", False):
            self.by_file[nodeid.split("::", maxsplit=1)[0]].append(False)
        elif getattr(report, "when", "") == "call" and getattr(report, "passed", False):
            self.by_file[nodeid.split("::", maxsplit=1)[0]].append(True)


def run_tests() -> str:
    import pytest  # noqa: PLC0415 - pytest se descarga en el navegador solo al pulsar el botón

    previous = os.getcwd()
    os.chdir(PROJECT_ROOT)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    collector = _Collector()
    buffer = io.StringIO()
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            exit_code = int(pytest.main(["-p", "no:cacheprovider", "tests"], plugins=[collector]))
    finally:
        os.chdir(previous)
    files = [
        {"file": name, "passed": sum(results), "total": len(results)}
        for name, results in sorted(collector.by_file.items())
    ]
    return json.dumps(
        {
            "exit_code": exit_code,
            "seconds": round(time.perf_counter() - started, 2),
            "passed": sum(f["passed"] for f in files),
            "failed": sum(f["total"] - f["passed"] for f in files),
            "files": files,
            "output": buffer.getvalue(),
        },
        ensure_ascii=False,
    )
