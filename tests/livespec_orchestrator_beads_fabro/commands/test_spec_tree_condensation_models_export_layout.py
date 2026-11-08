"""The condensation models module lists each exported symbol on its own line."""

from __future__ import annotations

import ast
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._spec_tree_condensation_models as models

__all__: list[str] = []


def test_each_exported_symbol_sits_on_its_own_physical_line() -> None:
    tree = ast.parse(Path(models.__file__).read_text(encoding="utf-8"))
    exported: list[ast.expr] = []
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
            and isinstance(node.value, ast.List)
        ):
            exported = list(node.value.elts)
    lines = [element.lineno for element in exported]
    assert len(exported) == 2
    assert len(set(lines)) == len(lines)
