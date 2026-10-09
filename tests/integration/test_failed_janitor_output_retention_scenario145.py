"""Scenario 145 — a failed post-merge janitor retains its complete output.

Top-of-pyramid coverage for the failed-post-merge-janitor output-retention
clause of `SPECIFICATION/contracts.md`. The janitor command here is a REAL
child process, because the whole claim under test is about what the runner
captured from one: it writes distinct stdout and stderr, each far longer than
the journal row's bounded excerpt, puts its assertion marker at the HEAD of
each stream — where a tail of the last 2,000 characters structurally cannot
reach it — and exits with a distinctive non-zero code. So the control is real:
the row's excerpt cannot show the marker and the retained artifact must.

The git and provisioning stages around it are canned, since none of them is the
subject; the janitor argv alone is handed to the production `ShellCommandRunner`
and the journal is a real `JournalFile` whose records are read back off disk.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import stat
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_output_retention import (
    JanitorRetention,
    janitor_retention,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
)

# The two REQUIRED contract fields, without which the post-merge flow degrades
# before the janitor is ever reached.
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'

# The identity the retained artifact's path is keyed on.
_INVOCATION = "d15fa7c4"

# The one covered stage these cases drive.
_JANITOR_STAGE = "janitor-post-merge"

# Printed FIRST on each stream, so the journal row's trailing excerpt cannot
# carry it. Finding either marker in a row would mean the excerpt is not
# bounded the way this test assumes, which would void the control.
_STDOUT_MARKER = "RETENTION-ASSERTION-MARKER-ON-STDOUT"
_STDERR_MARKER = "RETENTION-ASSERTION-MARKER-ON-STDERR"

# Each loop emits ~26 characters per line, so ~7,800 characters per stream —
# comfortably past the 2,000-character excerpt bound.
_LINES = 300
_EXIT_CODE = 42

_CHILD_SCRIPT = (
    f'printf "%s\\n" "{_STDOUT_MARKER}"; '
    f'printf "%s\\n" "{_STDERR_MARKER}" >&2; '
    f"i=0; while [ $i -lt {_LINES} ]; do i=$((i+1)); "
    'printf "out-line-%s-aaaaaaaaaa\\n" "$i"; '
    'printf "err-line-%s-bbbbbbbbbb\\n" "$i" >&2; done; '
    f"exit {_EXIT_CODE}"
)
_JANITOR_ARGV: tuple[str, ...] = ("sh", "-c", _CHILD_SCRIPT)

_SUCCESS_STDOUT = "post-merge janitor green"
_SUCCESS_STDERR = ""
_SUCCESS_JANITOR_ARGV: tuple[str, ...] = (
    "sh",
    "-c",
    f'printf "%s\\n" "{_SUCCESS_STDOUT}"; exit 0',
)

# pull-primary, the venue's merge-containment probe, the preclean, and the five
# provisioning steps. The janitor argv itself is never taken from this queue.
_CANNED_STAGES_BEFORE_JANITOR = 8


def test_run_stage_groups_its_journaling_policy() -> None:
    """Row-stream and artifact choices cross the stage boundary as one policy."""
    parameters = inspect.signature(run_stage).parameters
    assert "streams" not in parameters
    assert "retention" not in parameters


@dataclass(kw_only=True)
class _JanitorChildRunner:
    """Canned results for every stage except the janitor, which runs for real."""

    shell: ShellCommandRunner = field(default_factory=ShellCommandRunner)
    canned: list[CommandResult] = field(default_factory=list)
    # Recorded so a retention-blocked run can be compared, call for call,
    # against a control run that performed no retention at all.
    calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append((tuple(argv), env))
        if tuple(argv) in {_JANITOR_ARGV, _SUCCESS_JANITOR_ARGV}:
            return self.shell.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
        return self.canned.pop(0)


def _canned_runner(*, after_janitor: int = 0) -> _JanitorChildRunner:
    canned = [CommandResult(exit_code=0, stdout="", stderr="")] * (
        _CANNED_STAGES_BEFORE_JANITOR + after_janitor
    )
    return _JanitorChildRunner(canned=list(canned))


def _merged() -> PrView:
    return PrView(
        number=2601,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha="cafe08",
        terminal_required_check_failures=(),
    )


def _plan(
    *, repo: Path, retention: JanitorRetention | None, janitor: tuple[str, ...] = _JANITOR_ARGV
) -> DispatchPlan:
    checkout = repo / "janitor-co"
    checkout.mkdir(parents=True, exist_ok=True)
    plan = build_plan(
        repo=repo,
        work_item_id="bd-ib-nezrrh",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=janitor,
        janitor_checkout=checkout,
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )
    return replace(plan, janitor_retention=retention)


def _journal(*, repo: Path) -> JournalFile:
    return JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")


def _rows(*, journal: JournalFile, stage: str) -> list[dict[str, object]]:
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    return [record for record in records if record.get("stage") == stage]


@dataclass(frozen=True, kw_only=True)
class _Drive:
    """One post-merge janitor run, with everything a comparison needs off it."""

    outcome: DispatchOutcome
    row: dict[str, object]
    calls: list[tuple[tuple[str, ...], dict[str, str] | None]]
    umask: int


def _umask() -> int:
    """The process umask, read by setting and restoring it.

    `os.umask` has no read-only form. The window is one call wide and inside a
    single pytest worker process, which runs its tests one at a time.
    """
    current = os.umask(0o022)
    _ = os.umask(current)
    return current


def _drive(
    *,
    repo: Path,
    journal: JournalFile,
    retention: JanitorRetention | None,
    janitor: tuple[str, ...] = _JANITOR_ARGV,
    canned_after_janitor: int = 0,
) -> _Drive:
    runner = _canned_runner(after_janitor=canned_after_janitor)
    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo, retention=retention, janitor=janitor),
        runner=runner,
        journal=journal,
        merged=_merged(),
    )
    return _Drive(
        outcome=outcome,
        row=_rows(journal=journal, stage=_JANITOR_STAGE)[-1],
        calls=runner.calls,
        umask=_umask(),
    )


def _run_janitor(*, repo: Path, journal: JournalFile) -> DispatchOutcome:
    return _drive(
        repo=repo,
        journal=journal,
        retention=janitor_retention(directory=journal.path.parent, invocation=_INVOCATION),
    ).outcome


def test_a_failed_post_merge_janitor_retains_its_complete_output_and_exit_code(
    *, tmp_path: Path
) -> None:
    """The artifact carries both complete streams and the exit code; the row names it.

    The FIRST assertion is deliberately about the dispatch plan's own shape
    rather than about behaviour, for the same reason the new-module pattern
    asserts a module's path before importing it: until the retention venue is a
    field of the resolved plan, the `replace()` inside `_plan` raises TypeError
    and NO assertion in this test would run at all.
    """
    assert "janitor_retention" in {plan_field.name for plan_field in fields(DispatchPlan)}

    journal = _journal(repo=tmp_path)
    outcome = _run_janitor(repo=tmp_path, journal=journal)

    assert (outcome.status, outcome.stage) == ("failed", "janitor-post-merge"), outcome.detail

    rows = _rows(journal=journal, stage="janitor-post-merge")
    assert len(rows) == 1
    row = rows[0]

    # The excerpt is untouched and, being a tail, cannot carry either marker —
    # which is precisely why the artifact has to exist.
    excerpt = row["detail"]
    assert isinstance(excerpt, str)
    assert "err-line-" in excerpt
    assert _STDERR_MARKER not in excerpt
    assert _STDOUT_MARKER not in excerpt

    artifact = Path(str(row["retained_output_path"]))
    assert artifact.is_file()
    # Private to the invocation, and OUTSIDE the disposable janitor checkout
    # whose removal it is written to survive.
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    assert artifact.is_relative_to(journal.path.parent)
    assert not artifact.is_relative_to(tmp_path / "janitor-co")
    assert _INVOCATION in artifact.name
    assert "janitor-post-merge" in artifact.name

    payload_bytes = artifact.read_bytes()
    assert row["retained_output_sha256"] == hashlib.sha256(payload_bytes).hexdigest()

    retained = json.loads(payload_bytes)
    assert retained["exit_code"] == _EXIT_CODE
    assert retained["stdout"].startswith(f"{_STDOUT_MARKER}\n")
    assert retained["stderr"].startswith(f"{_STDERR_MARKER}\n")
    assert retained["stdout"].count("out-line-") == _LINES
    assert retained["stderr"].count("err-line-") == _LINES
    assert len(retained["stdout"]) > len(excerpt)
    assert len(retained["stderr"]) > len(excerpt)


def test_a_second_failure_of_one_stage_retains_a_second_artifact(*, tmp_path: Path) -> None:
    """Two failures of one stage in one invocation retain two artifacts, each named by its row.

    The path is asserted NOT to be keyed on the invocation and stage alone
    BEFORE the second run, because at Red that is exactly what it is keyed on:
    the second retention cannot produce an artifact at all, since the name it
    would use already exists on disk.
    """
    journal = _journal(repo=tmp_path)
    first_outcome = _run_janitor(repo=tmp_path, journal=journal)
    assert (first_outcome.status, first_outcome.stage) == ("failed", _JANITOR_STAGE)

    first_rows = _rows(journal=journal, stage=_JANITOR_STAGE)
    assert len(first_rows) == 1
    first_artifact = Path(str(first_rows[0]["retained_output_path"]))
    first_bytes = first_artifact.read_bytes()
    assert first_artifact.name != f"{_INVOCATION}-{_JANITOR_STAGE}.json"

    second_outcome = _run_janitor(repo=tmp_path, journal=journal)
    assert (second_outcome.status, second_outcome.stage) == ("failed", _JANITOR_STAGE)

    rows = _rows(journal=journal, stage=_JANITOR_STAGE)
    assert len(rows) == 2
    paths = [Path(str(row["retained_output_path"])) for row in rows]
    assert paths[0] != paths[1]
    assert all(path.is_file() for path in paths)
    # The first artifact is what it was: a retention adds evidence, never
    # replaces it, and a retry is the occasion where both copies matter.
    assert first_artifact.read_bytes() == first_bytes
    # Each row names ITS OWN artifact, so neither digest describes the other's
    # bytes by accident — which two identical payloads would otherwise hide.
    for row, path in zip(rows, paths, strict=True):
        assert row["retained_output_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_retention_write_failure_is_journaled_and_changes_nothing_else(*, tmp_path: Path) -> None:
    """An unwritable artifact location becomes a reason on the row and nothing more.

    The CONTROL is the same drive with no retention venue at all, which is
    exactly "what it would be without retention": every claim about the
    command and the verdict is read as EQUALITY against that run rather than
    against literals written here, so a drift in either leg is what fails.

    At Red the retention-blocked leg does not reach a verdict at all — the
    write error escapes `post_merge` — which is the failure this assertion
    forbids in its sharpest form.
    """
    umask_before = _umask()
    journal = _journal(repo=tmp_path)

    # BOTH legs run in the SAME repository, so the only difference between them
    # is the retention venue. Two repositories would differ in every path the
    # recorded argvs carry, which is the one comparison this case rests on.
    control = _drive(repo=tmp_path, journal=journal, retention=None)

    # A regular FILE where the retention directory must be, so the artifact
    # cannot be written for a reason that has nothing to do with the command.
    unwritable = tmp_path / "not-a-directory"
    unwritable.write_text("retention cannot descend into a file\n", encoding="utf-8")
    blocked = _drive(
        repo=tmp_path,
        journal=journal,
        retention=janitor_retention(directory=unwritable, invocation=_INVOCATION),
    )

    # The row SAYS the artifact was not retained, and names why.
    reason = blocked.row["retained_output_error"]
    assert isinstance(reason, str)
    assert reason != ""
    assert "retained_output_path" not in blocked.row
    assert "retained_output_sha256" not in blocked.row
    assert "retained_output_error" not in control.row

    # The verdict is unchanged.
    assert (blocked.outcome.status, blocked.outcome.stage) == (
        control.outcome.status,
        control.outcome.stage,
    )
    assert blocked.outcome.stage == _JANITOR_STAGE

    # So are the command's argv, its environment and its exit code, plus the
    # row's own bounded excerpt — and the process umask, which retention
    # reaches the artifact's mode without touching.
    assert blocked.calls == control.calls
    assert blocked.row["exit_code"] == control.row["exit_code"] == _EXIT_CODE
    assert blocked.row["detail"] == control.row["detail"]
    assert blocked.umask == control.umask == umask_before


def test_a_green_janitor_retains_only_its_existing_journal_tail(*, tmp_path: Path) -> None:
    """A zero-exit janitor creates no private artifact and keeps today's row."""
    journal = _journal(repo=tmp_path)
    drive = _drive(
        repo=tmp_path,
        journal=journal,
        retention=janitor_retention(directory=journal.path.parent, invocation=_INVOCATION),
        janitor=_SUCCESS_JANITOR_ARGV,
        canned_after_janitor=1,
    )

    assert (drive.outcome.status, drive.outcome.stage) == ("green", "done")
    assert drive.row["exit_code"] == 0
    assert drive.row["detail"] == _SUCCESS_STDOUT
    assert drive.row.get("stderr", "") == _SUCCESS_STDERR

    artifact_directory = journal.path.parent / "janitor-failed-output"
    assert not artifact_directory.exists()
    assert "retained_output_path" not in drive.row
    assert "retained_output_sha256" not in drive.row
    assert "retained_output_error" not in drive.row


def test_an_invocation_without_an_identity_resolves_no_retention_venue(*, tmp_path: Path) -> None:
    """No minted identity means no venue — never a venue keyed on something else."""
    assert janitor_retention(directory=tmp_path, invocation=None) is None
    assert janitor_retention(directory=tmp_path, invocation=_INVOCATION) is not None
