"""Scenarios 190 and 191 — where the janitor's check suite runs, and what its row says.

Binds `SPECIFICATION/scenarios.md` Scenario 190 and Scenario 191, and the
`SPECIFICATION/contracts.md` subsection they exercise, "Post-merge janitor
check-suite venue".

THE ROW IS THE SUBJECT, AND IT IS A SUBJECT BECAUSE TWO SESSIONS HAD TO WORK
AROUND ITS ABSENCE. The cluster venue shipped in v0.210.0 while the
`janitor-post-merge` journal row kept carrying only `at`, `detail`, `exit_code`,
`invoker`, `invoker_source`, `removed_env_vars`, `stage` and `work_item_id` --
nothing saying which machine ran the suite or what the gate reported. One
session inferred `PASSED` from the gate Job's own status in the cluster's
`gates` namespace plus the venue code's rule that only `PASSED` reads green;
another rested its cluster-venue claim on a canary worktree's `.livespec.jsonc`
and the stage's timing. Both readings were correct and neither was available to
a reader of the journal, which is what these cases are about: a cluster run
must be tellable from a host-local one, and a cluster `PASSED` from an inferred
one, FROM THE ROW ALONE.

THE FLOW IS DRIVEN, NOT RESTATED. Every case runs the production `post_merge`
over a real on-disk `JournalFile` and reads the row back off that file, because
the row is what the clause is about and a projection asserted in isolation
would pass just as well while nothing wrote it into the record an operator
reads. The venue is taken from a real `.livespec.jsonc` on disk, which is where
`janitor_runs_on_the_cluster` reads it from, so no argument of this module can
put a venue into the flow.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_check_venue import (
    CLUSTER_GATE_ARGV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import PrView, build_plan

_JANITOR_STAGE = "janitor-post-merge"

# The row fields under test, spelled as LITERALS rather than imported from the
# production projection. A case that named the field set it is grading could
# not tell a projection missing a field from one that never claimed it.
_VENUE_FIELD = "venue"
_GATE_STATE_FIELD = "gate_state"

# The two venue words, likewise spelled out: these are the values an operator
# reads, so a rename is a diff a reviewer sees rather than a constant that
# followed the code.
_CLUSTER_JOB = "cluster_job"
_HOST_LOCAL = "host_local"

# The host-local venue's check suite. A command, not a stand-in: it is handed to
# the plan as the repository's own declaration and the runner keys on it, so a
# case can assert that it ran or that it did not.
_HOST_SUITE: tuple[str, ...] = ("sh", "-c", "exit 0")


def _config_text(*, venue: str | None) -> str:
    """A governed repository's declaration, carrying the venue under test.

    `compat.pinned` is one of the contract's REQUIRED fields: without it the
    post-merge flow degrades at provisioning and never reaches the check suite,
    so every case here would pass for the wrong reason.
    """
    janitor: dict[str, object] = {} if venue is None else {"venue": venue}
    return json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "compat": {"pinned": "master"},
                "dispatcher": {"janitor": {**janitor, "check_suite": list(_HOST_SUITE)}},
            }
        }
    )


@dataclass(kw_only=True)
class _VenueRunner:
    """Canned for every stage but the check suite, keyed on ARGV, not on call order.

    Keying on argv is what lets a case assert that a command was NOT run, and it
    keeps this module from encoding the post-merge flow's own stage sequence --
    which is not the subject here, and whose drift would fail these cases for a
    reason that has nothing to do with the venue.

    The CHECK SUITE answers whatever the case hands it, which is how one fixture
    stands in for a gate client that passed, one that failed, one that printed
    its state on the wrong stream, and one that decided nothing.
    """

    suite: CommandResult
    check_suite: tuple[str, ...]
    calls: list[list[str]] = field(default_factory=list)
    envs: list[Mapping[str, str | None] | None] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert cwd.exists()
        self.calls.append(list(argv))
        self.envs.append(env)
        if self._is_check_suite(argv=argv):
            return self.suite
        return CommandResult(exit_code=0, stdout="", stderr="")

    def _is_check_suite(self, *, argv: list[str]) -> bool:
        """Whichever command the resolved venue runs as its check suite."""
        return tuple(argv) in {tuple(CLUSTER_GATE_ARGV), self.check_suite}


@dataclass(frozen=True, kw_only=True)
class _Drive:
    """One post-merge janitor run, with everything an assertion needs off it."""

    outcome: DispatchOutcome
    row: dict[str, object]
    checkout: Path
    calls: list[list[str]]


def _merged() -> PrView:
    return PrView(
        number=3171,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha="0766415e",
        terminal_required_check_failures=(),
    )


def _gate(*, state: str) -> CommandResult:
    """What the delegated-gate client reports on its own JSON log line.

    `exit_code` follows that client's PUSH-oriented contract -- 0 only when the
    gate passed AND its green token was written -- which the janitor
    deliberately does not read.
    """
    return CommandResult(
        exit_code=0 if state == "PASSED" else 1,
        stdout="",
        stderr=json.dumps({"event": "delegated gate", "state": state}),
    )


def _gate_announcing_on_stdout(*, state: str) -> CommandResult:
    """A gate client that printed its state on the stream the verdict is NOT read from.

    The ratified reading is the last STANDARD-ERROR line carrying a string
    `state`, and the client's standard output is explicitly not read for it. A
    build that scanned both streams would report this as a verdict.
    """
    return CommandResult(
        exit_code=0, stdout=json.dumps({"event": "delegated gate", "state": state}), stderr=""
    )


def _gate_whose_state_is_not_a_word() -> CommandResult:
    """A JSON line carrying a `state` that is not a string, so it is not a verdict line.

    The selection rule asks for a JSON object carrying a STRING `state`, which
    is the part a reader keying merely on the key's presence would drop.
    """
    return CommandResult(
        exit_code=1, stdout="", stderr=json.dumps({"event": "delegated gate", "state": 3})
    )


def _gate_without_a_verdict() -> CommandResult:
    """A gate client that decided nothing: a traceback, and no state-bearing line at all."""
    return CommandResult(
        exit_code=1,
        stdout="",
        stderr="Traceback (most recent call last):\nModuleNotFoundError: no module named any\n",
    )


def _green() -> CommandResult:
    """A host-local check suite that passed: on that venue the exit code IS the verdict."""
    return CommandResult(exit_code=0, stdout="every target green", stderr="")


def _drive(*, tmp_path: Path, name: str, venue: str | None, suite: CommandResult) -> _Drive:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    config_text = _config_text(venue=venue)
    _ = (repo / ".livespec.jsonc").write_text(config_text, encoding="utf-8")
    checkout = repo / "janitor-co"
    checkout.mkdir(parents=True, exist_ok=True)
    plan = build_plan(
        repo=repo,
        work_item_id="bd-ib-nsrgxl",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=checkout,
        config_text=config_text,
        default_branch="master",
    )
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    runner = _VenueRunner(suite=suite, check_suite=tuple(plan.janitor))
    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    rows = [record for record in records if record.get("stage") == _JANITOR_STAGE]
    return _Drive(outcome=outcome, row=rows[-1], checkout=checkout, calls=runner.calls)


def test_scenario191_the_row_names_the_venue_the_suite_was_resolved_to_and_attempted_in(
    tmp_path: Path,
) -> None:
    """The row names the RESOLVED venue, never the raw declaration.

    Three declarations, one assertion each, and the third is the load-bearing
    one. A build that echoed `dispatcher.janitor.venue` onto the row would
    satisfy the first two exactly as a correct one does -- `cluster_job` and an
    absent key both resolve to the word they are spelled with -- and would then
    report `cluster` for a repository whose suite ran on the dispatching host.
    The selection rule resolves every doubtful declaration to `host_local`, so
    the row's job is to say where the suite really ran.

    The rows are read with `get`, so an ABSENT field and a present one carrying
    the wrong word are different readings rather than one `KeyError`.
    """
    cluster = _drive(
        tmp_path=tmp_path, name="cluster", venue=_CLUSTER_JOB, suite=_gate(state="PASSED")
    )
    host = _drive(tmp_path=tmp_path, name="host", venue=None, suite=_green())
    misdeclared = _drive(tmp_path=tmp_path, name="misdeclared", venue="cluster", suite=_green())

    assert cluster.row.get(_VENUE_FIELD) == _CLUSTER_JOB
    assert host.row.get(_VENUE_FIELD) == _HOST_LOCAL
    assert misdeclared.row.get(_VENUE_FIELD) == _HOST_LOCAL
    # Every drive reached the check suite, so each row above is an account of a
    # venue that was really attempted rather than of a flow that degraded first.
    assert [drive.outcome.stage for drive in (cluster, host, misdeclared)] == ["done"] * 3


def test_scenario191_a_cluster_row_carries_the_gate_state_word_and_null_where_there_is_none(
    tmp_path: Path,
) -> None:
    """The row carries the verdict line's state word, and `null` when no line carried one.

    Four readings of ONE field, and the three nulls are what make the first one
    worth anything. A row that simply omitted the field whenever it could not
    read a state would be indistinguishable, to a later reader, from a build
    that predates the field entirely -- which is the position both earlier
    sessions were in. So the field's PRESENCE is asserted separately from its
    value, with `in` rather than `get`.

    The three null arms are the three ways the ratified reading can decline,
    and each one is a different wrong build. A reader scanning both streams
    would call the stdout line a verdict. A reader keying on the `state` key's
    presence rather than on its being a STRING would call `3` a verdict. And a
    reader that simply took the exit code would call the traceback FAILED --
    the one reading the clause forbids outright, because a gate that decided
    nothing is not a red tree.
    """
    passed = _drive(
        tmp_path=tmp_path, name="passed", venue=_CLUSTER_JOB, suite=_gate(state="PASSED")
    )
    on_stdout = _drive(
        tmp_path=tmp_path,
        name="on-stdout",
        venue=_CLUSTER_JOB,
        suite=_gate_announcing_on_stdout(state="PASSED"),
    )
    not_a_word = _drive(
        tmp_path=tmp_path,
        name="not-a-word",
        venue=_CLUSTER_JOB,
        suite=_gate_whose_state_is_not_a_word(),
    )
    silent = _drive(
        tmp_path=tmp_path, name="silent", venue=_CLUSTER_JOB, suite=_gate_without_a_verdict()
    )

    assert passed.row.get(_GATE_STATE_FIELD) == "PASSED"
    for drive in (on_stdout, not_a_word, silent):
        assert _GATE_STATE_FIELD in drive.row
        assert drive.row[_GATE_STATE_FIELD] is None
    # The row's reading and the janitor's own verdict come from one rule, so a
    # row reporting no state sits on a run the flow called red.
    assert passed.outcome.stage == "done"
    assert [drive.outcome.stage for drive in (on_stdout, not_a_word, silent)] == [
        _JANITOR_STAGE
    ] * 3


def test_scenario191_a_host_local_row_carries_no_gate_field_at_all(tmp_path: Path) -> None:
    """On the host-local venue the gate fields are OMITTED, never nulled.

    This is the mirror of the case above and it is why that one asserts
    presence: a `gate_state` of `null` on a host-local row would read as a
    cluster run whose gate said nothing -- the exact conflation the nulls above
    exist to make legible. No gate was asked here, so the row has nothing to
    report about one.
    """
    host = _drive(tmp_path=tmp_path, name="host-no-gate", venue=_HOST_LOCAL, suite=_green())

    assert host.row.get(_VENUE_FIELD) == _HOST_LOCAL
    assert _GATE_STATE_FIELD not in host.row
    assert host.outcome.stage == "done"
