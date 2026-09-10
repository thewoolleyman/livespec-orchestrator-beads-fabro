# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""spec_id_presence_discipline — the overloaded spec id field is never tested for presence.

`WorkItem.spec_commitment_hint` (persisted as the beads-native `spec_id`
column) is OVERLOADED: it carries both the `plan:<slug>` anchor marker and a
genuine commitment to ratified spec text. `commands/_plan_anchor.py` owns the
discrimination and exports `is_plan_anchor` / `is_spec_commitment`; every
consumer that means to ask one of those two questions must ask it by name.

FOUR independent consumers instead tested the field for PRESENCE, which
answers neither question. That is not four slips; it is evidence about which
predicate is attractive, and the preconditions are permanent — un-overloading
the field would take an upstream change to the vendored runtime plus a data
migration across every live tenant. A docstring does not fail a build, so this
check makes the narrowing executable: a FIFTH consumer written the same way
fails here.

WHAT COUNTS AS A PRESENCE TEST. The scan is AST-based, so prose and comments
are invisible. A finding is raised when a read of the field — an attribute
`.spec_id` / `.spec_commitment_hint`, a `record["spec_id"]` subscript, a
`record.get("spec_id")` call, a bare name spelled exactly like the field, a
WALRUS whose value is any of those, or a local alias assigned from any of them
by plain, ANNOTATED, or walrus assignment — appears as:

- a `None` comparison (`is None`, `is not None`, `== None`, `!= None`);
- a `bool(...)` argument;
- a bare truthiness test (an `if` / `while` / ternary condition, an `assert`,
  a `not` operand, a boolean operand, or a comprehension filter).

THE ANNOTATED AND WALRUS FORMS ARE NOT EXOTIC, which is why they are in that
list. `hint: str | None = item.spec_id` is the idiomatic way to alias an
optional field, and `if (hint := item.spec_id):` the idiomatic way to read one
inline. A first cut of this scan tracked aliases only through a plain `Assign`
and tested only the walrus TARGET, so both shapes reintroduced a bare presence
test while the scan reported clean — the fifth consumer walking through the
guard written to catch it.

An EQUALITY COMPARISON AGAINST ANOTHER VALUE is deliberately NOT a finding:
`list_work_items` filters `item.spec_commitment_hint == with_spec_commitment_hint`,
which asks a third question that neither helper answers.

THE ALLOWLIST IS MEASURED, NOT GUESSED. Each entry below was confirmed to
raise a finding without it, and confirmed to need the raw field. Two sites the
original proposal named are absent because the scan measured them as needing
nothing: `store.py` reads the column through the `_optional_str` accessor
rather than testing it, and `commands/list_work_items.py` compares for
equality against a caller-supplied filter value.

TWO POSITIVE CONTROLS, because this check reports an ABSENCE for a living. A
broken pattern or a mis-scoped glob would make it permanently green while
printing exactly what a clean repo prints, so `main` refuses to report a clean
scan unless both controls hold:

- the DISCOVERY control asserts the package walk actually reached the modules
  that own and write the field, so a mis-scoped or unsplit file list fails
  rather than passing silently;
- the MATCHER control asserts the checked-in fixture, which carries known bare
  presence tests, still produces findings through the same read/parse/match
  path the package scan uses.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Iterable
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
# `livespec_dev_tooling` package's vendored copy.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = [
    "ALLOWLIST",
    "DISCOVERY_ANCHORS",
    "FIELD_NAMES",
    "Finding",
    "control_failures",
    "fixture_path",
    "main",
    "module_paths",
    "package_dir",
    "package_findings",
    "path_findings",
    "source_findings",
    "unallowed_findings",
]

FIELD_NAMES = frozenset({"spec_commitment_hint", "spec_id"})

# Package-relative POSIX paths whose raw read of the field was MEASURED to be
# legitimate. Named explicitly rather than matched by pattern, so widening the
# exemption is a reviewable diff.
ALLOWLIST: frozenset[str] = frozenset(
    {
        # Owns the discrimination: its parameter IS the raw field, and the
        # `is not None` / `bool(...)` tests here are the implementation the
        # rest of the package is required to call instead.
        "commands/_plan_anchor.py",
        # The write path. It builds `bd` argv and emits `--spec-id` only when
        # the draft carries one; a CLI argument builder has no occasion to
        # discriminate a marker from a commitment.
        "_beads_client_argv.py",
        # Narrows `str | None` to `str` for `removeprefix` AFTER
        # `is_plan_anchor` has already answered the discriminating question,
        # so the presence test is a typing obligation and not the predicate.
        "commands/_needs_attention_handoffs.py",
    }
)

