"""Whether a coverage entry's test node id names a test that exists.

`SPECIFICATION/contracts.md` makes "names a test that does not exist" one
of the three conditions that leave a heading uncovered, so this is the
one question that turns a registry row from a claim into evidence. The
answer is taken STATICALLY — a module file and, where the id names one, a
function definition inside it — and never by executing pytest, because a
detection pass must be a pure read of the tree.

WHY THREE SPELLINGS ARE ADMITTED AND NOT ONE. The registry's own rows
carry three, and a resolver that recognised only the dotted form would
report the other two as dangling — a FALSE finding manufactured by the
instrument rather than observed in the tree. Measured over this
repository's 124 non-`TODO` rows: 107 resolve as `module.function`, 11 as
a module with no function part, and 6 are genuinely dangling (a renamed
test). A dotted-only resolver reported 42 dangling, the extra 36 being
rows written in pytest's own `module::function` spelling.

WHY A MODULE-ONLY ID COUNTS AS EXISTING. A pytest node id may name a
module, and a registry row that names one is asking for the whole module
as the exercising test. The row is still a claim about coverage depth
rather than about existence, and depth is the shared `heading_coverage`
gate's tier direction to judge — not this one's.
"""

from __future__ import annotations

import ast
from pathlib import Path

__all__: list[str] = ["names_an_existing_test"]

# pytest's own node-id separator between a module path and the test inside
# it. The registry carries rows in both this spelling and the fully dotted
# one, so both resolve.
_NODE_SEPARATOR = "::"
_DOT = "."


def names_an_existing_test(*, project_root: Path, test_node: str) -> bool:
    """Whether `test_node` resolves to a test module, or to a function in one."""
    if _NODE_SEPARATOR in test_node:
        dotted, _, function = test_node.partition(_NODE_SEPARATOR)
        return _function_exists(
            module=_module_file(project_root=project_root, dotted=dotted),
            function=function,
        )
    whole = _module_file(project_root=project_root, dotted=test_node)
    if whole is not None:
        return True
    dotted, _, function = test_node.rpartition(_DOT)
    if not dotted:
        return False
    return _function_exists(
        module=_module_file(project_root=project_root, dotted=dotted),
        function=function,
    )


def _module_file(*, project_root: Path, dotted: str) -> Path | None:
    """The module file a dotted path names, or `None` when it names no file.

    `None` is an ANSWER rather than a gap in the reading: the read happened
    and there is no such module, which is exactly what a dangling entry looks
    like.
    """
    if not dotted:
        return None
    candidate = project_root.joinpath(*dotted.split(_DOT)).with_suffix(".py")
    return candidate if candidate.is_file() else None


def _function_exists(*, module: Path | None, function: str) -> bool:
    """Whether `module` defines `function`, read through its syntax tree.

    A module that does not PARSE defines nothing this reader can see, which
    is the honest answer for an entry pointing into a broken file: the
    surfaced finding then names the entry, and the broken file fails the
    suite on its own account.
    """
    if module is None or not function:
        return False
    source = module.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function
        for node in ast.walk(tree)
    )
