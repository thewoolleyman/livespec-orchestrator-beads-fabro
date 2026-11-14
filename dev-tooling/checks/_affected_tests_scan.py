"""_affected_tests_scan — the import graph of the repository, and who reaches a module.

The scanning half of `_affected_tests_selection`, split out along its own seam: this
module answers "which modules, tests among them, reach this one", and the selection
module decides what a change selects and whether the selected tests cover it.

A module REACHES another when it imports it, directly or through a chain of imported
modules, or when it names it in a string literal: a path, a file name or a dotted name,
which is how a test loads a script it cannot import. An import is matched by every
dotted-name suffix of the module it names, so it resolves from whichever sys.path root
a test runs under, and it counts each parent package, because importing a module runs
its packages. A conftest that reaches a module reaches the tests below it that request
one of its fixtures. Over-reaching only selects more tests, so every ambiguity here is
resolved toward the wider answer.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["Scan", "git_lines", "is_test", "scan_repository", "tests_reaching"]

_SCRIPTS_ROOT = ".claude-plugin/scripts/"
# A word-like run of characters, dots and dashes: a file name, or a dotted module name.
_TOKEN = re.compile(r"[\w-]+(?:\.[\w-]+)*")


@dataclass(frozen=True, kw_only=True)
class _Facts:
    imports: frozenset[str]
    tokens: frozenset[str]
    fixtures: frozenset[str]
    arguments: frozenset[str]


def _dotted(*, path: str) -> str:
    """The module name a repo-relative `.py` path is imported as, minus any scripts root."""
    name = path.removeprefix(_SCRIPTS_ROOT).removesuffix(".py").replace("/", ".")
    return name.removesuffix(".__init__")


def _absolute(*, name: str | None, level: int, own: str, is_package: bool) -> str:
    """Resolve a (possibly relative) `from` import's module to its dotted name."""
    if level == 0:
        return name or ""
    package = own.split(".") if is_package else own.split(".")[:-1]
    base = ".".join(package[: len(package) - level + 1])
    return f"{base}.{name}" if name else base


def _string_tokens(*, text: str) -> set[str]:
    """The words of a string literal; a dotted word also yields its dotted prefixes of 2+ parts."""
    tokens: set[str] = set()
    for word in _TOKEN.findall(text):
        parts = word.split(".")
        tokens.add(word)
        tokens.update(".".join(parts[:end]) for end in range(2, len(parts)))
    return tokens


def _is_fixture(*, node: ast.expr) -> bool:
    """Whether a decorator is `fixture` or `<anything>.fixture`, called or not."""
    target = node.func if isinstance(node, ast.Call) else node
    return (isinstance(target, ast.Name) and target.id == "fixture") or (
        isinstance(target, ast.Attribute) and target.attr == "fixture"
    )


def _facts(*, tree: ast.AST, path: str) -> _Facts:
    """The dotted names a module imports and every word its string literals hold."""
    imports: set[str] = set()
    tokens: set[str] = set()
    fixtures: set[str] = set()
    arguments: set[str] = set()
    own = _dotted(path=path)
    is_package = path.endswith("__init__.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(name=node.module, level=node.level, own=own, is_package=is_package)
            imports.add(base)
            imports.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            tokens.update(_string_tokens(text=node.value))
        elif isinstance(node, ast.arg):
            arguments.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
            _is_fixture(node=d) for d in node.decorator_list
        ):
            fixtures.add(node.name)
    return _Facts(
        imports=frozenset(imports),
        tokens=frozenset(tokens),
        fixtures=frozenset(fixtures),
        arguments=frozenset(arguments),
    )


def _git(*, root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )


def git_lines(*, root: Path, arguments: list[str]) -> list[str] | None:
    """Git's output lines, or None when git fails or `root` is not the repository's top level.

    Paths are read as repo-root-relative, so a `root` that sits below a repository's top level, or
    that git answers for only through an ancestor, would read as a different tree.
    """
    prefix = _git(root=root, arguments=["rev-parse", "--show-prefix"])
    if prefix.returncode != 0 or prefix.stdout.strip():
        return None
    done = _git(root=root, arguments=arguments)
    return done.stdout.splitlines() if done.returncode == 0 else None


