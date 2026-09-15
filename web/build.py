"""Genera la demo web: una página autocontenida con el código del repositorio embebido.

Uso: python3 web/build.py [directorio_de_salida]   (por defecto _site)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent


def project_files() -> dict[str, str]:
    paths = [
        ROOT / "pyproject.toml",
        *sorted((ROOT / "src").rglob("*.py")),
        *sorted((ROOT / "tests").rglob("*.py")),
    ]
    return {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in paths
        if "__pycache__" not in p.parts
    }


def commit() -> str:
    sha = (
        os.environ.get("GITHUB_SHA")
        or subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
    )
    return sha[:7]


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_site")
    payload = {
        "files": project_files(),
        "bridge": (WEB / "bridge.py").read_text(encoding="utf-8"),
        "commit": commit(),
    }
    # "</" escapado para que ningún fichero cierre la etiqueta <script> antes de tiempo.
    embedded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (WEB / "template.html").read_text(encoding="utf-8")
    html = html.replace("__PAYLOAD__", embedded).replace(
        "__JS__", (WEB / "app.js").read_text(encoding="utf-8")
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"{out / 'index.html'}: {len(payload['files'])} ficheros del commit {payload['commit']}")


if __name__ == "__main__":
    main()
