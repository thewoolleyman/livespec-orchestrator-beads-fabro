# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""needs_attention_surface_ownership — v079 ownership-boundary guard.

The needs-attention snapshot composition is orchestrator-owned: it MUST NOT
read overseer or foreman surfaces, and MUST NOT emit an item whose derivation
required one. This check keeps that negative constraint executable by scanning
only the composition modules:

- `commands/needs_attention.py`
- every `commands/_needs_attention*.py`

It deliberately does not scan the plan lane. In particular,
`commands/_plan_timeline.py` may mention the overseer in prose; that module is
outside the snapshot composition bound by this guard.

The check is AST-based rather than grep-based so comments are invisible and
docstring prose can mention the boundary without tripping it. Executable names,
imports, attributes, and non-docstring string constants still fail if they carry
the forbidden surface tokens.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_SCRIPTS_VENDOR = _SCRIPTS / "_vendor"
for _path in (_SCRIPTS, _SCRIPTS_VENDOR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy, whose path is added to
# `sys.path` here. The file-level pyright pragma above silences the
# untyped-structlog diagnostics this import would otherwise raise.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: since livespec-dev-tooling v1.90.0 that
# `_vendor` also carries a PARTIAL `livespec_runtime` (the github_budget
# modules only, no `work_items`), and putting it ahead of this repo's own
# `_vendor` shadowed the full copy every plugin module imports, so every
# check in this directory died on `No module named
# 'livespec_runtime.work_items'` (livespec-dev-tooling-8o8e.24 is the
# two-copies class). Appending keeps `structlog` resolvable while this
# repo's full vendored runtime keeps precedence.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = [
    "Finding",
    "main",
    "ownership_findings",
    "source_findings",
]

_FORBIDDEN_TOKENS = ("overseer", "foreman")
_COMMANDS_RELPATH = (
    ".claude-plugin",
    "scripts",
    "livespec_orchestrator_beads_fabro",
    "commands",
)


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One executable forbidden-surface reference in the composition."""

    path: Path
    token: str
    lineno: int
    reference: str


def _commands_dir(*, repo_root: Path) -> Path:
    return repo_root.joinpath(*_COMMANDS_RELPATH)


def _composition_paths(*, repo_root: Path) -> list[Path]:
    commands_dir = _commands_dir(repo_root=repo_root)
    paths = [commands_dir / "needs_attention.py"]
    paths.extend(sorted(commands_dir.glob("_needs_attention*.py")))
    return [path for path in paths if path.is_file()]


def _docstring_node_ids(*, tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.update(id(docstring_node) for docstring_node in ast.walk(body[0]))
    return ids


def _executable_nodes(*, tree: ast.AST) -> Iterator[ast.AST]:
    docstring_ids = _docstring_node_ids(tree=tree)
    for node in ast.walk(tree):
        if id(node) not in docstring_ids:
            yield node


def _references_from_node(*, node: ast.AST) -> Iterable[str]:
    match node:
        case ast.Import(names=names):
            return [alias.name for alias in names] + [
                alias.asname for alias in names if alias.asname is not None
            ]
        case ast.ImportFrom(module=module, names=names):
            return (
                ([module] if module is not None else [])
                + [alias.name for alias in names]
                + [alias.asname for alias in names if alias.asname is not None]
            )
        case ast.Name(id=name):
            return [name]
        case ast.Attribute(attr=attr):
            return [attr]
        case ast.Constant(value=value) if isinstance(value, str):
            return [value]
        case _:
            return []


def _forbidden_token(*, reference: str) -> str | None:
    lowered = reference.lower()
    for token in _FORBIDDEN_TOKENS:
        if token in lowered:
            return token
    return None


def source_findings(*, source: str, path: Path) -> list[Finding]:
    tree = ast.parse(source, filename=str(path))
    findings: list[Finding] = []
    for node in _executable_nodes(tree=tree):
        for reference in _references_from_node(node=node):
            token = _forbidden_token(reference=reference)
            if token is not None:
                findings.append(
                    Finding(
                        path=path,
                        token=token,
                        lineno=getattr(node, "lineno", 0),
                        reference=reference,
                    )
                )
    return sorted(findings, key=lambda finding: (finding.lineno, finding.reference))


def ownership_findings(*, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _composition_paths(repo_root=repo_root):
        findings.extend(source_findings(source=path.read_text(encoding="utf-8"), path=path))
    return findings


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("needs_attention_surface_ownership")
    findings = ownership_findings(repo_root=Path.cwd())
    for finding in findings:
        log.error(
            "needs-attention composition reads a forbidden ownership surface",
            path=str(finding.path),
            token=finding.token,
            line=finding.lineno,
            reference=finding.reference,
        )
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