def _read_graph(*, root: Path, files: list[str]) -> dict[str, _Facts] | str:
    """Parse every module, or name the first one that cannot be parsed."""
    graph: dict[str, _Facts] = {}
    for path in files:
        try:
            tree = ast.parse((root / path).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError) as failure:
            return f"{path} cannot be parsed ({type(failure).__name__})"
        graph[path] = _facts(tree=tree, path=path)
    return graph


def _suffix_index(*, files: list[str]) -> dict[str, set[str]]:
    """Every dotted-name suffix of every module, so an import resolves from any sys.path root."""
    index: dict[str, set[str]] = {}
    for path in files:
        parts = _dotted(path=path).split(".")
        for start in range(len(parts)):
            suffix = ".".join(parts[start:])
            if suffix not in sys.stdlib_module_names:
                index.setdefault(suffix, set()).add(path)
    return index


def _importers(*, graph: dict[str, _Facts], files: list[str]) -> dict[str, set[str]]:
    """Map each module to the modules that import it, counting each parent package."""
    index = _suffix_index(files=files)
    reverse: dict[str, set[str]] = {}
    for path, facts in graph.items():
        for name in facts.imports:
            parts = name.split(".")
            for end in range(1, len(parts) + 1):
                for target in index.get(".".join(parts[:end]), ()):
                    reverse.setdefault(target, set()).add(path)
    return reverse


@dataclass(frozen=True, kw_only=True)
class Scan:
    graph: dict[str, _Facts]
    reverse: dict[str, set[str]]
    named: dict[str, set[str]]


def _closure(*, seeds: set[str], scan: Scan) -> set[str]:
    """Every module that reaches a seed through imports or by naming it in a string."""
    seen = set(seeds)
    pending = deque(seeds)
    while pending:
        path = pending.popleft()
        names = {Path(path).name, _dotted(path=path)} - {"__init__.py"}
        named: set[str] = set()
        for name in names:
            named |= scan.named.get(name, set())
        for other in (scan.reverse.get(path, set()) | named) - seen:
            seen.add(other)
            pending.append(other)
    return seen


def is_test(*, path: str) -> bool:
    name = Path(path).name
    return path.startswith("tests/") and (name.startswith("test_") or name.endswith("_test.py"))


def tests_reaching(*, seeds: set[str], scan: Scan) -> set[str]:
    """The test modules that reach a seed.

    A test also reaches it through a fixture: one that requests, by argument name or in a string
    such as `usefixtures`, a fixture defined in a `conftest.py` that reaches the seed, below that
    conftest's directory. A conftest's autouse fixtures run in every test the gate selects.
    """
    reached = _closure(seeds=seeds, scan=scan)
    tests = {p for p in reached if is_test(path=p)}
    for conftest in (p for p in reached if Path(p).name == "conftest.py"):
        defined = scan.graph[conftest].fixtures
        directory = str(Path(conftest).parent) + "/"
        tests |= {
            p
            for p, facts in scan.graph.items()
            if is_test(path=p)
            and p.startswith(directory)
            and defined & (facts.arguments | facts.tokens)
        }
    return tests


def scan_repository(*, root: Path) -> Scan | str:
    """Parse every `.py` the repository holds and invert its import graph, or say why not."""
    listed = git_lines(
        root=root, arguments=["ls-files", "--cached", "--others", "--exclude-standard"]
    )
    if listed is None:
        return "the repository's files could not be listed"
    files = sorted(p for p in listed if p.endswith(".py") and "_vendor/" not in p)
    graph = _read_graph(root=root, files=files)
    if isinstance(graph, str):
        return graph
    named: dict[str, set[str]] = {}
    for path, facts in graph.items():
        for token in facts.tokens:
            named.setdefault(token, set()).add(path)
    return Scan(graph=graph, reverse=_importers(graph=graph, files=files), named=named)
