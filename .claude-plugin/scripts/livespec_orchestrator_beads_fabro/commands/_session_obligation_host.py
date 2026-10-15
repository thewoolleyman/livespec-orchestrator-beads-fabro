"""Where a host DECLARES its independent recovery coverage, and where obligations live.

`contracts.md` section "Launch obligations and consumed recovery" requires the
declaration to be a real artifact rather than an argument: "A protected-host
coverage declaration MUST be visible through inventory/check and bind the
runtime and version, terminal backend/version and instance, independent service
identity and generation, authorized recovery route, maximum observation interval
and takeover/launch budget, and installed proof artifact identity." This module
is the READ of that artifact off one host, and nothing else — the grade is
`_session_obligation_coverage`, which stays pure precisely so every state it
distinguishes can be exercised without the host this module reads.

WHY THE DECLARATION IS A FILE AND NOT A COMMAND-LINE OPTION. The same clause
says the declaration "is runtime evidence, not a user-selectable exemption", so
the value a launch is graded against has to be something INSTALLED on the host
rather than something the launching caller hands in. There is deliberately no
parameter any caller can put a declaration in; the only input is the path it is
installed at, and that is derived from the repository.

WHY IT DOES NOT LIVE IN THE OBLIGATION STORE. `outstanding_obligations` reads
every `*.json` under the store root as an obligation, so a declaration filed
there would be censused as an UNREADABLE one — and every completion gate would
then report the host's own coverage declaration as outstanding work.

WHY AN ABSENT FILE AND AN UNREADABLE ONE ANSWER DIFFERENTLY, and why the split
is at the SHAPE rather than at the content. A file that is not there is a host
declaring no owner, which the grade reports as the confident negative
`unmonitored`. A file that IS there and whose bytes this build cannot resolve
into the declared field set is a failure to OBSERVE, which the grade reports as
`unobservable`; the clause keeps those two apart because their remedies differ
in both directions. A declaration that is well-shaped but holds blanks, a PID, an
unknown route or budgets that do not fit the bound is CONTENT, and belongs to the
pure ladder rather than to this reader — deciding it here would put half the
coverage decision somewhere no test can reach without a filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    DIAGNOSTIC_COVERAGE_UNREADABLE,
    CoverageDeclaration,
    CoverageReading,
)

__all__: list[str] = [
    "COVERAGE_DECLARATION_FILENAME",
    "coverage_declaration_path",
    "host_coverage_reading",
    "obligation_store_root",
]

COVERAGE_DECLARATION_FILENAME = "session-coverage.json"

# Every identity the clause enumerates, as the declaration spells it. This tuple
# IS the schema: a payload missing one of these names, or holding it at another
# type, is a declaration this build cannot read rather than one it may grade.
_TEXT_FIELDS: tuple[str, ...] = (
    "proof_artifact",
    "recovery_route",
    "runtime",
    "runtime_version",
    "service_generation",
    "service_identity",
    "terminal_backend",
    "terminal_instance",
    "terminal_version",
)

# The two measured timing budgets, read as numbers and handed on AS READ. The
# bound they must fit TOGETHER is the pure grade's to apply, so a budget that
# overruns is reported as a finding about the host rather than as a file nobody
# could parse.
_BUDGET_FIELDS: tuple[str, ...] = (
    "max_observation_interval_seconds",
    "takeover_budget_seconds",
)

_UNREADABLE = CoverageReading(declaration=None, diagnostic=DIAGNOSTIC_COVERAGE_UNREADABLE)


def obligation_store_root(*, primary: Path) -> Path:
    """The durable launch-obligation store this host's repository registers into.

    It sits BESIDE the session-wait store rather than inside it, because the
    whole guarantee of the registration is that an obligation survives a
    coordinator that never armed a wait — and a record filed under the wait
    store would be discoverable only by a reader walking wait rows.
    """
    return primary / "tmp" / "session-obligations"


def coverage_declaration_path(*, primary: Path) -> Path:
    return primary / "tmp" / COVERAGE_DECLARATION_FILENAME


def host_coverage_reading(*, path: Path) -> CoverageReading:
    """Read one host's coverage declaration, or report why it could not be read."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return CoverageReading(declaration=None)
    except OSError:
        return _UNREADABLE
    return _declared(raw=raw)


def _declared(*, raw: str) -> CoverageReading:
    """Grade the BYTES of a declaration that was read, apart from reading it."""
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return _UNREADABLE
    if not isinstance(loaded, dict):
        return _UNREADABLE
    payload = cast("dict[str, object]", loaded)
    if not _well_shaped(payload=payload):
        return _UNREADABLE
    return CoverageReading(declaration=_declaration(payload=payload))


def _well_shaped(*, payload: dict[str, object]) -> bool:
    """Whether every declared field is present at the type the schema names."""
    return all(isinstance(payload.get(name), str) for name in _TEXT_FIELDS) and all(
        _is_number(value=payload.get(name)) for name in _BUDGET_FIELDS
    )


def _is_number(*, value: object) -> bool:
    """Whether a budget field holds a real number.

    `bool` is excluded explicitly because it is an `int` subclass, so `True`
    would otherwise read as a one-second budget — a well-typed declaration
    carrying a value no operator wrote.
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


def _declaration(*, payload: dict[str, object]) -> CoverageDeclaration:
    """Build the declaration from a payload `_well_shaped` has already graded."""
    return CoverageDeclaration(
        runtime=cast("str", payload["runtime"]),
        runtime_version=cast("str", payload["runtime_version"]),
        terminal_backend=cast("str", payload["terminal_backend"]),
        terminal_version=cast("str", payload["terminal_version"]),
        terminal_instance=cast("str", payload["terminal_instance"]),
        service_identity=cast("str", payload["service_identity"]),
        service_generation=cast("str", payload["service_generation"]),
        recovery_route=cast("str", payload["recovery_route"]),
        max_observation_interval_seconds=float(
            cast("float", payload["max_observation_interval_seconds"])
        ),
        takeover_budget_seconds=float(cast("float", payload["takeover_budget_seconds"])),
        proof_artifact=cast("str", payload["proof_artifact"]),
    )
