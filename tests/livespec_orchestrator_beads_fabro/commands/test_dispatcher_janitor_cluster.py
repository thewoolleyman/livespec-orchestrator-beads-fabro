"""Tests for the post-merge janitor's cluster venue and its verdict reading."""

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_dev_tooling.gate_remote_verdict import GATE_FAILED, GATE_NO_VERDICT, GATE_PASSED
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    CLUSTER_JANITOR_GATE_ARGV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_cluster import (
    CLUSTER_GATE_STAGE,
    CLUSTER_JOB_VENUE,
    HOST_PROCESS_VENUE,
    cluster_janitor_red,
    janitor_runs_on_cluster,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_cluster import (
    GATE_FAILED as VENUE_GATE_FAILED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_cluster import (
    GATE_NO_VERDICT as VENUE_GATE_NO_VERDICT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_cluster import (
    GATE_PASSED as VENUE_GATE_PASSED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
)

_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )


@dataclass(kw_only=True)
class Runner:
    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = env
        assert timeout_seconds > 0
        self.calls.append((argv, cwd))
        return self.queue.pop(0)


@dataclass(kw_only=True)
class Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _merged() -> PrView:
    return PrView(
        number=7,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha="cafe08",
        terminal_required_check_failures=(),
    )


def _gated(*, stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)


def _verdict_line(*, state: str, detail: object) -> str:
    return json.dumps({"state": state, "detail": detail, "event": "delegated gate"})


def _red(*, repo: Path, reply: CommandResult) -> DispatchOutcome | None:
    return cluster_janitor_red(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo),
        runner=Runner(queue=[reply]),
        journal=Journal(),
        merged=_merged(),
    )


def _write_config(*, repo: Path, text: str) -> None:
    _ = (repo / ".livespec.jsonc").write_text(text, encoding="utf-8")


def test_the_three_gate_states_are_the_shared_clients_own_states() -> None:
    """The state words cross a PROCESS boundary, so they are pinned to their source.

    They are spelled as literals in the venue module because the package that
    renders them is not resolvable from a dispatch's interpreter — which is the
    whole reason the gate is invoked rather than imported. A literal that drifted
    from its source would make every verdict unrecognised, and an unrecognised
    verdict reads as a cluster that said nothing, so the drift would present as a
    cluster outage rather than as a typo.
    """
    assert VENUE_GATE_PASSED == GATE_PASSED
    assert VENUE_GATE_FAILED == GATE_FAILED
    assert VENUE_GATE_NO_VERDICT == GATE_NO_VERDICT


def test_the_gate_argv_names_an_entry_point_that_is_actually_importable() -> None:
    """The invoked module must EXIST, or every cluster janitor reaches no verdict.

    Asserted by import rather than by string comparison against the constant:
    comparing the constant with itself passes for any spelling, including one
    naming a module the shared package does not publish.
    """
    entry_point = importlib.import_module(CLUSTER_JANITOR_GATE_ARGV[-2])

    assert CLUSTER_JANITOR_GATE_ARGV[-1] == "run"
    assert callable(entry_point.main)


@pytest.mark.parametrize(
    "config_text",
    [
        pytest.param(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
            '{"janitor_gate_venue": "host_process"}}}',
            id="declared-host-process",
        ),
        pytest.param(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
            '{"janitor_gate_venue": "k8s"}}}',
            id="unrecognised-value",
        ),
        pytest.param(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"janitor_gate_venue": true}}}',
            id="wrong-type",
        ),
        pytest.param('{"livespec-orchestrator-beads-fabro": {}}', id="absent-key"),
        pytest.param("{not jsonc at all", id="unparseable-config"),
    ],
)
def test_every_doubt_about_the_venue_keeps_the_host_local_check_suite(
    tmp_path: Path, config_text: str
) -> None:
    """OFF is the strict path, so only the literal opt-in reaches the cluster.

    The unparseable case is the one worth keeping: a repository whose
    configuration cannot be read is one that should run its checks where it
    always did, not one whose every merge turns red on a cluster nobody
    established it can reach.
    """
    _write_config(repo=tmp_path, text=config_text)

    assert janitor_runs_on_cluster(cwd=tmp_path) is False


def test_the_declared_cluster_venue_is_the_one_value_that_selects_it(tmp_path: Path) -> None:
    """The positive control: without it every case above passes on a dead switch."""
    _write_config(
        repo=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
            f'{{"janitor_gate_venue": "{CLUSTER_JOB_VENUE}"}}}}}}'
        ),
    )

    assert janitor_runs_on_cluster(cwd=tmp_path) is True


def test_the_two_venue_names_are_distinct_and_say_what_they_are() -> None:
    """Neither value ranks a tier; each names the machine its checks run on."""
    assert {HOST_PROCESS_VENUE, CLUSTER_JOB_VENUE} == {"host_process", "cluster_job"}