# Package-relative POSIX paths the walk MUST reach. These are the modules that
# own, write, and read the field, so a walk that misses one is mis-scoped.
DISCOVERY_ANCHORS: tuple[str, ...] = (
    "_beads_client_argv.py",
    "commands/_plan_anchor.py",
    "store.py",
)

_PACKAGE_RELPATH = (".claude-plugin", "scripts", "livespec_orchestrator_beads_fabro")
_FIXTURE_RELPATH = ("dev-tooling", "checks", "fixtures", "spec_id_presence_control.py.txt")
_NONE_OPS = (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)
_FINDING_MESSAGE = "spec id field tested for presence; ask is_spec_commitment or is_plan_anchor"


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One presence test on the overloaded spec id field."""

    relpath: str
    lineno: int
    form: str
    expression: str


def _is_field_read(*, node: ast.AST, aliases: frozenset[str]) -> bool:
    match node:
        case ast.Attribute(attr=attr):
            return attr in FIELD_NAMES
        case ast.Name(id=name):
            return name in FIELD_NAMES or name in aliases
        case ast.Subscript(slice=ast.Constant(value=str() as key)):
            return key in FIELD_NAMES
        case ast.Call(func=ast.Attribute(attr="get"), args=[ast.Constant(value=str() as key), *_]):
            return key in FIELD_NAMES
        # A walrus IS the read it binds — `if (hint := item.spec_id):` tests
        # the field, not the name. Recognizing it here rather than at each
        # call site covers the truthiness, `None`-comparison and `bool(...)`
        # positions with one rule.
        case ast.NamedExpr(value=value):
            return _is_field_read(node=value, aliases=aliases)
        case _:
            return False


def _field_aliases(*, tree: ast.AST) -> frozenset[str]:
    """Local names assigned directly from a read of the field.

    `AnnAssign` is in the set because annotating the alias — the natural
    thing to do for a `str | None` field — must not launder the read. Its
    `value` is optional, and a bare annotation (`hint: str | None`) binds
    nothing, so the guard rejects it before asking what it reads.
    """
    aliases: set[str] = set()
    empty: frozenset[str] = frozenset()
    for node in ast.walk(tree):
        match node:
            case (
                ast.Assign(targets=[ast.Name(id=name)], value=value)
                | ast.AnnAssign(target=ast.Name(id=name), value=value)
                | ast.NamedExpr(target=ast.Name(id=name), value=value)
            ) if value is not None and _is_field_read(node=value, aliases=empty):
                aliases.add(name)
            case _:
                pass
    return frozenset(aliases)


def _truthiness_positions(*, tree: ast.AST) -> frozenset[int]:
    """Node ids of every expression evaluated for its truth value."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        match node:
            case (
                ast.If(test=test)
                | ast.While(test=test)
                | ast.IfExp(test=test)
                | ast.Assert(test=test)
            ):
                ids.add(id(test))
            case ast.BoolOp(values=values):
                ids.update(id(value) for value in values)
            case ast.UnaryOp(op=ast.Not(), operand=operand):
                ids.add(id(operand))
            case ast.comprehension(ifs=ifs):
                ids.update(id(condition) for condition in ifs)
            case _:
                pass
    return frozenset(ids)


def _is_none_literal(*, node: ast.AST) -> bool:
    match node:
        case ast.Constant(value=None):
            return True
        case _:
            return False


def _is_none_presence(*, node: ast.Compare, aliases: frozenset[str]) -> bool:
    if len(node.ops) != 1:
        return False
    if not isinstance(node.ops[0], _NONE_OPS):
        return False
    left = node.left
    right = node.comparators[0]
    if _is_field_read(node=left, aliases=aliases) and _is_none_literal(node=right):
        return True
    return _is_field_read(node=right, aliases=aliases) and _is_none_literal(node=left)


