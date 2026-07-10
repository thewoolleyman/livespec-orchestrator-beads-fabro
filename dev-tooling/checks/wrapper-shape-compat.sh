#!/usr/bin/env bash
set -euo pipefail
uv run python - <<'PYCODE'
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

root = Path.cwd()
rx = re.compile(r"^livespec(_[a-z0-9_]+)?\.")
bad: list[str] = []

for path in sorted((root / ".claude-plugin/scripts/bin").glob("*.py")):
    if path.name == "_bootstrap.py":
        continue
    body = ast.parse(path.read_text(encoding="utf-8")).body
    body = [
        stmt
        for stmt in body
        if not (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "__all__"
        )
    ]
    ok = (
        len(body) == 5
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
        and isinstance(body[1], ast.ImportFrom)
        and body[1].module == "_bootstrap"
        and len(body[1].names) == 1
        and body[1].names[0].name == "bootstrap"
        and isinstance(body[2], ast.Expr)
        and isinstance(body[2].value, ast.Call)
        and isinstance(body[2].value.func, ast.Name)
        and body[2].value.func.id == "bootstrap"
        and isinstance(body[3], ast.ImportFrom)
        and body[3].module is not None
        and rx.match(body[3].module) is not None
        and len(body[3].names) == 1
        and body[3].names[0].name == "main"
        and isinstance(body[4], ast.Raise)
        and isinstance(body[4].exc, ast.Call)
        and isinstance(body[4].exc.func, ast.Name)
        and body[4].exc.func.id == "SystemExit"
    )
    if not ok:
        bad.append(str(path.relative_to(root)))

for path in bad:
    print(f"wrapper shape violation: {path}", file=sys.stderr)
raise SystemExit(1 if bad else 0)
PYCODE
