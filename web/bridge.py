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
    """Recoge el resultado de cada test para poder explicar qué comprueba cada uno.

    Un test parametrizado se agrupa en una sola entrada con el número de casos.
    """

    def __init__(self) -> None:
        self.cases: dict[tuple[str, str], list[bool]] = defaultdict(list)
        self.docs: dict[tuple[str, str], str] = {}

    def pytest_collection_modifyitems(self, items: list[object]) -> None:
        for item in items:
            nodeid = str(getattr(item, "nodeid", ""))
            file, _, test = nodeid.partition("::")
            doc = getattr(getattr(item, "function", None), "__doc__", None)
            if doc:
                self.docs[(file, test.split("[")[0])] = " ".join(doc.split())

    def pytest_runtest_logreport(self, report: object) -> None:
        nodeid = str(getattr(report, "nodeid", ""))
        if "::" not in nodeid:
            return
        file, _, test = nodeid.partition("::")
        key = (file, test.split("[")[0])
        if getattr(report, "failed", False):
            self.cases[key].append(False)
        elif getattr(report, "when", "") == "call" and getattr(report, "passed", False):
            self.cases[key].append(True)


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
    tests = [
        {
            "file": file,
            "test": test,
            "doc": collector.docs.get((file, test), ""),
            "passed": sum(results),
            "cases": len(results),
        }
        for (file, test), results in sorted(collector.cases.items())
    ]
    return json.dumps(
        {
            "exit_code": exit_code,
            "seconds": round(time.perf_counter() - started, 2),
            "passed": sum(t["passed"] for t in tests),
            "failed": sum(t["cases"] - t["passed"] for t in tests),
            "tests": tests,
            "output": buffer.getvalue(),
        },
        ensure_ascii=False,
    )
