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
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
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
_GATE_TREE_HASH_FIELD = "gate_tree_hash"
_STARTED_AT_FIELD = "started_at"

# The journal's own append instant, stamped by `JournalFile` on every record.
# It is the OTHER half of the stage's duration, so a case that reads one reads
# both from the same row.
_APPENDED_AT_FIELD = "at"

# The instant format both fields are written in. Parsing with it rather than
# with a tolerant reader is itself an assertion: a value that is not a
# seconds-precision UTC instant raises here instead of comparing oddly.
_INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# The Job identity and timing keys the verdict line MAY carry, which the row
# copies when present and omits when absent.
_JOB_ROW_FIELDS: tuple[str, ...] = (
    "job_name",
    "namespace",
    "job_started_at",
    "job_finished_at",
)

# Every field the row may carry on the CLUSTER venue and must omit on the
# host-local one. Collected so the host-local omission case grades the whole
# gate account rather than whichever field was added last.
_GATE_ROW_FIELDS: tuple[str, ...] = (
    _GATE_STATE_FIELD,
    _GATE_TREE_HASH_FIELD,
    *_JOB_ROW_FIELDS,
)

# A Job name and namespace shaped exactly as the gate client's own convention
# renders them -- `gate-<repository>-<first twelve of the tree hash>` in the
# `gates` namespace -- so a build that DERIVED them rather than copying them
# would produce something very close to these values.
_JOB_NAME = "gate-livespec-orchestrator-beads-fabro-1c5e8de33c1f"
_GATES_NAMESPACE = "gates"

# The substring that identifies the venue's own reading of the tree it is about
# to submit. The runner routes that one command to the production
# `ShellCommandRunner` against the real checkout.
_SUBMITTED_TREE_READ = "rev-parse"

# The two venue words, likewise spelled out: these are the values an operator
# reads, so a rename is a diff a reviewer sees rather than a constant that
# followed the code.
_CLUSTER_JOB = "cluster_job"
_HOST_LOCAL = "host_local"

# The host-local venue's check suite. A command, not a stand-in: it is handed to
# the plan as the repository's own declaration and the runner keys on it, so a
# case can assert that it ran or that it did not.
_HOST_SUITE: tuple[str, ...] = ("sh", "-c", "exit 0")

# The same declaration, slowed down by a known amount. A check suite that
# really takes time is the only way to observe that the start instant was taken
# BEFORE the launch rather than beside the journal append.
_SLEEP_SECONDS = 2
_SLOW_HOST_SUITE: tuple[str, ...] = ("sh", "-c", f"sleep {_SLEEP_SECONDS}")


def _config_text(*, venue: str | None, check_suite: tuple[str, ...]) -> str:
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
                "dispatcher": {"janitor": {**janitor, "check_suite": list(check_suite)}},
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
    its state on the wrong stream, and one that decided nothing. A `suite` of
    `None` means RUN IT, through the production runner -- the only way a case
    can give the stage a command that really takes time.

    The SUBMITTED-TREE READING is not canned at all: it runs for real, through
    the production `ShellCommandRunner`, against the real git checkout the
    fixture built. A canned answer there would turn the tree-hash assertion
    into a reading of this module's own constant, which would hold for any argv
    the venue happened to send.
    """

    suite: CommandResult | None
    check_suite: tuple[str, ...]
    shell: ShellCommandRunner = field(default_factory=ShellCommandRunner)
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
        canned = self.suite if self._is_check_suite(argv=argv) else None
        if canned is not None:
            return canned
        if self._is_check_suite(argv=argv) or _SUBMITTED_TREE_READ in argv:
            return self.shell.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
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


def _gate_naming_its_job(*, state: str, job_fields: dict[str, object]) -> CommandResult:
    """A gate client whose verdict line also reports the Job it ran as.

    The Job keys ride the SAME line as the state word, which is where the
    clause says the row copies them from, so one fixture cannot accidentally
    prove that a row read them off some other line.
    """
    return CommandResult(
        exit_code=0 if state == "PASSED" else 1,
        stdout="",
        stderr=json.dumps({"event": "delegated gate", "state": state, **job_fields}),
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


def _git(*, cwd: Path, argv: tuple[str, ...]) -> str:
    """One git invocation in a fixture checkout, with its identity supplied per call.

    The identity rides every invocation rather than a `git config` of its own,
    because this host may carry no user identity in any scope and a commit
    without one simply fails -- the measured trap behind Scenario 176.
    """
    completed = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Janitor Fixture",
            "-c",
            "user.email=janitor@example.invalid",
            *argv,
        ],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _janitor_checkout(*, repo: Path) -> Path:
    """A REAL git checkout standing in for the merged default-branch tip.

    Real, because the venue reads the tree it is about to submit by asking git
    about this directory's HEAD: a bare `mkdir` would leave that reading
    unobservable rather than wrong, and the case would pass against a build
    that recorded nothing. The provisioning stages are canned, so nothing else
    in the flow would create it.
    """
    checkout = repo / "janitor-co"
    checkout.mkdir(parents=True, exist_ok=True)
    _ = _git(cwd=checkout, argv=("init", "--quiet"))
    _ = (checkout / "merged.txt").write_text(f"the merged tree of {repo.name}\n", encoding="utf-8")
    _ = _git(cwd=checkout, argv=("add", "merged.txt"))
    _ = _git(cwd=checkout, argv=("commit", "--quiet", "-m", "the merged default-branch tip"))
    return checkout


def _head_tree(*, checkout: Path) -> str:
    """The checkout's HEAD tree, measured through a DIFFERENT git invocation.

    `git show -s --format=%T` renders the commit object's own tree field, where
    the venue asks `rev-parse` to resolve `HEAD^{tree}`. Measuring with the
    production argv would be one reading taken twice: it would agree with the
    row for whatever either command happened to answer, a wrong value included.
    """
    return _git(cwd=checkout, argv=("show", "-s", "--format=%T", "HEAD"))


def _head_commit(*, checkout: Path) -> str:
    """The checkout's HEAD commit id: the plausible wrong answer to rule out."""
    return _git(cwd=checkout, argv=("show", "-s", "--format=%H", "HEAD"))


