"""The facade's `settings` verb and the scheduler ceiling it is read for.

Overflow selection needs one number no other facade verb carries — a factory's
own `max_concurrent_runs` — and the factory-overflow-selection clause of
`SPECIFICATION/contracts.md` requires it to be read "from that candidate's own
Fabro server at selection time". `fabro settings --json` is the measured route
(hp reported 10 and petri 2 on 2026-10-19), so the verb belongs on the facade
family rather than in whichever module needed the figure: `_fabro_port` is the
one place this package reaches the engine.

WHY THE PARSE SEARCHES FOR A `scheduler` BLOCK RATHER THAN READING A FIXED PATH.
Two spellings of the same figure have been measured. The ratifying revision
named `server.scheduler.max_concurrent_runs`, while the 2026-08-22 retention
spike recorded the server block one level deeper — "the `server.server` block
is listen, api, web, auth, sandbox, storage, artifacts, slatedb, scheduler,
logging, integrations". A fixed-path read is correct for exactly one of those
and returns `None` for the other, and `None` is read downstream as "this
candidate has no free slot" — so a build whose settings nest one level
differently would silently retire overflow selection while every surface still
reported a healthy dispatch. Both spellings are asserted here for that reason.

WHY AN ABSENT AND AN UNUSABLE FIGURE ANSWER IDENTICALLY, and why neither is a
zero. A ceiling of 0 would mean a server that runs nothing; the absence of a
readable ceiling means the question was not answered. Both are `None`, which the
clause's own fail-closed direction turns into "no free slot" — never into a
candidate with infinite room.

WHY BOTH SUBJECTS ARE REACHED THROUGH A SYMBOL ASSERTION FIRST. The verb and the
parse are additions to EXISTING modules, so a top-level import of either would
succeed at Red and the cases would die on an `AttributeError` at call time
rather than on an assertion. Asserting the declared surface first makes the Red
a genuine statement about behaviour that is not there yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _fabro_port_records as records
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget

_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_HP_CEILING = 10
_PETRI_CEILING = 2
_PARSE_NAME = "scheduler_max_concurrent_runs_from_payload"
_VERB_NAME = "settings"


@dataclass(kw_only=True)
class _Runner:
    """Records every argv and answers with the queued results, in order."""

    results: list[CommandResult]
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.argvs.append(argv)
        return self.results.pop(0)


def _ceiling_of(*, payload: object | None) -> int | None:
    """The scheduler ceiling one payload reports, through the declared surface."""
    assert _PARSE_NAME in records.__all__
    parse: Any = getattr(records, _PARSE_NAME)
    ceiling: object = parse(payload=payload)
    assert ceiling is None or isinstance(ceiling, int)
    return ceiling


def _port(*, runner: _Runner, cwd: Path) -> Any:
    assert _VERB_NAME in vars(FabroPort)
    return FabroPort(
        fabro_bin="/opt/fabro",
        target=FabroTarget(server_url=_SERVER),
        runner=runner,
        cwd=cwd,
    )


def test_the_settings_verb_asks_this_ports_own_server_in_json(tmp_path: Path) -> None:
    """`settings` carries `--json` and addresses the factory the port is bound to.

    `--server` is asserted as the LAST TWO argv tokens because the pinned engine
    requires the flag to stay last on the subcommand, and as adjacent tokens
    rather than by substring because an address spliced onto the flag would
    satisfy a substring probe and be rejected by the engine.
    """
    runner = _Runner(
        results=[
            CommandResult(
                exit_code=0,
                stdout='{"server": {"scheduler": {"max_concurrent_runs": 10}}}',
                stderr="",
            )
        ]
    )

    result = _port(runner=runner, cwd=tmp_path).settings(timeout_seconds=30.0)

    assert runner.argvs == [["/opt/fabro", _VERB_NAME, "--json", "--server", _SERVER]]
    assert _ceiling_of(payload=result.payload) == _HP_CEILING


def test_a_non_zero_settings_exit_reports_no_ceiling_rather_than_a_zero(
    tmp_path: Path,
) -> None:
    """A server that refused the read has not reported a ceiling of nothing."""
    runner = _Runner(results=[CommandResult(exit_code=1, stdout="", stderr="refused")])

    result = _port(runner=runner, cwd=tmp_path).settings(timeout_seconds=30.0)

    assert result.payload is None
    assert _ceiling_of(payload=result.payload) is None


def test_both_measured_scheduler_nestings_report_the_same_ceiling() -> None:
    """The two observed spellings of one figure read identically.

    `server.scheduler` is the spelling the ratifying revision named;
    `server.server.scheduler` is the one the retention spike measured. A reader
    correct for one and blind to the other returns `None` on the other build,
    which silently reports every candidate as having no free slot.
    """
    shallow: dict[str, Any] = {"server": {"scheduler": {"max_concurrent_runs": _PETRI_CEILING}}}
    deep: dict[str, Any] = {
        "server": {"server": {"scheduler": {"max_concurrent_runs": _PETRI_CEILING}}}
    }

    assert _ceiling_of(payload=shallow) == _PETRI_CEILING
    assert _ceiling_of(payload=deep) == _PETRI_CEILING


def test_a_payload_naming_no_usable_ceiling_reports_none() -> None:
    """Every shape that answers nothing answers `None`, never a number.

    `True` is in the list because `bool` is a subclass of `int` in Python, so an
    `isinstance(value, int)` test accepts it and a ceiling of `True` would read
    as a server that admits exactly one run. A ceiling of `0` is in it for the
    opposite reason: the clause calls a `max_concurrent_runs` below 1 no free
    slot, so a zero is a REPORTED figure and must survive the parse as one
    rather than be flattened into the unanswered case here.
    """
    unusable: tuple[object, ...] = (
        None,
        [],
        {},
        {"server": {}},
        {"server": {"scheduler": []}},
        {"server": {"scheduler": {"max_concurrent_runs": "10"}}},
        {"server": {"scheduler": {"max_concurrent_runs": True}}},
        {"max_concurrent_runs": 10},
    )

    assert [_ceiling_of(payload=one) for one in unusable] == [None for _ in unusable]
    assert _ceiling_of(payload={"server": {"scheduler": {"max_concurrent_runs": 0}}}) == 0
