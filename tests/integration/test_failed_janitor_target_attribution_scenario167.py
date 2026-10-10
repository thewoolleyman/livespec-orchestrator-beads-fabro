"""Scenario 167 — a failed janitor names the aggregate runner's failed targets.

The janitor command in these cases is a real child process.  Its structured
summary is deliberately emitted before enough later stdout to push the whole
summary beyond the bounded journal excerpt, while the final stderr line names a
passing recipe.  The git and provisioning commands around it are canned: the
claim under test begins only once the aggregate command runs.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass, field, replace
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

_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'
_INVOCATION = "scenario167-dispatch"
_JANITOR_STAGE = "janitor-post-merge"
_EXIT_CODE = 47
_PASSING_RECIPE = "check-spec-governance-default-block.py"
_CANNED_STAGES_BEFORE_JANITOR = 8


@dataclass(kw_only=True)
class _JanitorRunner:
    janitor: tuple[str, ...]
    shell: ShellCommandRunner = field(default_factory=ShellCommandRunner)
    canned: list[CommandResult] = field(
        default_factory=lambda: [CommandResult(exit_code=0, stdout="", stderr="")]
        * _CANNED_STAGES_BEFORE_JANITOR
    )

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        if tuple(argv) == self.janitor:
            return self.shell.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
        return self.canned.pop(0)


def _janitor_argv(*, targets: tuple[str, ...]) -> tuple[str, ...]:
    summary = "\n".join(
        [f"Failed targets ({len(targets)}):", *(f"  - {target}" for target in targets)]
    )
    script = (
        f"printf '%s\\n' {shlex.quote(summary)}; "
        "i=0; while [ $i -lt 300 ]; do i=$((i+1)); "
        "printf 'later-stdout-%s-xxxxxxxxxx\\n' \"$i\"; done; "
        f"printf '::: just %s\\n' {shlex.quote(_PASSING_RECIPE)} >&2; "
        f"exit {_EXIT_CODE}"
    )
    return ("sh", "-c", script)


def _unstructured_janitor_argv() -> tuple[str, ...]:
    script = (
        "i=0; while [ $i -lt 300 ]; do i=$((i+1)); "
        "printf 'stdout-observation-%s-aaaaaaaaaa\\n' \"$i\"; "
        "printf 'stderr-observation-%s-bbbbbbbbbb\\n' \"$i\" >&2; done; "
        f"exit {_EXIT_CODE}"
    )
    return ("sh", "-c", script)


def _nested_summary_janitor_argv(
    *, nested_targets: tuple[str, ...], aggregate_targets: tuple[str, ...]
) -> tuple[str, ...]:
    nested_summary = "\n".join(
        [
            f"Failed targets ({len(nested_targets)}):",
            *(f"  - {target}" for target in nested_targets),
        ]
    )
    aggregate_summary = "\n".join(
        [
            f"Failed targets ({len(aggregate_targets)}):",
            *(f"  - {target}" for target in aggregate_targets),
        ]
    )
    script = (
        f"printf '%s\\n' {shlex.quote(nested_summary)}; "
        "printf 'nested-check-output\\n'; "
        f"printf '%s\\n' {shlex.quote(aggregate_summary)}; "
        f"exit {_EXIT_CODE}"
    )
    return ("sh", "-c", script)


def _stderr_decoy_janitor_argv(
    *, aggregate_targets: tuple[str, ...], decoy_targets: tuple[str, ...]
) -> tuple[str, ...]:
    aggregate_summary = "\n".join(
        [
            f"Failed targets ({len(aggregate_targets)}):",
            *(f"  - {target}" for target in aggregate_targets),
        ]
    )
    decoy_summary = "\n".join(
        [
            f"Failed targets ({len(decoy_targets)}):",
            *(f"  - {target}" for target in decoy_targets),
        ]
    )
    script = (
        f"printf '%s\\n' {shlex.quote(aggregate_summary)}; "
        f"printf '%s\\n' {shlex.quote(decoy_summary)} >&2; "
        f"exit {_EXIT_CODE}"
    )
    return ("sh", "-c", script)


def _plan(
    *,
    repo: Path,
    janitor: tuple[str, ...],
    retention_directory: Path | None = None,
) -> DispatchPlan:
    checkout = repo / "janitor-co"
    checkout.mkdir(parents=True, exist_ok=True)
    plan = build_plan(
        repo=repo,
        work_item_id="bd-ib-ma3fvj",
        workflow_toml=repo / "workflow.fabro",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=janitor,
        janitor_checkout=checkout,
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )
    return replace(
        plan,
        janitor_retention=janitor_retention(
            directory=repo / "tmp" if retention_directory is None else retention_directory,
            invocation=_INVOCATION,
        ),
    )


def _merged() -> PrView:
    return PrView(
        number=2671,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha="face167",
        terminal_required_check_failures=(),
    )


def _janitor_rows(*, journal: JournalFile) -> list[dict[str, object]]:
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    return [record for record in records if record.get("stage") == _JANITOR_STAGE]


def test_every_summarized_failed_target_reaches_both_reports_and_the_log_is_named(
    *, tmp_path: Path
) -> None:
    """A complete over-window summary, not the stderr tail, is the attribution."""
    targets = tuple(f"check-failure-{index:03d}-{'x' * 24}" for index in range(72))
    janitor = _janitor_argv(targets=targets)
    journal = JournalFile(path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl")

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path, janitor=janitor),
        runner=_JanitorRunner(janitor=janitor),
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("failed", _JANITOR_STAGE)
    assert all(target in outcome.detail for target in targets), outcome.detail

    rows = _janitor_rows(journal=journal)
    assert len(rows) == 1
    row = rows[0]
    assert row.get("failed_targets") == list(targets), row
    assert all(target in str(row["detail"]) for target in targets), row["detail"]
    assert row["exit_code"] == _EXIT_CODE

    artifact = Path(str(row["retained_output_path"]))
    payload = artifact.read_bytes()
    assert artifact.is_file()
    assert row["retained_output_sha256"] == hashlib.sha256(payload).hexdigest()
    assert "Failed targets" in str(json.loads(payload)["stdout"])


def test_a_passing_recipe_in_the_stderr_tail_is_not_reported_as_the_cause(
    *, tmp_path: Path
) -> None:
    """A structured summary excludes unrelated recipe output from attribution."""
    targets = ("check-per-file-coverage", "check-coverage")
    janitor = _janitor_argv(targets=targets)
    journal = JournalFile(path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl")

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path, janitor=janitor),
        runner=_JanitorRunner(janitor=janitor),
        journal=journal,
        merged=_merged(),
    )

    row = _janitor_rows(journal=journal)[0]
    assert _PASSING_RECIPE not in outcome.detail, outcome.detail
    assert _PASSING_RECIPE not in str(row["detail"]), row["detail"]
    assert row["failed_targets"] == list(targets)


def test_the_aggregate_terminal_summary_wins_over_a_nested_failed_targets_block(
    *, tmp_path: Path
) -> None:
    """An inner check's summary cannot replace the aggregate runner's own summary."""
    nested_targets = ("nested-check-failure",)
    aggregate_targets = ("check-per-file-coverage", "check-coverage")
    janitor = _nested_summary_janitor_argv(
        nested_targets=nested_targets,
        aggregate_targets=aggregate_targets,
    )
    journal = JournalFile(path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl")

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path, janitor=janitor),
        runner=_JanitorRunner(janitor=janitor),
        journal=journal,
        merged=_merged(),
    )

    row = _janitor_rows(journal=journal)[0]
    assert row["failed_targets"] == list(aggregate_targets)
    assert all(target in outcome.detail for target in aggregate_targets)
    assert all(target not in outcome.detail for target in nested_targets)


def test_the_stdout_aggregate_summary_wins_over_a_stderr_decoy(*, tmp_path: Path) -> None:
    """A target-emitted stderr summary cannot override the aggregate stdout summary."""
    aggregate_targets = ("check-per-file-coverage", "check-coverage")
    decoy_targets = ("nested-stderr-decoy",)
    janitor = _stderr_decoy_janitor_argv(
        aggregate_targets=aggregate_targets,
        decoy_targets=decoy_targets,
    )
    journal = JournalFile(path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl")

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path, janitor=janitor),
        runner=_JanitorRunner(janitor=janitor),
        journal=journal,
        merged=_merged(),
    )

    row = _janitor_rows(journal=journal)[0]
    assert row["failed_targets"] == list(aggregate_targets)
    assert all(target in outcome.detail for target in aggregate_targets)
    assert all(target not in outcome.detail for target in decoy_targets)


def test_without_a_summary_both_bounded_streams_are_labelled_observations(
    *, tmp_path: Path
) -> None:
    """Unstructured output stays observational and the complete artifact stays named."""
    janitor = _unstructured_janitor_argv()
    journal = JournalFile(path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl")

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path, janitor=janitor),
        runner=_JanitorRunner(janitor=janitor),
        journal=journal,
        merged=_merged(),
    )

    row = _janitor_rows(journal=journal)[0]
    for detail in (outcome.detail, str(row["detail"])):
        assert "stdout observation (bounded):" in detail
        assert "stderr observation (bounded):" in detail
        assert "stdout-observation-300" in detail
        assert "stderr-observation-300" in detail
    assert "failed_targets" not in row
    assert Path(str(row["retained_output_path"])).is_file()


def test_retention_failure_preserves_target_attribution_and_the_red_verdict(
    *, tmp_path: Path
) -> None:
    """Artifact-write failure is journaled without erasing the observed summary."""
    targets = ("check-per-file-coverage", "check-coverage")
    janitor = _janitor_argv(targets=targets)
    journal = JournalFile(path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl")
    blocked_directory = tmp_path / "not-a-directory"
    blocked_directory.write_text("retention cannot descend here\n", encoding="utf-8")

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(
            repo=tmp_path,
            janitor=janitor,
            retention_directory=blocked_directory,
        ),
        runner=_JanitorRunner(janitor=janitor),
        journal=journal,
        merged=_merged(),
    )

    row = _janitor_rows(journal=journal)[0]
    assert (outcome.status, outcome.stage) == ("failed", _JANITOR_STAGE)
    assert all(target in outcome.detail for target in targets)
    assert row["failed_targets"] == list(targets)
    assert row["exit_code"] == _EXIT_CODE
    assert isinstance(row.get("retained_output_error"), str)
    assert "retained_output_path" not in row
    assert "retained_output_sha256" not in row
