"""Scenario 166: reconcile terminal success separately from run-store loss.

The incident shape is preserved here rather than simplified to a generic failed
run: the engine's conclusion says the worker exited before persisting a terminal
event, while its newest checkpoint records the final successful workflow stage
selecting the configured green exit.  The forge seam then reports the pull
request published from that checkpoint's exact commit.

Every case drives ``run_dispatch`` itself.  Only the engine, forge, and checkout
commands leave the process, so those transports are controlled; terminal
classification, pull-request reconciliation, merge handling, and journaling are
production code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_terminal_publication
from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
    CurrentMergeHold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    DispatchOutcome,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

_RUN_ID = "01PROOFTERMINAL"
_HEAD = "a" * 40
_MERGE_SHA = "c" * 40
_REPOSITORY = "thewoolleyman/proof-repo"
_WORKER_EXIT_MESSAGE = "Worker exited before emitting a terminal run event: exit status: 0"
_REPO_ROOT = Path(__file__).parents[2]
_WORKFLOW = _REPO_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml"
_NATIVE_INSPECT = _REPO_ROOT / "tests/fixtures/fabro_native_inspect/background.json"
_SUCCESSFUL_NODES = (
    "start",
    "dod_gate",
    "implement",
    "implementation_diff",
    "janitor",
    "publish_draft",
    "proof_capture",
    "review",
    "proof_verify",
    # The per-assertion grade of the verified record (v156; bd-ib-kcq6pu). It is
    # on the success route because it is the ONLY route out of a `verified`
    # replay: the clause forbids any edge from `proof_verify` to `pr_refresh` or
    # `pr`, so a green run that skipped it took a path the graph does not carry.
    "proof_grade",
    "pr",
    "pr_route",
    "pr_refresh_head",
    "pr_refresh",
    "verify_pr",
)
_CONFIG = '{"livespec-orchestrator-beads-fabro":{"compat":{"pinned":"master"}}}'


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Launcher:
    stderr: str = _WORKER_EXIT_MESSAGE

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(
                exit_code=1,
                stdout=f"Run: {_RUN_ID}\n",
                stderr=self.stderr,
            ),
            run_id=_RUN_ID,
        )


@dataclass(kw_only=True)
class _Runner:
    plan: DispatchPlan
    inspect_record: dict[str, object] = field(default_factory=dict)
    pr_overrides: dict[str, object] = field(default_factory=dict)
    pr_responses: tuple[dict[str, object], ...] = ()
    pr_available: bool = True
    repository_slug: str = _REPOSITORY
    repository_exit_code: int = 0
    repository_stdout: str | None = None
    calls: list[tuple[list[str], Path]] = field(default_factory=list)
    pr_view_count: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (timeout_seconds, env, stdin)
        self.calls.append((argv, cwd))
        if argv[:2] == ["synthetic-fabro", "inspect"]:
            return _ok(stdout=json.dumps([self.inspect_record]))
        if argv[:3] == ["gh", "repo", "view"]:
            return CommandResult(
                exit_code=self.repository_exit_code,
                stdout=(
                    json.dumps({"nameWithOwner": self.repository_slug})
                    if self.repository_stdout is None
                    else self.repository_stdout
                ),
                stderr="repository unavailable" if self.repository_exit_code else "",
            )
        if argv[:3] == ["gh", "pr", "view"]:
            if not self.pr_available:
                return CommandResult(exit_code=1, stdout="", stderr="not found")
            response = (
                self.pr_responses[min(self.pr_view_count, len(self.pr_responses) - 1)]
                if self.pr_responses
                else self.pr_overrides
            )
            self.pr_view_count += 1
            return _ok(
                stdout=json.dumps(
                    {
                        **_pull_request(plan=self.plan),
                        **response,
                    }
                )
            )
        if argv[:2] == ["gh", "api"]:
            return _ok(stdout=json.dumps([{"number": 41}]))
        return _ok()


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _held_merge(*, repo: Path, work_item_id: str) -> CurrentMergeHold:
    _ = (repo, work_item_id)
    return "held"


def _plan(*, root: Path, workflow_toml: Path = _WORKFLOW) -> DispatchPlan:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    repo.mkdir()
    return build_plan(
        repo=repo,
        work_item_id="proof-terminal",
        workflow_toml=workflow_toml,
        goal_file=root / "goal.md",
        fabro_bin="synthetic-fabro",
        janitor=("mise", "exec", "--", "just", "check"),
        janitor_checkout=root / "janitor",
        config_text=_CONFIG,
        default_branch="master",
    )


def _successful_checkpoint(*, completed_exit: bool = False) -> dict[str, object]:
    completed = [*_SUCCESSFUL_NODES, "exit"] if completed_exit else list(_SUCCESSFUL_NODES)
    outcomes = {node: {"status": "succeeded"} for node in completed}
    return {
        "timestamp": "2026-10-09T03:15:20.178706428Z",
        "current_node": "exit" if completed_exit else "verify_pr",
        "next_node_id": None if completed_exit else "exit",
        "completed_nodes": completed,
        "git_commit_sha": _HEAD,
        "node_outcomes": outcomes,
    }


def _failed_inspect(
    *,
    checkpoint: dict[str, object] | None,
    run_id: str = _RUN_ID,
    status_kind: str = "failed",
    failure_message: str = _WORKER_EXIT_MESSAGE,
    earlier_checkpoints: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    record: dict[str, object] = {
        "run_id": run_id,
        "status": {"kind": status_kind, "reason": "terminated"},
        "conclusion": {
            "status": status_kind,
            "failure": {
                "reason": "terminated",
                "detail": {
                    "category": "deterministic",
                    "message": failure_message,
                },
            },
        },
    }
    if earlier_checkpoints:
        record["checkpoints"] = [{"checkpoint": item} for item in earlier_checkpoints]
    if checkpoint is not None:
        record["checkpoint"] = checkpoint
    return record


def _pull_request(*, plan: DispatchPlan) -> dict[str, object]:
    return {
        "number": 41,
        "state": "MERGED",
        "headRefName": plan.branch,
        "headRefOid": _HEAD,
        "headRepository": {"nameWithOwner": _REPOSITORY},
        "mergeCommit": {"oid": _MERGE_SHA},
        "autoMergeRequest": None,
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [],
        "additions": 1,
        "deletions": 1,
    }


def _dispatch(
    *,
    root: Path,
    inspect_record: dict[str, object] | None = None,
    pr_overrides: dict[str, object] | None = None,
    pr_responses: tuple[dict[str, object], ...] = (),
    pr_available: bool = True,
    repository_slug: str = _REPOSITORY,
    repository_exit_code: int = 0,
    repository_stdout: str | None = None,
    launcher_stderr: str = _WORKER_EXIT_MESSAGE,
    workflow_toml: Path = _WORKFLOW,
) -> tuple[DispatchOutcome, _Journal, _Runner]:
    plan = _plan(root=root, workflow_toml=workflow_toml)
    runner = _Runner(
        plan=plan,
        inspect_record=(
            _failed_inspect(checkpoint=_successful_checkpoint())
            if inspect_record is None
            else inspect_record
        ),
        pr_overrides=pr_overrides or {},
        pr_responses=pr_responses,
        pr_available=pr_available,
        repository_slug=repository_slug,
        repository_exit_code=repository_exit_code,
        repository_stdout=repository_stdout,
    )
    journal = _Journal()
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0),
        fabro_launcher=_Launcher(stderr=launcher_stderr),
    )
    return outcome, journal, runner


def test_store_loss_after_success_continues_the_normal_merge_reconciliation(
    tmp_path: Path,
) -> None:
    outcome, _journal, runner = _dispatch(root=tmp_path)

    assert (outcome.status, outcome.stage, outcome.pr_number, outcome.merge_sha) == (
        "green",
        "done",
        41,
        _MERGE_SHA,
    )
    assert any(argv[:3] == ["gh", "pr", "view"] for argv, _cwd in runner.calls)


def test_publication_must_match_the_checkpoint_head_and_reports_merge_state(
    tmp_path: Path,
) -> None:
    matching, _journal, _runner = _dispatch(
        root=tmp_path / "matching",
    )
    stale, _journal, _runner = _dispatch(
        root=tmp_path / "stale",
        pr_overrides={"headRefOid": "b" * 40},
    )

    assert (matching.status, matching.stage, matching.pr_number, matching.merge_sha) == (
        "green",
        "done",
        41,
        _MERGE_SHA,
    )
    assert (stale.status, stale.stage, stale.pr_number) == (
        "failed",
        "fabro-run",
        None,
    )


def test_rejected_publication_is_authenticated_before_any_forge_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _dispatcher_terminal_publication,
        "read_current_merge_hold",
        lambda **_kwargs: "unheld",
    )
    cases: tuple[tuple[str, dict[str, object], str], ...] = (
        ("wrong-head", {"headRefOid": "b" * 40}, _REPOSITORY),
        ("wrong-branch", {"headRefName": "feat/unrelated"}, _REPOSITORY),
        ("wrong-repository", {}, "someone-else/proof-repo"),
    )

    for name, pr_overrides, repository_slug in cases:
        outcome, _journal, runner = _dispatch(
            root=tmp_path / name,
            pr_overrides={"state": "OPEN", "mergeCommit": None, **pr_overrides},
            repository_slug=repository_slug,
        )

        assert (outcome.status, outcome.stage, outcome.pr_number) == (
            "failed",
            "fabro-run",
            None,
        ), name
        assert not any(argv[:3] == ["gh", "pr", "merge"] for argv, _cwd in runner.calls), name


def test_changed_publication_is_reauthenticated_before_any_forge_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _dispatcher_terminal_publication,
        "read_current_merge_hold",
        lambda **_kwargs: "unheld",
    )
    initial = {"state": "OPEN", "mergeCommit": None}
    cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("changed-head", {"headRefOid": "b" * 40}),
        ("changed-branch", {"headRefName": "feat/unrelated"}),
        (
            "changed-repository",
            {"headRepository": {"nameWithOwner": "someone-else/proof-repo"}},
        ),
        ("changed-number", {"number": 42}),
    )

    for name, changed in cases:
        outcome, _journal, runner = _dispatch(
            root=tmp_path / name,
            pr_responses=(initial, {**initial, **changed}),
        )

        assert (outcome.status, outcome.stage, outcome.pr_number) == (
            "failed",
            "fabro-run",
            None,
        ), name
        assert not any(argv[:3] == ["gh", "pr", "merge"] for argv, _cwd in runner.calls), name
        assert all(
            {"headRefName", "headRefOid", "headRepository"}.issubset(argv[-1].split(","))
            for argv, _cwd in runner.calls
            if argv[:3] == ["gh", "pr", "view"]
        ), name


def test_journal_separates_conflict_checkpoint_publication_and_classification(
    tmp_path: Path,
) -> None:
    outcome, journal, _runner = _dispatch(root=tmp_path)
    records = {str(record.get("stage")): record for record in journal.records}

    assert outcome.status == "green"
    assert {
        "fabro-terminal-conflict",
        "fabro-terminal-checkpoint",
        "fabro-terminal-publication",
        "fabro-terminal-classification",
    }.issubset(records)
    assert records["fabro-terminal-conflict"] == {
        "stage": "fabro-terminal-conflict",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "engine_status": "failed",
        "failure_cause": _WORKER_EXIT_MESSAGE,
        "failure_category": "deterministic",
    }
    assert records["fabro-terminal-checkpoint"] == {
        "stage": "fabro-terminal-checkpoint",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "timestamp": "2026-10-09T03:15:20.178706428Z",
        "current_node": "verify_pr",
        "next_node_id": "exit",
        "commit_sha": _HEAD,
    }
    assert records["fabro-terminal-publication"] == {
        "stage": "fabro-terminal-publication",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "pr_number": 41,
        "state": "MERGED",
        "branch": "feat/proof-terminal",
        "head": _HEAD,
        "repository": "thewoolleyman/proof-repo",
    }
    assert records["fabro-terminal-classification"] == {
        "stage": "fabro-terminal-classification",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "classification": "successful-workflow",
        "evidence": "checkpoint+publication",
    }


def test_scenario_166_authenticates_terminal_success_and_preserves_non_green_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final_stage, _journal, _runner = _dispatch(root=tmp_path / "final-stage")
    completed_exit, _journal, _runner = _dispatch(
        root=tmp_path / "completed-exit",
        inspect_record=_failed_inspect(checkpoint=_successful_checkpoint(completed_exit=True)),
    )

    assert (final_stage.status, final_stage.stage, final_stage.pr_number) == (
        "green",
        "done",
        41,
    )
    assert (completed_exit.status, completed_exit.stage, completed_exit.pr_number) == (
        "green",
        "done",
        41,
    )

    intermediate = _successful_checkpoint()
    intermediate.update(current_node="pr", next_node_id="verify_pr")
    failed_required = _successful_checkpoint()
    failed_required["node_outcomes"] = {
        **{node: {"status": "succeeded"} for node in _SUCCESSFUL_NODES},
        "review": {"status": "failed"},
    }
    needs_human = _successful_checkpoint()
    needs_human.update(current_node="needs_human", next_node_id=None)
    cases: tuple[tuple[str, dict[str, object], dict[str, object], bool, str], ...] = (
        ("missing-checkpoint", _failed_inspect(checkpoint=None), {}, True, _REPOSITORY),
        (
            "other-run",
            _failed_inspect(checkpoint=_successful_checkpoint(), run_id="01OTHER"),
            {},
            True,
            _REPOSITORY,
        ),
        (
            "earlier-success",
            _failed_inspect(
                checkpoint=intermediate,
                earlier_checkpoints=(_successful_checkpoint(),),
            ),
            {},
            True,
            _REPOSITORY,
        ),
        ("intermediate", _failed_inspect(checkpoint=intermediate), {}, True, _REPOSITORY),
        ("required-failed", _failed_inspect(checkpoint=failed_required), {}, True, _REPOSITORY),
        (
            "cancelled",
            _failed_inspect(
                checkpoint=_successful_checkpoint(),
                status_kind="cancelled",
                failure_message="cancelled by operator",
            ),
            {},
            True,
            _REPOSITORY,
        ),
        ("needs-human", _failed_inspect(checkpoint=needs_human), {}, True, _REPOSITORY),
        (
            "missing-pr",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {},
            False,
            _REPOSITORY,
        ),
        (
            "wrong-head",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {"headRefOid": "b" * 40},
            True,
            _REPOSITORY,
        ),
        (
            "wrong-branch",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {"headRefName": "feat/unrelated"},
            True,
            _REPOSITORY,
        ),
        (
            "wrong-repository",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {},
            True,
            "someone-else/proof-repo",
        ),
        (
            "closed-unmerged",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {"state": "CLOSED", "mergeCommit": None},
            True,
            _REPOSITORY,
        ),
        (
            "worker-nonzero",
            _failed_inspect(
                checkpoint=_successful_checkpoint(),
                failure_message="Worker exited before emitting a terminal run event: exit status: 2",
            ),
            {},
            True,
            _REPOSITORY,
        ),
    )
    for name, inspect_record, pr_overrides, pr_available, repository_slug in cases:
        outcome, journal, _runner = _dispatch(
            root=tmp_path / name,
            inspect_record=inspect_record,
            pr_overrides=pr_overrides,
            pr_available=pr_available,
            repository_slug=repository_slug,
        )
        assert (outcome.status, outcome.stage, outcome.pr_number) == (
            "failed",
            "fabro-run",
            None,
        ), name
        assert not any(
            record.get("stage") == "fabro-terminal-classification" for record in journal.records
        ), name

    monkeypatch.setattr(
        _dispatcher_terminal_publication,
        "read_current_merge_hold",
        _held_merge,
    )
    held, held_journal, _runner = _dispatch(
        root=tmp_path / "held",
        pr_overrides={"state": "OPEN", "mergeCommit": None},
    )
    assert (held.status, held.stage, held.pr_number, held.merge_sha) == (
        "green",
        "pr",
        41,
        None,
    )
    assert any(
        record.get("stage") == "fabro-terminal-classification" for record in held_journal.records
    )


def test_unavailable_or_unstructured_evidence_retains_the_failed_disposition(
    tmp_path: Path,
) -> None:
    incomplete = _successful_checkpoint()
    incomplete["completed_nodes"] = ["start", "verify_pr"]
    incomplete["node_outcomes"] = {
        "start": {"status": "succeeded"},
        "verify_pr": {"status": "succeeded"},
    }
    malformed = _successful_checkpoint()
    _ = malformed.pop("node_outcomes")
    cases: tuple[tuple[str, dict[str, object], int, str | None], ...] = (
        ("repository-unavailable", _failed_inspect(checkpoint=_successful_checkpoint()), 1, ""),
        (
            "repository-malformed",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            0,
            "not-json",
        ),
        ("incomplete-route", _failed_inspect(checkpoint=incomplete), 0, None),
        ("malformed-checkpoint", _failed_inspect(checkpoint=malformed), 0, None),
    )
    observed: list[tuple[str, DispatchOutcome | AttemptFailure]] = []
    for name, inspect_record, repository_exit_code, repository_stdout in cases:
        dispatched = attempt(
            action=partial(
                _dispatch,
                root=tmp_path / name,
                inspect_record=inspect_record,
                repository_exit_code=repository_exit_code,
                repository_stdout=repository_stdout,
            ),
            exceptions=(AttributeError, TypeError),
        )
        observed.append(
            (name, dispatched if isinstance(dispatched, AttemptFailure) else dispatched[0])
        )

    assert [
        (name, value.status, value.stage, value.pr_number)
        if isinstance(value, DispatchOutcome)
        else (name, type(value.error).__name__, "raised", None)
        for name, value in observed
    ] == [(name, "failed", "fabro-run", None) for name, *_rest in cases]


def test_unmeasurable_configured_route_fails_closed_without_raising(
    tmp_path: Path,
) -> None:
    """A configured green terminal nobody can READ is no evidence, not a crash.

    These four faults belong to the CONFIGURED WORKFLOW rather than to the
    engine record, which is why no checkpoint fixture can reach them: a run
    config that cannot be read, one declaring no ``[workflow] graph``, a graph
    file the declaration names but that is not there, and a graph whose shape
    the success derivation refuses.  Each is a failure to MEASURE the green
    terminal, so the dispatch keeps its ordinary non-green outcome -- the same
    treatment the sibling malformed-node-outcome legs get, because reading an
    unmeasurable route as a success and raising out of ``run_dispatch`` are
    both ways of abandoning the dispatch mid-flight.

    ``exceptions`` catches ``OSError`` beside the two the sibling legs catch,
    because two of these faults are unreadable FILES rather than unreadable
    engine evidence, and a raise has to be OBSERVED as a case outcome instead
    of ending the whole case list at the first one.
    """
    unsupported_graph = (
        "digraph fabricated {\n"
        "  verify_pr [shape=box];\n"
        "  exit [shape=Msquare];\n"
        "  verify_pr -> exit;\n"
        "}\n"
    )
    cases: tuple[tuple[str, str | None, str | None], ...] = (
        ("absent-run-config", None, None),
        ("no-graph-key", '[workflow]\nname = "fabricated"\n', None),
        ("absent-graph-file", '[workflow]\ngraph = "fabricated.fabro"\n', None),
        ("unsupported-graph", '[workflow]\ngraph = "fabricated.fabro"\n', unsupported_graph),
    )
    observed: list[tuple[str, DispatchOutcome | AttemptFailure]] = []
    for name, manifest, graph_text in cases:
        workflow_dir = tmp_path / name / "workflow"
        workflow_dir.mkdir(parents=True)
        workflow_toml = workflow_dir / "workflow.toml"
        if manifest is not None:
            _ = workflow_toml.write_text(manifest, encoding="utf-8")
        if graph_text is not None:
            _ = (workflow_dir / "fabricated.fabro").write_text(graph_text, encoding="utf-8")
        dispatched = attempt(
            action=partial(
                _dispatch,
                root=tmp_path / name / "dispatch",
                workflow_toml=workflow_toml,
            ),
            exceptions=(AttributeError, OSError, TypeError),
        )
        observed.append(
            (name, dispatched if isinstance(dispatched, AttemptFailure) else dispatched[0])
        )

    assert [
        (name, value.status, value.stage, value.pr_number)
        if isinstance(value, DispatchOutcome)
        else (name, type(value.error).__name__, "raised", None)
        for name, value in observed
    ] == [(name, "failed", "fabro-run", None) for name, *_rest in cases]


def test_a_real_records_ungraded_completed_nodes_still_prove_the_route(
    tmp_path: Path,
) -> None:
    """The engine GRADES FEWER NODES THAN IT COMPLETES, measured off a real record.

    Every other case here synthesizes a grade for every node it also lists as
    completed, so a predicate demanding one per graph dominator passes against
    all of them and refuses the shape the engine actually writes.  The omission
    set is therefore taken from the committed ``fabro inspect --json`` capture
    rather than invented: that record lists ``setup`` and ``dod_gate`` in
    ``completed_nodes`` with NO ``node_outcomes`` entry, and ``dod_gate`` is a
    dominator of this repository's configured green terminal by that same name.

    ``start`` stands in for that record's ``setup``, the graph's own entry
    marker: ``start [shape=Mdiamond]`` declares no backend and runs no script,
    so there has never been anything for the engine to grade there.  A
    dominator the engine never graded is UNGRADED, not failed -- the dispatch
    keeps its ordinary non-green outcome when a graded one reports a failure,
    which the ``required-failed`` control asserts, and when the route is not
    completed at all, which ``incomplete-route`` asserts.
    """
    captured = json.loads(_NATIVE_INSPECT.read_text(encoding="utf-8"))
    assert isinstance(captured, list)
    checkpoint = captured[0]["checkpoint"]
    ungraded = tuple(
        node for node in checkpoint["completed_nodes"] if node not in checkpoint["node_outcomes"]
    )

    sparse = _successful_checkpoint()
    sparse["node_outcomes"] = {
        node: {"status": "succeeded"}
        for node in _SUCCESSFUL_NODES
        if node not in {"start", "dod_gate"}
    }
    outcome, _journal, _runner = _dispatch(
        root=tmp_path,
        inspect_record=_failed_inspect(checkpoint=sparse),
    )

    assert ungraded == ("setup", "dod_gate")
    assert (outcome.status, outcome.stage, outcome.pr_number, outcome.merge_sha) == (
        "green",
        "done",
        41,
        _MERGE_SHA,
    )


def test_petri_stage_states_grade_the_route_and_collapse_repaired_visits(
    tmp_path: Path,
) -> None:
    """A record carrying no ``node_outcomes`` is graded from its ``stages`` map.

    The Petri engine records no ``node_outcomes`` at all; its per-stage results
    live in the record's own top-level ``stages`` map, keyed ``<node>@<visit>``
    and carrying ``state`` rather than ``status``.  The needs-human reader
    already resolves both inputs, so a second reading here would make the two
    disagree about whether the SAME record is readable -- and "unreadable" is
    the answer that keeps an already-merged pull request classified failed.

    The map is the run's whole history and the engine never retires an entry,
    so the fixture carries the ORDINARY shape of every run the graph's bounded
    fix loop rescued: ``janitor@1`` failed, ``fix@1`` succeeded, ``janitor@2``
    succeeded.  Grading entry by entry would refuse that run on its repaired
    stage.  The control is the mirror image -- a final stage whose NEWEST visit
    is the failed one -- which must still end non-green, so the collapse is
    evidence about visit order rather than a reader that stopped reading
    failures.
    """
    repaired = _successful_checkpoint()
    _ = repaired.pop("node_outcomes")
    repaired_record = _failed_inspect(checkpoint=repaired)
    repaired_record["stages"] = {
        **{f"{node}@1": {"state": "succeeded"} for node in _SUCCESSFUL_NODES},
        "janitor@1": {"state": "failed"},
        "fix@1": {"state": "succeeded"},
        "janitor@2": {"state": "succeeded"},
    }
    regressed = _successful_checkpoint()
    _ = regressed.pop("node_outcomes")
    regressed_record = _failed_inspect(checkpoint=regressed)
    regressed_record["stages"] = {
        **{f"{node}@1": {"state": "succeeded"} for node in _SUCCESSFUL_NODES},
        "verify_pr@2": {"state": "failed"},
    }

    graded, _journal, _runner = _dispatch(
        root=tmp_path / "repaired",
        inspect_record=repaired_record,
    )
    regressed_outcome, _journal, _runner = _dispatch(
        root=tmp_path / "regressed",
        inspect_record=regressed_record,
    )

    assert (graded.status, graded.stage, graded.pr_number, graded.merge_sha) == (
        "green",
        "done",
        41,
        _MERGE_SHA,
    )
    assert (regressed_outcome.status, regressed_outcome.stage, regressed_outcome.pr_number) == (
        "failed",
        "fabro-run",
        None,
    )


def test_missing_or_malformed_per_node_outcomes_fail_closed_without_raising(
    tmp_path: Path,
) -> None:
    missing = _successful_checkpoint(completed_exit=True)
    missing["node_outcomes"] = {node: {"status": "succeeded"} for node in _SUCCESSFUL_NODES}
    cases: list[tuple[str, dict[str, object]]] = [("missing", missing)]
    for name, malformed_outcome in (
        ("null", None),
        ("string", "succeeded"),
        ("number", 1),
    ):
        malformed = _successful_checkpoint()
        outcomes = malformed["node_outcomes"]
        assert isinstance(outcomes, dict)
        outcomes["verify_pr"] = malformed_outcome
        cases.append((name, malformed))

    observed: list[tuple[str, DispatchOutcome | AttemptFailure]] = []
    for name, checkpoint in cases:
        dispatched = attempt(
            action=partial(
                _dispatch,
                root=tmp_path / name,
                inspect_record=_failed_inspect(checkpoint=checkpoint),
            ),
            exceptions=(AttributeError, TypeError),
        )
        observed.append(
            (name, dispatched if isinstance(dispatched, AttemptFailure) else dispatched[0])
        )

    assert [
        (name, value.status, value.stage, value.pr_number)
        if isinstance(value, DispatchOutcome)
        else (name, type(value.error).__name__, "raised", None)
        for name, value in observed
    ] == [(name, "failed", "fabro-run", None) for name, _checkpoint in cases]


def test_the_engines_own_entry_marker_proves_the_route_without_the_graph_start_id(
    tmp_path: Path,
) -> None:
    """A REAL record's entry marker proves the route, and no record carries ``start``.

    Every qualifying case above lists the graph's literal ``start`` id in
    ``completed_nodes``.  No engine writes it: ``start [shape=Mdiamond]``
    declares no backend and runs no script, so nothing executes there and
    ``completed_nodes`` -- the engine's own account of the nodes it RAN --
    cannot contain it.  Both committed ``fabro inspect --json`` captures open
    with ``setup``, the engine's own name for that marker, and NEITHER names
    ``start``.

    So a completion requirement reaching for ``start`` refuses 100% of real
    records while reporting the same clean non-green a genuine failure
    reports.  That is the one failure this rule cannot have: it is
    indistinguishable at every surface from the correct fail-closed answer,
    so Definition-of-Done assertions 1 and 2 would deliver nothing while
    every test built on a substituted ``start`` still passed.

    The entry marker is therefore relieved of COMPLETION exactly as it is
    already relieved of the GRADE, and nothing is given up by it: the marker
    dominates every node in the graph, so it carries no discriminating
    information, and the route still rests on every EXECUTABLE dominator
    completing and on the terminal-shape test.  The ``required-failed`` and
    ``incomplete-route`` controls above keep the fail-closed direction.
    """
    entry_markers = {
        path.name: json.loads(path.read_text(encoding="utf-8"))[0]["checkpoint"]["completed_nodes"]
        for path in sorted(_NATIVE_INSPECT.parent.glob("*.json"))
    }
    marker = entry_markers["background.json"][0]

    real = _successful_checkpoint()
    real["completed_nodes"] = [marker, *(node for node in _SUCCESSFUL_NODES if node != "start")]
    real["node_outcomes"] = {
        node: {"status": "succeeded"} for node in _SUCCESSFUL_NODES if node != "start"
    }
    outcome, _journal, _runner = _dispatch(
        root=tmp_path,
        inspect_record=_failed_inspect(checkpoint=real),
    )

    assert marker == "setup"
    assert [name for name, nodes in entry_markers.items() if "start" in nodes] == []
    assert [nodes[0] for nodes in entry_markers.values()] == ["setup", "setup"]
    assert (outcome.status, outcome.stage, outcome.pr_number, outcome.merge_sha) == (
        "green",
        "done",
        41,
        _MERGE_SHA,
    )