def test_a_passed_verdict_is_green_even_when_the_gate_itself_exits_non_zero(
    tmp_path: Path,
) -> None:
    """The exit code is the PUSH's answer, and this janitor is making no push.

    A gate that passed but could not write the push-specific green token exits
    non-zero while its verdict stands, so reading the code would turn a gated,
    green merge red on a fact about a push nobody attempted.
    """
    outcome = _red(
        repo=tmp_path,
        reply=_gated(
            exit_code=1,
            stderr=_verdict_line(state=GATE_PASSED, detail="the gate passed on tree cafe08"),
        ),
    )

    assert outcome is None


def test_the_gate_runs_in_the_janitor_checkout_under_its_own_journal_stage(
    tmp_path: Path,
) -> None:
    """The stage is distinct from the host-local one, which is how a reader tells them apart."""
    plan = _plan(repo=tmp_path)
    runner = Runner(
        queue=[_gated(stderr=_verdict_line(state=GATE_PASSED, detail="passed"))],
    )
    journal = Journal()

    outcome = cluster_janitor_red(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert outcome is None
    assert [record["stage"] for record in journal.records] == [CLUSTER_GATE_STAGE]
    assert runner.calls == [(list(CLUSTER_JANITOR_GATE_ARGV), plan.janitor_checkout)]


def test_a_verdict_on_stdout_is_read_as_readily_as_one_on_stderr(tmp_path: Path) -> None:
    """Both streams are searched, because which one carries it is not ours to fix."""
    outcome = _red(
        repo=tmp_path,
        reply=_gated(stdout=_verdict_line(state=GATE_FAILED, detail="the Job ended Failed")),
    )

    assert outcome is not None
    assert "the Job ended Failed" in outcome.detail


def test_the_last_recognised_verdict_line_wins_over_earlier_lookalikes(tmp_path: Path) -> None:
    """The gate streams the pod's own logs BEFORE rendering its verdict.

    So a reader taking the first recognised line would grade this merge on
    whatever an earlier gate's output happened to say — which is exactly what a
    replay or a `cat` of a prior record puts on that stream.
    """
    earlier = _verdict_line(state=GATE_PASSED, detail="a verdict from some earlier run")
    outcome = _red(
        repo=tmp_path,
        reply=_gated(
            stderr="\n".join(
                (
                    earlier,
                    "a pod log line that is not structured at all",
                    "[1, 2, 3]",
                    json.dumps({"event": "no state here"}),
                    json.dumps({"state": "MAYBE", "detail": "not one of the three"}),
                    _verdict_line(state=GATE_FAILED, detail="check-types went red"),
                )
            )
        ),
    )

    assert outcome is not None
    assert "check-types went red" in outcome.detail
    assert "some earlier run" not in outcome.detail


def test_structured_lines_after_the_verdict_are_skipped_rather_than_read_as_one(
    tmp_path: Path,
) -> None:
    """Being LAST on the stream is not what makes a line a verdict.

    The gate's own cleanup — the ref deletion, and whatever the cluster client
    prints on its way out — can put further structured output below the verdict,
    so a reader that simply took the last JSON object it could parse would grade
    the merge on a line the gate never meant as an answer.
    """
    outcome = _red(
        repo=tmp_path,
        reply=_gated(
            stderr="\n".join(
                (
                    _verdict_line(state=GATE_FAILED, detail="check-lint went red"),
                    json.dumps({"event": "deleting the gate ref", "level": "info"}),
                    json.dumps({"state": "Complete", "detail": "a Job condition, not a verdict"}),
                )
            )
        ),
    )

    assert outcome is not None
    assert "check-lint went red" in outcome.detail


def test_a_recognised_verdict_with_no_readable_detail_still_reports_its_state(
    tmp_path: Path,
) -> None:
    """A detail of the wrong type is a missing detail, never a missing verdict."""
    outcome = _red(
        repo=tmp_path,
        reply=_gated(stderr=_verdict_line(state=GATE_FAILED, detail=17)),
    )

    assert outcome is not None
    assert "the gate gave no detail" in outcome.detail


def test_output_carrying_no_verdict_line_at_all_is_red_at_the_cluster_stage(
    tmp_path: Path,
) -> None:
    """An invocation that rendered nothing readable reached no verdict.

    This is the arm a missing entry point, a killed process and a truncated
    stream all land on, and it must never be green: the merged tree was not
    gated by anything.
    """
    outcome = _red(repo=tmp_path, reply=_gated(exit_code=127, stderr="No module named whatever"))

    assert outcome is not None
    assert (outcome.status, outcome.stage) == ("failed", CLUSTER_GATE_STAGE)
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe08")
    assert "no verdict" in outcome.detail
