# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""tests_no_real_time — a test may not wait on, or assert about, the host clock.

Flaky master tests accounted for 9 of 37 defective factory endings after the
factory stability freeze, and all of them shared ONE shape: a real sleep plus a
tight elapsed bound, which passes on an idle laptop and fails on a loaded
factory host. The remedy is not a wider bound — that keeps the real-time
dependence and only moves the threshold — so this gate refuses the shape
itself. A test waits on a DETERMINISTIC EVENT (a joined thread, a set
`threading.Event`, a written file) and asserts on an INJECTED clock's readings
or on the ORDERING of those events.

TWO FORMS ARE REFUSED, and they are refused for different reasons.

A `time.sleep` call is refused because it is a wait whose length the host
decides: under load the thing being waited for may not have happened yet when
the sleep returns, and nothing in the test says so.

An `assert` reading a DIFFERENCE of real clock readings is refused because the
verdict it renders is about the host's scheduler rather than about the code. The
difference is tracked through local names, so the ordinary two-line spelling —
`started = time.monotonic()` then `elapsed = time.monotonic() - started` — is
seen as the one expression it is. Name tracking is PER SCOPE: a module that
assigns `elapsed` inside one function must not taint an identically-named local
in the next, which is exactly the over-reporting that makes a gate get switched
off.

WHAT THIS INSTRUMENT CANNOT SEE, stated so an absence is not read as coverage.
It matches the SUBTRACTION, so the rearranged form `observed_at >= started +
budget` is out of scope by construction, as is a bare instant comparison such
as `assert time.time() < deadline` — neither is a difference. A clock read
passed as FIXTURE DATA is deliberately not an offence either (`deadline =
int(time.time()) + 3600` seeds a value; it renders no timing verdict), and that
exclusion is what keeps the gate pointed at the flaky class instead of at every
test that mentions time. A sleep reached through an alias, or spelled inside a
string handed to a child process, is also unseen: the string case is
deliberate, since a subprocess fixture's own sleep is that fixture's business.

THERE IS NO STAND-DOWN YET. Every offence this finds is reported, and a test
whose subject genuinely IS real time therefore has nowhere to say so. That is
the next slice's job; until it lands, this gate refuses and names, and nothing
more.

TWO POSITIVE CONTROLS, because this check reports an ABSENCE for a living and a
scan that walked the wrong tree prints exactly what a clean suite prints. The
DISCOVERY control requires the tests walk to return a plausible number of files;
the MATCHER control requires the committed fixture's own marked lines to be
found, so a matcher that stopped recognising a form fails loudly instead of
certifying every test file in the repository.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Sequence
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
for _path in (_SCRIPT_DIR, _SCRIPTS, _SCRIPTS / "_vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script; it
# is imported from the installed shared dev-tooling package's vendored copy.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: that `_vendor` also carries a PARTIAL
# `livespec_runtime`, and putting it ahead of this repo's own `_vendor` shadows
# the full copy every plugin module imports.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = [
    "MINIMUM_SCANNED_FILES",
    "file_findings",
    "findings",
    "main",
]

# The discovery control's floor. The tests tree held 860 `.py` files when this
# gate landed, so a walk returning fewer than half that has lost the tree rather
# than found a clean one.
MINIMUM_SCANNED_FILES = 400

_TESTS_TREE = "tests"
_CONTROL_FIXTURE = Path("dev-tooling") / "checks" / "fixtures" / "real_time_control.py.txt"
# Every line the matcher must flag in the control fixture carries this marker.
_EXPECT_OFFENCE = "EXPECT-OFFENCE"

# The three readings whose DIFFERENCE is a verdict about the host.
_CLOCK_READS = frozenset({"monotonic", "perf_counter", "time"})
# Wrapping a reading in one of these keeps it a reading.
_COERCIONS = frozenset({"int", "float", "round"})

_SLEEP_FINDING = "waits in real time through time.sleep"
_ELAPSED_FINDING = "asserts on a difference of real clock readings"