def _finding_form(
    *,
    node: ast.AST,
    aliases: frozenset[str],
    truthiness: frozenset[int],
) -> str | None:
    if id(node) in truthiness and _is_field_read(node=node, aliases=aliases):
        return "truthiness"
    match node:
        case ast.Compare() if _is_none_presence(node=node, aliases=aliases):
            return "none-comparison"
        case ast.Call(func=ast.Name(id="bool"), args=[argument]) if _is_field_read(
            node=argument, aliases=aliases
        ):
            return "bool-call"
        case _:
            return None


def source_findings(*, source: str, relpath: str) -> list[Finding]:
    """Every presence test on the field in one module's source."""
    tree = ast.parse(source, filename=relpath)
    aliases = _field_aliases(tree=tree)
    truthiness = _truthiness_positions(tree=tree)
    findings = [
        Finding(
            relpath=relpath,
            lineno=getattr(node, "lineno", 0),
            form=form,
            expression=ast.unparse(node),
        )
        for node, form in (
            (node, _finding_form(node=node, aliases=aliases, truthiness=truthiness))
            for node in ast.walk(tree)
        )
        if form is not None
    ]
    return sorted(findings, key=lambda finding: (finding.lineno, finding.form, finding.expression))


def package_dir(*, repo_root: Path) -> Path:
    """The scanned package root."""
    return repo_root.joinpath(*_PACKAGE_RELPATH)


def fixture_path(*, repo_root: Path) -> Path:
    """The positive-control fixture carrying known bare presence tests."""
    return repo_root.joinpath(*_FIXTURE_RELPATH)


def module_paths(*, root: Path) -> list[Path]:
    """Every module the scan walks under `root`.

    The walked tree is LIVE, so it can change underneath the walk. `os.walk`
    rather than `Path.rglob` because pathlib lists a directory and then opens
    it, and lets a `FileNotFoundError` from that open escape: a `__pycache__`
    removed concurrently between the two steps took this whole check down and
    turned master CI red on a pure version bump. `os.walk` ignores a `scandir`
    error by default, so a vanished subtree is dropped rather than fatal.

    `__pycache__` is pruned from the descent as well as tolerated: it can
    never hold a scanned `.py` module, and it is the directory that actually
    races here.
    """
    paths: list[Path] = []
    for parent, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname != "__pycache__"]
        paths.extend(Path(parent) / name for name in filenames if name.endswith(".py"))
    return sorted(paths)


def path_findings(*, paths: Iterable[Path], root: Path) -> list[Finding]:
    """Findings for an explicit file list — the shared read/parse/match path."""
    findings: list[Finding] = []
    for path in paths:
        findings.extend(
            source_findings(
                source=path.read_text(encoding="utf-8"),
                relpath=path.relative_to(root).as_posix(),
            )
        )
    return findings


def package_findings(*, repo_root: Path) -> list[Finding]:
    """Every presence test in the package, allowlist NOT applied."""
    root = package_dir(repo_root=repo_root)
    return path_findings(paths=module_paths(root=root), root=root)


def unallowed_findings(*, repo_root: Path) -> list[Finding]:
    """Every presence test the allowlist does not excuse."""
    return [
        finding
        for finding in package_findings(repo_root=repo_root)
        if finding.relpath not in ALLOWLIST
    ]


def control_failures(*, repo_root: Path) -> list[str]:
    """Why a clean scan of `repo_root` would not be trustworthy, if it would not."""
    failures: list[str] = []
    root = package_dir(repo_root=repo_root)
    discovered = {path.relative_to(root).as_posix() for path in module_paths(root=root)}
    failures.extend(
        f"discovery control: the walk of {root} did not reach {anchor}"
        for anchor in DISCOVERY_ANCHORS
        if anchor not in discovered
    )
    fixture = fixture_path(repo_root=repo_root)
    if not fixture.is_file():
        failures.append(f"matcher control: the positive-control fixture is missing at {fixture}")
        return failures
    if not path_findings(paths=[fixture], root=fixture.parent):
        failures.append(f"matcher control: no presence test was found in {fixture}")
    return failures


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("spec_id_presence_discipline")
    repo_root = Path.cwd()
    failures = control_failures(repo_root=repo_root)
    for failure in failures:
        log.error(
            "positive control failed; this scan cannot report a trustworthy absence",
            detail=failure,
        )
    findings = unallowed_findings(repo_root=repo_root)
    for finding in findings:
        log.error(
            _FINDING_MESSAGE,
            path=finding.relpath,
            line=finding.lineno,
            form=finding.form,
            expression=finding.expression,
        )
    return 1 if failures or findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
