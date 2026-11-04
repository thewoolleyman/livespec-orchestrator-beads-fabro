# pyright: reportMissingImports=none, reportMissingTypeStubs=none
"""What counts as a real-time offence in one test source, and nothing else.

This is the MATCHER half of `tests_no_real_time` and it is a separate module
because the two halves change for different reasons. This one owns the
question "is THIS expression a wait on, or an assertion about, the host
clock", which moves when Python grows a statement form or a new spelling of a
reading appears. Its sibling owns which files are looked at, how an occurrence
is stood down, and the controls that keep a clean scan meaningful, which move
when the gate's scope or its exemption policy change.

TWO FORMS ARE OFFENCES, and they are offences for different reasons.

A `time.sleep` call is one because its length is the host's decision: under
load the thing being waited for may not have happened yet when the sleep
returns, and nothing in the test says so.

An `assert` reading a DIFFERENCE of real clock readings is one because the
verdict it renders is about the host's scheduler rather than about the code.
The difference is tracked through local names, so the ordinary two-line
spelling — `started = time.monotonic()` then `elapsed = time.monotonic() -
started` — is seen as the one expression it is. Name tracking is PER SCOPE: a
module that assigns `elapsed` inside one function must not taint an
identically-named local in the next, which is exactly the over-reporting that
makes a gate get switched off.

WHAT THIS CANNOT SEE, stated so an absence is not read as coverage. It matches
the SUBTRACTION, so the rearranged form `observed_at >= started + budget` is
out of scope by construction, as is a bare instant comparison such as `assert
time.time() < deadline` — neither is a difference. A clock read passed as
FIXTURE DATA is deliberately not an offence either (`deadline =
int(time.time()) + 3600` seeds a value; it renders no timing verdict), and
that exclusion is what keeps the gate pointed at the flaky class instead of at
every test that mentions time. A sleep reached through an alias, or spelled
inside a string handed to a child process, is also unseen: the string case is
deliberate, since a subprocess fixture's own sleep is that fixture's business.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

__all__: list[str] = [
    "ELAPSED_FINDING",
    "SLEEP_FINDING",
    "offences",
]

# The three readings whose DIFFERENCE is a verdict about the host.
_CLOCK_READS = frozenset({"monotonic", "perf_counter", "time"})
# Wrapping a reading in one of these keeps it a reading.
_COERCIONS = frozenset({"int", "float", "round"})

SLEEP_FINDING = "waits in real time through time.sleep"
ELAPSED_FINDING = "asserts on a difference of real clock readings"


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
            offences.append((first, last, ELAPSED_FINDING))
        for nested in _nested_statements(statement=statement):
            _scan(statements=nested, instants=instants, elapsed=elapsed, offences=offences)


def offences(*, source: str) -> list[tuple[int, int, str]]:
    """Every offending expression in this source, as (first line, last line, what)."""
    tree = ast.parse(source)
    offences: list[tuple[int, int, str]] = [
        (*_span(node=node), SLEEP_FINDING) for node in ast.walk(tree) if _is_sleep(node=node)
    ]
    _scan(statements=tree.body, instants=set(), elapsed=set(), offences=offences)
    return sorted(set(offences))