def _reads_clock(*, node: ast.AST, attribute: str) -> bool:
    """Whether `node` is a `time.<attribute>()` call on the stdlib module."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
    )


def _is_sleep(*, node: ast.AST) -> bool:
    return _reads_clock(node=node, attribute="sleep")


def _is_instant(*, node: ast.expr, instants: frozenset[str]) -> bool:
    """Whether this expression denotes an instant read from the real clock.

    An instant plus or minus something that is NOT an instant is still an
    instant — which is what makes `int(time.time()) + 3600` fixture data rather
    than a measurement, and keeps it out of the elapsed rule below.
    """
    if any(_reads_clock(node=node, attribute=reading) for reading in _CLOCK_READS):
        return True
    if isinstance(node, ast.Name):
        return node.id in instants
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in _COERCIONS and any(
            _is_instant(node=argument, instants=instants) for argument in node.args
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub):
        return _is_instant(node=node.left, instants=instants) != _is_instant(
            node=node.right, instants=instants
        )
    return False


def _is_elapsed(*, node: ast.AST, instants: frozenset[str], elapsed: frozenset[str]) -> bool:
    """Whether this expression IS a difference of two real clock instants."""
    if isinstance(node, ast.Name):
        return node.id in elapsed
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Sub)
        and _is_instant(node=node.left, instants=instants)
        and _is_instant(node=node.right, instants=instants)
    )


def _holds_elapsed(*, node: ast.expr, instants: frozenset[str], elapsed: frozenset[str]) -> bool:
    return any(
        _is_elapsed(node=inner, instants=instants, elapsed=elapsed) for inner in ast.walk(node)
    )


def _assigned(*, statement: ast.stmt) -> tuple[tuple[str, ...], ast.expr | None]:
    """The simple names this statement binds, and the expression it binds them to."""
    if isinstance(statement, ast.Assign):
        return (
            tuple(target.id for target in statement.targets if isinstance(target, ast.Name)),
            statement.value,
        )
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return ((statement.target.id,), statement.value)
    return ((), None)


def _learn(*, statement: ast.stmt, instants: set[str], elapsed: set[str]) -> None:
    """Record what each name this statement binds now denotes.

    Rebinding a tracked name to something ordinary CLEARS it. Without that, a
    helper reusing the name `started` for an unrelated value would keep the
    earlier reading's taint and report an assertion that measures nothing.
    """
    names, value = _assigned(statement=statement)
    if value is None:
        return
    for name in names:
        if _holds_elapsed(node=value, instants=frozenset(instants), elapsed=frozenset(elapsed)):
            _ = instants.discard(name)
            elapsed.add(name)
        elif _is_instant(node=value, instants=frozenset(instants)):
            _ = elapsed.discard(name)
            instants.add(name)
        else:
            _ = instants.discard(name)
            _ = elapsed.discard(name)


def _nested_statements(*, statement: ast.stmt) -> tuple[Sequence[ast.stmt], ...]:
    """Every statement list this compound statement owns, in source order."""
    if isinstance(statement, ast.If | ast.While | ast.For | ast.AsyncFor):
        return (statement.body, statement.orelse)
    if isinstance(statement, ast.With | ast.AsyncWith):
        return (statement.body,)
    if isinstance(statement, ast.Try):
        return (
            statement.body,
            *(handler.body for handler in statement.handlers),
            statement.orelse,
            statement.finalbody,
        )
    if isinstance(statement, ast.Match):
        return tuple(case.body for case in statement.cases)
    return ()


def _span(*, node: ast.AST) -> tuple[int, int]:
    first = getattr(node, "lineno", 0)
    return (first, getattr(node, "end_lineno", None) or first)


def _scan(
    *,
    statements: Sequence[ast.stmt],
    instants: set[str],
    elapsed: set[str],
    offences: list[tuple[int, int, str]],
) -> None:
    """Collect every elapsed-assertion offence, learning names as they bind.

    A function or class body gets a COPY of the enclosing scope, so a name
    bound there cannot leak sideways into a sibling definition.
    """
    for statement in statements:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            _scan(
                statements=statement.body,
                instants=set(instants),
                elapsed=set(elapsed),
                offences=offences,
            )
            continue
        _learn(statement=statement, instants=instants, elapsed=elapsed)
        if isinstance(statement, ast.Assert) and _holds_elapsed(
            node=statement.test, instants=frozenset(instants), elapsed=frozenset(elapsed)
        ):
            first, last = _span(node=statement)
            offences.append((first, last, _ELAPSED_FINDING))
        for nested in _nested_statements(statement=statement):
            _scan(statements=nested, instants=instants, elapsed=elapsed, offences=offences)


def _offences(*, source: str) -> list[tuple[int, int, str]]:
    """Every offending expression in this source, as (first line, last line, what)."""
    tree = ast.parse(source)
    offences: list[tuple[int, int, str]] = [
        (*_span(node=node), _SLEEP_FINDING) for node in ast.walk(tree) if _is_sleep(node=node)
    ]
    _scan(statements=tree.body, instants=set(), elapsed=set(), offences=offences)
    return sorted(set(offences))


def file_findings(*, source: str, label: str) -> list[str]:
    """Every offence in one test file, each naming its file and line."""
    return [f"{label}:{first}: {what}" for first, _, what in _offences(source=source)]


def _matcher_control(*, repo_root: Path) -> list[str]:
    """The fixture's own marked lines must be exactly what the matcher finds."""
    path = repo_root / _CONTROL_FIXTURE
    if not path.is_file():
        return [f"control: the matcher control fixture {_CONTROL_FIXTURE} is missing"]
    source = path.read_text(encoding="utf-8")
    marked = sorted(
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if _EXPECT_OFFENCE in line
    )
    detected = sorted({first for first, _, _ in _offences(source=source)})
    fixture = _CONTROL_FIXTURE
    if detected == marked:
        return []
    return [f"control: the matcher found {detected} in {fixture}; its markers say {marked}"]


def findings(*, repo_root: Path) -> list[str]:
    """Every surviving offence under `tests/`, plus every failed control."""
    paths = sorted((repo_root / _TESTS_TREE).rglob("*.py"))
    found = [
        finding
        for path in paths
        for finding in file_findings(
            source=path.read_text(encoding="utf-8"),
            label=path.relative_to(repo_root).as_posix(),
        )
    ]
    scanned, floor = len(paths), MINIMUM_SCANNED_FILES
    if scanned < floor:
        found.append(f"control: the {_TESTS_TREE} walk returned {scanned}, below {floor}")
    found.extend(_matcher_control(repo_root=repo_root))
    return found


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("tests_no_real_time")
    found = findings(repo_root=_REPO_ROOT)
    for finding in found:
        log.error(finding, kind="control" if finding.startswith("control:") else "real-time")
    return 1 if found else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