def _elapsed_seconds(*, row: dict[str, object]) -> float:
    """The stage's own duration, read from the row's two instants and nothing else.

    This IS the clause's requirement rather than a convenience: the row has to
    make the stage's duration readable, so the reading is taken exactly as an
    operator would take it.
    """
    started = datetime.strptime(str(row[_STARTED_AT_FIELD]), _INSTANT_FORMAT).replace(
        tzinfo=timezone.utc
    )
    appended = datetime.strptime(str(row[_APPENDED_AT_FIELD]), _INSTANT_FORMAT).replace(
        tzinfo=timezone.utc
    )
    return (appended - started).total_seconds()


def _drive(
    *,
    tmp_path: Path,
    name: str,
    venue: str | None,
    suite: CommandResult | None,
    check_suite: tuple[str, ...] = _HOST_SUITE,
) -> _Drive:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    config_text = _config_text(venue=venue, check_suite=check_suite)
    _ = (repo / ".livespec.jsonc").write_text(config_text, encoding="utf-8")
    checkout = _janitor_checkout(repo=repo)
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
    """On the host-local venue every gate field is OMITTED, never nulled.

    This is the mirror of the state-word case above and it is why that one
    asserts presence: a `gate_state` of `null` on a host-local row would read
    as a cluster run whose gate said nothing -- the exact conflation the nulls
    above exist to make legible. No gate was asked here, so the row has nothing
    to report about one.

    Graded over the WHOLE gate account rather than over one field, so a field
    added to the cluster arm later cannot start leaking onto host-local rows
    unnoticed.
    """
    host = _drive(tmp_path=tmp_path, name="host-no-gate", venue=_HOST_LOCAL, suite=_green())

    assert host.row.get(_VENUE_FIELD) == _HOST_LOCAL
    assert [field_name for field_name in _GATE_ROW_FIELDS if field_name in host.row] == []
    assert host.outcome.stage == "done"


def test_scenario191_a_cluster_row_carries_the_tree_the_gate_was_asked_about(
    tmp_path: Path,
) -> None:
    """The row names the submitted tree -- the checkout's HEAD tree -- even with no Job.

    The expected value is MEASURED off the real checkout through a different
    git invocation than the venue uses, so the assertion compares two readings
    of one repository rather than the row against a constant this module also
    fed the flow.

    Two discriminators carry the case. The row must name the TREE and not
    HEAD's own commit id: both are forty hex characters, both look entirely
    plausible in a journal, and only the tree is what a gate Job's
    `livespec.gate/tree-hash` label holds -- so a row carrying the commit sends
    an operator looking for a Job that cannot exist. And it must be named where
    the gate reached NO verdict, which is the arm an operator needs it in most:
    that is the reading that lets them find, or rule out, a Job for that tree.
    """
    passed = _drive(
        tmp_path=tmp_path, name="tree-passed", venue=_CLUSTER_JOB, suite=_gate(state="PASSED")
    )
    silent = _drive(
        tmp_path=tmp_path, name="tree-silent", venue=_CLUSTER_JOB, suite=_gate_without_a_verdict()
    )
    submitted = _head_tree(checkout=passed.checkout)

    assert len(submitted) == 40
    assert submitted != _head_commit(checkout=passed.checkout)
    assert passed.row.get(_GATE_TREE_HASH_FIELD) == submitted
    assert silent.row.get(_GATE_TREE_HASH_FIELD) == _head_tree(checkout=silent.checkout)
    # The two checkouts hold different trees, so neither row could be carrying
    # the other's reading -- or one value this module supplied to both.
    assert _head_tree(checkout=silent.checkout) != submitted


