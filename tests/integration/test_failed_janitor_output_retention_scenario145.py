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
import json
import stat
from dataclasses import dataclass, field, fields, replace
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_output_retention import (
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

# pull-primary, the venue's merge-containment probe, the preclean, and the five
# provisioning steps. The janitor argv itself is never taken from this queue.
_CANNED_STAGES_BEFORE_JANITOR = 8


@dataclass(kw_only=True)
class _JanitorChildRunner:
    """Canned results for every stage except the janitor, which runs for real."""

    shell: ShellCommandRunner = field(default_factory=ShellCommandRunner)
    canned: list[CommandResult] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        if tuple(argv) == _JANITOR_ARGV:
            return self.shell.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
        return self.canned.pop(0)


def _canned_runner() -> _JanitorChildRunner:
    canned = [CommandResult(exit_code=0, stdout="", stderr="")] * _CANNED_STAGES_BEFORE_JANITOR
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


def _plan(*, repo: Path, retention_directory: Path) -> DispatchPlan:
    checkout = repo / "janitor-co"
    checkout.mkdir(parents=True, exist_ok=True)
    plan = build_plan(
        repo=repo,
        work_item_id="bd-ib-nezrrh",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=_JANITOR_ARGV,
        janitor_checkout=checkout,
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )
    return replace(
        plan,
        janitor_retention=janitor_retention(directory=retention_directory, invocation=_INVOCATION),
    )


def _journal(*, repo: Path) -> JournalFile:
    return JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")


def _rows(*, journal: JournalFile, stage: str) -> list[dict[str, object]]:
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    return [record for record in records if record.get("stage") == stage]


def _run_janitor(*, repo: Path, journal: JournalFile) -> DispatchOutcome:
    plan = _plan(repo=repo, retention_directory=journal.path.parent)
    return post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=_canned_runner(),
        journal=journal,
        merged=_merged(),
    )


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


def test_an_invocation_without_an_identity_resolves_no_retention_venue(*, tmp_path: Path) -> None:
    """No minted identity means no venue — never a venue keyed on something else."""
    assert janitor_retention(directory=tmp_path, invocation=None) is None
    assert janitor_retention(directory=tmp_path, invocation=_INVOCATION) is not None