def test_scenario191_a_cluster_row_copies_only_the_job_keys_the_verdict_line_carries(
    tmp_path: Path,
) -> None:
    """Each Job key present on the verdict line is copied; each absent one is omitted.

    The explicit `null` is the whole reason the clause distinguishes copying
    from reporting. `job_started_at: null` is the gate SAYING the Job it names
    had not started, which is a different fact from a key the line never
    mentioned -- and a projection that dropped falsy values, or that filled
    every declared key with `null`, would collapse the two in opposite
    directions while looking equally well-formed.

    The control is a verdict line naming NO Job at all, against a row that
    carries the submitted tree hash. The gate's own convention is
    `gate-<repository>-<first twelve of the tree hash>` in the `gates`
    namespace, so that row holds every ingredient a derivation would need: if
    the row names no Job there, nothing was derived, which is what the clause
    forbids outright. A derived name is indistinguishable from a reported one
    at the row, and wrong whenever the gate did not actually create that Job.
    """
    reported = _drive(
        tmp_path=tmp_path,
        name="job-reported",
        venue=_CLUSTER_JOB,
        suite=_gate_naming_its_job(
            state="PASSED",
            job_fields={
                "job_name": _JOB_NAME,
                "namespace": _GATES_NAMESPACE,
                "job_started_at": None,
            },
        ),
    )
    unreported = _drive(
        tmp_path=tmp_path, name="job-unreported", venue=_CLUSTER_JOB, suite=_gate(state="PASSED")
    )

    assert reported.row.get("job_name") == _JOB_NAME
    assert reported.row.get("namespace") == _GATES_NAMESPACE
    assert "job_started_at" in reported.row
    assert reported.row["job_started_at"] is None
    assert "job_finished_at" not in reported.row
    assert [name for name in _JOB_ROW_FIELDS if name in unreported.row] == []
    assert unreported.row.get(_GATE_TREE_HASH_FIELD) is not None


def test_scenario191_the_row_carries_the_suites_start_so_the_stage_duration_is_readable(
    tmp_path: Path,
) -> None:
    """The start instant is taken before the launch, so the row's two fields bound the stage.

    The check suite RUNS HERE, through the production runner, and one of the
    two legs really sleeps. That is the only way to observe what the clause
    actually asks for: a canned result returns instantly, so every stamp -- one
    taken before the launch, one taken beside the journal append, one taken at
    the top of the post-merge flow -- would read identically.

    The quick leg is the control, and without it the slow leg proves nothing: a
    duration of two seconds is equally consistent with a start instant taken
    before the launch and with a fixture that simply takes two seconds to do
    anything. The two legs differ only in their declared check suite, so the
    difference between their durations is the sleep.

    Both instants are parsed with the exact seconds-precision UTC format, so a
    value that is not one raises here rather than comparing oddly, and the
    duration is read from the ROW as an operator reads it rather than from any
    clock this module holds.
    """
    slow = _drive(
        tmp_path=tmp_path,
        name="slow",
        venue=_HOST_LOCAL,
        suite=None,
        check_suite=_SLOW_HOST_SUITE,
    )
    quick = _drive(tmp_path=tmp_path, name="quick", venue=_HOST_LOCAL, suite=None)
    cluster = _drive(
        tmp_path=tmp_path, name="started-cluster", venue=_CLUSTER_JOB, suite=_gate(state="PASSED")
    )

    assert [
        drive.row.get(_VENUE_FIELD)
        for drive in (slow, quick, cluster)
        if _STARTED_AT_FIELD not in drive.row
    ] == []
    assert _elapsed_seconds(row=slow.row) >= _SLEEP_SECONDS
    assert _elapsed_seconds(row=quick.row) < _SLEEP_SECONDS
    # Owed on BOTH venues: the field is not part of the gate account, so a
    # cluster row carries it too and parses the same way.
    assert _elapsed_seconds(row=cluster.row) < _SLEEP_SECONDS
    assert (slow.outcome.stage, quick.outcome.stage) == ("done", "done")
