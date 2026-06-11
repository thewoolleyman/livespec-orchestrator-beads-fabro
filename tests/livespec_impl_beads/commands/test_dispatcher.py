"""Tests for the `dispatcher` CLI (ledger-check / dispatch / loop) and its
private planning, engine, ledger-check, and io layers.

The hermetic `FakeBeadsClient` is the Ledger backend (autouse fixture).
The engine is driven through a scripted in-memory `CommandRunner`; the
production `ShellCommandRunner` is exercised with real `sys.executable -c`
subprocesses, mirroring `test_orchestrator`'s injected-CLI approach.
"""

import json
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_impl_beads.commands import dispatcher
from livespec_impl_beads.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_impl_beads.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
    _decode,  # pyright: ignore[reportPrivateUsage]
    utc_now_iso,
)
from livespec_impl_beads.commands._dispatcher_janitor_checks import run_janitor_checks
from livespec_impl_beads.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_impl_beads.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
    fabro_run_argv,
    fetch_argv,
    janitor_argv_with_default,
    mise_trust_argv,
    parse_pr_view,
    pr_arm_argv,
    pr_update_branch_argv,
    pr_view_argv,
    pull_primary_argv,
    render_goal,
    worktree_add_argv,
    worktree_remove_argv,
)
from livespec_impl_beads.commands._dispatcher_spec_checks import run_spec_checks
from livespec_impl_beads.commands._dispatcher_spec_commitments import (
    Obligation,
    collect_obligations_and_supersedes,
)
from livespec_impl_beads.commands.detect_impl_gaps import detect_rules
from livespec_impl_beads.commands.dispatcher import main
from livespec_impl_beads.store import append_work_item, materialize_work_items, read_work_items
from livespec_impl_beads.types import StoreConfig, WorkItem
from livespec_runtime.cross_repo.types import CrossRepoManifest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="open",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
    )


@dataclass(kw_only=True)
class _FakeRunner:
    """Scripted CommandRunner: consumes queued results, logs invocations."""

    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        assert timeout_seconds > 0
        self.calls.append((argv, cwd))
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _err(stderr: str = "boom") -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr=stderr)


def _pr_json(
    *,
    state: str = "OPEN",
    armed: bool = True,
    merge_state: str = "CLEAN",
    sha: str | None = None,
) -> str:
    return json.dumps(
        {
            "number": 7,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": merge_state,
            "mergeCommit": {"oid": sha} if sha is not None else None,
        }
    )


def _dispatch(
    *,
    runner: _FakeRunner,
    repo: Path,
    attempts: int = 3,
) -> tuple[DispatchOutcome, _RecordingJournal, list[float]]:
    journal = _RecordingJournal()
    naps: list[float] = []
    outcome = run_dispatch(
        plan=_plan(repo=repo),
        runner=runner,
        journal=journal,
        sleep=naps.append,
        poll=PollPolicy(attempts=attempts, interval_seconds=0.5),
    )
    return outcome, journal, naps


# ---------------------------------------------------------------------------
# Ledger checks
# ---------------------------------------------------------------------------


def test_ledger_checks_pass_on_clean_items() -> None:
    items = [
        _item(),
        _item(id="b-2", depends_on=("livespec-impl-beads-t1",), gap_id="gap-1"),
        _item(id="b-3", status="closed", gap_id="gap-1"),
    ]
    assert run_ledger_checks(items=items) == []


def test_ledger_checks_flag_unparseable_depends_on_entry() -> None:
    items = [_item(depends_on=({"bogus": "shape"},))]
    findings = run_ledger_checks(items=items)
    assert [finding.check for finding in findings] == ["depends-on-ref-wellformedness"]
    assert "bogus" in findings[0].message


def test_ledger_checks_flag_orphan_dependency() -> None:
    items = [_item(depends_on=("nope-99",))]
    findings = run_ledger_checks(items=items)
    assert [finding.check for finding in findings] == ["no-orphan-dependency"]
    assert "nope-99" in findings[0].message


def test_ledger_checks_flag_duplicate_gap_ids_sorted() -> None:
    items = [
        _item(id="z-2", gap_id="gap-x"),
        _item(id="a-1", gap_id="gap-x"),
        _item(id="m-3", gap_id="gap-solo"),
    ]
    findings = run_ledger_checks(items=items)
    assert [finding.item_id for finding in findings] == ["a-1", "z-2"]
    assert all(finding.check == "no-duplicate-gap-id" for finding in findings)
    assert "a-1, z-2" in findings[0].message


def test_ledger_checks_ignore_closed_items() -> None:
    items = [_item(status="closed", depends_on=("nope-99", {"bad": True}))]
    assert run_ledger_checks(items=items) == []


# ---------------------------------------------------------------------------
# Spec checks (the re-homed spec-context invariants)
# ---------------------------------------------------------------------------


def _manifest() -> CrossRepoManifest:
    return CrossRepoManifest(targets={})


def _write_pc(*, directory: Path, stem: str, pc_text: str, revision_text: str | None) -> None:
    _ = (directory / f"{stem}.md").write_text(pc_text, encoding="utf-8")
    if revision_text is not None:
        _ = (directory / f"{stem}-revision.md").write_text(revision_text, encoding="utf-8")


def _revision(*, decision: str) -> str:
    return f"---\ndecision: {decision}\n---\nNarration.\n"


def _spec_tree(*, tmp_path: Path) -> Path:
    """Build a SPECIFICATION tree with one live MUST rule + a rich history walk."""
    spec = tmp_path / "SPECIFICATION"
    v1 = spec / "history" / "v001" / "proposed_changes"
    v1.mkdir(parents=True)
    _ = (spec / "spec.md").write_text(
        "# Spec\n\n## Rules\n\nThe system MUST frobnicate.\n", encoding="utf-8"
    )
    covered_pc = (
        "---\n"
        "topic: covered\n"
        "spec_commitments:\n"
        "  impl_followups:\n"
        "    - id_hint: hint-filed\n"
        "      description: tracked by a filed work-item\n"
        "\n"
        "    - id_hint: hint-unfiled\n"
        "    - id_hint:\n"
        "    - id_hint: hint-old\n"
        "status: pending\n"
        "---\nBody.\n"
    )
    _write_pc(
        directory=v1, stem="covered", pc_text=covered_pc, revision_text=_revision(decision="accept")
    )
    rejected_pc = (
        "---\nspec_commitments:\n  impl_followups:\n    - id_hint: hint-rejected\n---\nBody.\n"
    )
    _write_pc(
        directory=v1,
        stem="rejected",
        pc_text=rejected_pc,
        revision_text=_revision(decision="reject"),
    )
    _write_pc(
        directory=v1,
        stem="plain",
        pc_text="No front matter here.\n",
        revision_text=_revision(decision="accept"),
    )
    _write_pc(
        directory=v1,
        stem="unclosed",
        pc_text="---\nspec_commitments:\n",
        revision_text=_revision(decision="accept"),
    )
    _write_pc(
        directory=v1,
        stem="no-commitments",
        pc_text="---\ntopic: bare\n---\nBody.\n",
        revision_text=_revision(decision="accept"),
    )
    _write_pc(
        directory=v1,
        stem="no-decision",
        pc_text="---\ntopic: x\n---\n",
        revision_text="---\ntopic: undecided\n---\n",
    )
    _write_pc(
        directory=v1,
        stem="bare-rev",
        pc_text="---\ntopic: y\n---\n",
        revision_text="No front matter either.\n",
    )
    _write_pc(directory=v1, stem="orphan", pc_text="---\ntopic: z\n---\n", revision_text=None)
    _ = (v1 / "notes.txt").write_text("not a pc\n", encoding="utf-8")
    (v1 / "drafts").mkdir()
    v2 = spec / "history" / "v002"
    (v2 / "proposed_changes").mkdir(parents=True)
    _ = (v2 / "PRUNED_HISTORY.json").write_text("{}\n", encoding="utf-8")
    pruned_pc = "---\nspec_commitments:\n  impl_followups:\n    - id_hint: hint-pruned\n---\n"
    _write_pc(
        directory=v2 / "proposed_changes",
        stem="pruned",
        pc_text=pruned_pc,
        revision_text=_revision(decision="accept"),
    )
    v3 = spec / "history" / "v003" / "proposed_changes"
    v3.mkdir(parents=True)
    superseder_pc = (
        "---\n"
        "spec_commitments:\n"
        "  supersedes:\n"
        "    - hint-old\n"
        "      reason: replaced by the v003 wiring\n"
        "  impl_followups:\n"
        "---\n"
    )
    _write_pc(
        directory=v3,
        stem="superseder",
        pc_text=superseder_pc,
        revision_text=_revision(decision="modify"),
    )
    (spec / "history" / "v004").mkdir()
    (spec / "history" / "not-a-version").mkdir()
    _ = (spec / "history" / "stray.txt").write_text("not a version dir\n", encoding="utf-8")
    return spec


def test_collect_obligations_walks_accepted_history(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    obligations, superseded = collect_obligations_and_supersedes(spec_root=spec)
    assert obligations == [
        Obligation(id_hint="hint-filed", version_label="v001", pc_stem="covered"),
        Obligation(id_hint="hint-unfiled", version_label="v001", pc_stem="covered"),
        Obligation(id_hint="hint-old", version_label="v001", pc_stem="covered"),
    ]
    assert superseded == {"hint-old"}


def test_collect_obligations_empty_without_history(tmp_path: Path) -> None:
    assert collect_obligations_and_supersedes(spec_root=tmp_path) == ([], set())


def test_spec_checks_flag_stalled_epics() -> None:
    items = [
        _item(id="dep-1", status="closed"),
        _item(id="dep-2", status="closed"),
        _item(
            id="epic-stalled",
            type="epic",
            depends_on=("dep-1", {"kind": "local", "work_item_id": "dep-2"}),
        ),
        _item(id="epic-rolling", type="epic", status="in_progress", depends_on=("dep-1",)),
    ]
    findings = run_spec_checks(items=items, spec_root=Path("/nonexistent"), manifest=_manifest())
    stalled = [finding for finding in findings if finding.check == "no-stalled-epic"]
    assert [(finding.item_id, finding.severity) for finding in stalled] == [
        ("epic-rolling", "fail"),
        ("epic-stalled", "fail"),
    ]
    assert "still open" in stalled[1].message


def test_spec_checks_epic_not_stalled_when_any_dep_unresolved_or_open() -> None:
    items = [
        _item(id="dep-open"),
        _item(id="dep-closed", status="closed"),
        _item(id="epic-open-dep", type="epic", depends_on=("dep-open", "dep-closed")),
        _item(id="epic-missing-dep", type="epic", depends_on=("ghost-1",)),
        _item(id="epic-bad-dep", type="epic", depends_on=({"bogus": True},)),
        _item(
            id="epic-sibling-dep",
            type="epic",
            depends_on=(
                {"kind": "sibling_work_item", "repo": "unconfigured", "work_item_id": "x-1"},
            ),
        ),
        _item(id="epic-empty", type="epic"),
        _item(id="epic-closed", type="epic", status="closed", depends_on=("dep-closed",)),
        _item(id="task-done-deps", depends_on=("dep-closed",)),
    ]
    findings = run_spec_checks(items=items, spec_root=Path("/nonexistent"), manifest=_manifest())
    assert [finding for finding in findings if finding.check == "no-stalled-epic"] == []


def test_spec_checks_skip_spec_tree_checks_without_spec_root(tmp_path: Path) -> None:
    findings = run_spec_checks(items=[], spec_root=tmp_path / "missing", manifest=_manifest())
    assert [(finding.check, finding.severity) for finding in findings] == [
        ("no-stale-gap-tied", "skipped"),
        ("unresolved-spec-commitment", "skipped"),
    ]
    assert all(finding.item_id == "-" for finding in findings)


def test_spec_checks_warn_only_for_stale_gap_tied_items(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    fresh_gap = detect_rules(spec_root=spec)[0].gap_id
    items = [
        _item(id="g-fresh", origin="gap-tied", gap_id=fresh_gap),
        _item(id="g-stale", origin="gap-tied", gap_id="gap-gone1234", status="in_progress"),
        _item(id="g-closed", origin="gap-tied", gap_id="gap-gone1234", status="closed"),
        _item(id="g-none", origin="gap-tied", gap_id=None),
        _item(id="f-free", gap_id="gap-gone1234"),
    ]
    findings = run_spec_checks(items=items, spec_root=spec, manifest=_manifest())
    stale = [finding for finding in findings if finding.check == "no-stale-gap-tied"]
    assert [(finding.item_id, finding.severity) for finding in stale] == [("g-stale", "warn")]
    assert "gap-gone1234" in stale[0].message
    assert "non-fix disposition" in stale[0].message


def test_spec_checks_no_gap_findings_without_open_gap_tied_items(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    findings = run_spec_checks(items=[_item()], spec_root=spec, manifest=_manifest())
    assert [finding for finding in findings if finding.check == "no-stale-gap-tied"] == []


def test_spec_checks_flag_unresolved_commitments(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    items = [
        _item(id="filed-1", spec_commitment_hint="hint-filed"),
        _item(id="empty-hint", spec_commitment_hint=""),
    ]
    findings = run_spec_checks(items=items, spec_root=spec, manifest=_manifest())
    unresolved = [finding for finding in findings if finding.check == "unresolved-spec-commitment"]
    assert [(finding.item_id, finding.severity) for finding in unresolved] == [
        ("hint-unfiled", "fail")
    ]
    assert "v001/proposed_changes/covered.md" in unresolved[0].message
    assert "--spec-commitment-hint hint-unfiled" in unresolved[0].message


# ---------------------------------------------------------------------------
# Janitor checks (the re-homed stale-cleanup checks)
# ---------------------------------------------------------------------------

_JANITOR_PROBE_COUNT = 7


def _janitor_results(*, fail_at: int | None = None) -> list[CommandResult]:
    """Script the seven janitor probes; `fail_at` makes that probe exit 1."""
    worktrees = (
        "worktree /repo\nHEAD aaa\nbranch refs/heads/master\n\n"
        "worktree /repo/worktrees/merged\nHEAD bbb\nbranch refs/heads/feat/x\n\n"
        "worktree /repo/worktrees/gone\nHEAD ccc\nbranch refs/heads/feat/y\n\n"
        "worktree /repo/worktrees/detached\nHEAD ddd\ndetached\n\n"
        "worktree /repo/worktrees/ondefault\nHEAD eee\nbranch refs/heads/master\n\n"
        "worktree /repo/worktrees/active\nHEAD fff\nbranch refs/heads/feat/z\n"
    )
    remote = (
        "aaa\trefs/heads/master\n"
        "bbb\trefs/heads/feat/x\n"
        "fff\trefs/heads/feat/z\n"
        "malformed-line-without-tab\n"
    )
    results = [
        _ok("true\n"),
        _ok("origin/master\n"),
        _ok("master\nfeat/x\n"),
        _ok(remote),
        _ok(worktrees),
        _ok("thewoolleyman/livespec-impl-beads\n"),
        _ok("feat/x\nmaster\n"),
    ]
    if fail_at is not None:
        results[fail_at] = _err()
    return results


def test_janitor_checks_skip_outside_git_repo(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_err()])
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert [(finding.check, finding.severity) for finding in findings] == [
        ("no-stale-merged-branch", "skipped"),
        ("no-stale-merged-pr-branch", "skipped"),
        ("no-stale-worktree", "skipped"),
    ]
    assert len(runner.calls) == 1
    assert runner.calls[0][0] == ["git", "rev-parse", "--is-inside-work-tree"]


def test_janitor_checks_skip_without_default_branch(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_ok("true\n"), _err()])
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert {finding.severity for finding in findings} == {"skipped"}
    assert "default branch undetermined" in findings[0].message
    assert len(runner.calls) == 2


def test_janitor_checks_clean_state_yields_no_findings(tmp_path: Path) -> None:
    results = _janitor_results()
    results[2] = _ok("master\n")
    results[4] = _ok("worktree /repo\nHEAD aaa\nbranch refs/heads/master\n")
    results[6] = _ok("")
    runner = _FakeRunner(queue=results)
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert findings == []
    assert len(runner.calls) == _JANITOR_PROBE_COUNT
    assert runner.calls[2][0] == [
        "git",
        "for-each-ref",
        "--format=%(refname:short)",
        "--merged",
        "master",
        "refs/heads",
    ]


def test_janitor_checks_tolerate_empty_worktree_listing(tmp_path: Path) -> None:
    results = _janitor_results()
    results[4] = _ok("")
    runner = _FakeRunner(queue=results)
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert [finding for finding in findings if finding.check == "no-stale-worktree"] == []


def test_janitor_checks_flag_stale_branches_prs_and_worktrees(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=_janitor_results())
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert [(finding.check, finding.item_id, finding.severity) for finding in findings] == [
        ("no-stale-merged-branch", "feat/x", "warn"),
        ("no-stale-merged-pr-branch", "feat/x", "warn"),
        ("no-stale-worktree", "/repo/worktrees/gone", "warn"),
        ("no-stale-worktree", "/repo/worktrees/merged", "warn"),
    ]
    assert "git branch -d feat/x" in findings[0].message
    delete_action = "gh api -X DELETE repos/thewoolleyman/livespec-impl-beads/git/refs/heads/feat/x"
    assert delete_action in findings[1].message
    assert "git worktree remove /repo/worktrees/gone" in findings[2].message


@pytest.mark.parametrize(
    ("fail_at", "expected_skipped"),
    [
        (2, {"no-stale-merged-branch", "no-stale-worktree"}),
        (3, {"no-stale-merged-pr-branch", "no-stale-worktree"}),
        (4, {"no-stale-worktree"}),
        (5, {"no-stale-merged-pr-branch"}),
        (6, {"no-stale-merged-pr-branch"}),
    ],
)
def test_janitor_checks_skip_per_failed_probe(
    tmp_path: Path,
    fail_at: int,
    expected_skipped: set[str],
) -> None:
    runner = _FakeRunner(queue=_janitor_results(fail_at=fail_at))
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    skipped = {finding.check for finding in findings if finding.severity == "skipped"}
    assert skipped == expected_skipped
    assert len(runner.calls) == _JANITOR_PROBE_COUNT


# ---------------------------------------------------------------------------
# Plan layer — builders and parsers
# ---------------------------------------------------------------------------


def test_build_plan_derives_branch_worktree_and_default_janitor(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    assert plan.branch == "fabro/x-1"
    assert plan.worktree == tmp_path / "worktrees" / "fabro-x-1"
    assert plan.janitor == ("mise", "exec", "--", "just", "check")


def test_janitor_argv_with_default_passthrough_and_empty() -> None:
    assert janitor_argv_with_default(janitor=("echo", "hi")) == ("echo", "hi")
    assert janitor_argv_with_default(janitor=()) == ("mise", "exec", "--", "just", "check")


def test_render_goal_includes_item_fields_and_optional_gap(tmp_path: Path) -> None:
    with_gap = render_goal(item=_item(gap_id="gap-9"), repo=tmp_path, branch="fabro/t")
    assert "Gap id: gap-9" in with_gap
    assert "Work-item: livespec-impl-beads-t1" in with_gap
    assert "A ready task" in with_gap
    assert "Do the thing." in with_gap
    without_gap = render_goal(item=_item(), repo=tmp_path, branch="fabro/t")
    assert "Gap id" not in without_gap


def test_argv_builders_encode_family_discipline(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    assert fetch_argv(plan=plan) == ["git", "-C", str(tmp_path), "fetch", "origin"]
    assert worktree_add_argv(plan=plan) == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "add",
        str(plan.worktree),
        "-b",
        "fabro/x-1",
        "origin/master",
    ]
    assert mise_trust_argv(plan=plan) == ["mise", "trust"]
    assert fabro_run_argv(plan=plan) == [
        "fabro",
        "run",
        str(tmp_path / "wf.toml"),
        "--goal-file",
        str(tmp_path / "goal.md"),
        "--no-upgrade-check",
        "-I",
        "work_item_id=x-1",
        "-I",
        "branch=fabro/x-1",
    ]
    assert pr_view_argv(plan=plan)[:3] == ["gh", "pr", "view"]
    assert pr_arm_argv(plan=plan, number=7) == [
        "gh",
        "pr",
        "merge",
        "7",
        "--rebase",
        "--auto",
        "--delete-branch",
    ]
    assert pr_update_branch_argv(plan=plan, number=7) == ["gh", "pr", "update-branch", "7"]
    assert pull_primary_argv(plan=plan) == [
        "mise",
        "exec",
        "--",
        "git",
        "-C",
        str(tmp_path),
        "pull",
        "--ff-only",
        "origin",
        "master",
    ]
    assert worktree_remove_argv(plan=plan) == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "remove",
        str(plan.worktree),
    ]


def test_parse_pr_view_rejects_unusable_shapes() -> None:
    assert parse_pr_view(stdout="not json") is None
    assert parse_pr_view(stdout="[1, 2]") is None
    assert parse_pr_view(stdout=json.dumps({"state": "OPEN"})) is None


def test_parse_pr_view_reads_fields_and_defaults() -> None:
    full = parse_pr_view(stdout=_pr_json(state="MERGED", armed=True, sha="abc123"))
    assert full is not None
    assert (full.number, full.state, full.auto_merge_armed) == (7, "MERGED", True)
    assert full.merge_sha == "abc123"
    sparse = parse_pr_view(stdout=json.dumps({"number": 3}))
    assert sparse is not None
    assert (sparse.state, sparse.merge_state_status) == ("UNKNOWN", "UNKNOWN")
    assert sparse.auto_merge_armed is False
    assert sparse.merge_sha is None
    weird = parse_pr_view(stdout=json.dumps({"number": 3, "mergeCommit": {"oid": ""}}))
    assert weird is not None
    assert weird.merge_sha is None
    nonsense = parse_pr_view(stdout=json.dumps({"number": 3, "mergeCommit": "abc"}))
    assert nonsense is not None
    assert nonsense.merge_sha is None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def test_engine_fails_at_each_worktree_preparation_step(tmp_path: Path) -> None:
    for failing_index, stage in [(0, "fetch"), (1, "worktree-add"), (2, "mise-trust")]:
        queue = [_ok(), _ok(), _ok()][:failing_index] + [_err(stderr=f"{stage} broke")]
        runner = _FakeRunner(queue=queue)
        outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
        assert (outcome.status, outcome.stage) == ("failed", stage)
        assert f"{stage} broke" in outcome.detail
        assert journal.records[-1]["stage"] == stage


def test_engine_fails_when_fabro_run_fails_and_trims_detail(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_ok(), _ok(), _ok(), _err(stderr="x" * 3000)])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    assert len(outcome.detail) == 2000


def test_engine_fails_when_no_pr_found(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_ok(), _ok(), _ok(), _ok(), _err(stderr="no pr")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")
    runner = _FakeRunner(queue=[_ok(), _ok(), _ok(), _ok(), _ok(stdout="garbage")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")


def test_engine_green_path_with_already_armed_pr(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(stdout="fabro done"),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe01")),
            _ok(),
            _ok(),
            _ok(),
        ]
    )
    outcome, journal, naps = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "done")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe01")
    assert naps == []
    stages = [record["stage"] for record in journal.records]
    assert stages[-3:] == ["pull-primary", "janitor-post-merge", "worktree-remove"]


def test_engine_arms_auto_merge_as_fallback(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(stdout=_pr_json(armed=False)),
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe02")),
            _ok(),
            _ok(),
            _ok(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    armed_call = runner.calls[5][0]
    assert armed_call[:3] == ["gh", "pr", "merge"]


def test_engine_skips_arming_when_pr_already_merged(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(stdout=_pr_json(state="MERGED", armed=False, sha="cafe03")),
            _ok(stdout=_pr_json(state="MERGED", armed=False, sha="cafe03")),
            _ok(),
            _ok(),
            _ok(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    assert all(call[0][:3] != ["gh", "pr", "merge"] for call in runner.calls)


def test_engine_fails_when_review_after_arming_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(stdout=_pr_json(armed=False)),
            _ok(),
            _err(stderr="gh broke"),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")


def test_engine_updates_branch_when_behind_then_merges(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(armed=True, merge_state="BEHIND")),
            _ok(),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe04")),
            _ok(),
            _ok(),
            _ok(),
        ]
    )
    outcome, _, naps = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    assert naps == [0.5]
    update_call = runner.calls[6][0]
    assert update_call == ["gh", "pr", "update-branch", "7"]


def test_engine_poll_budget_exhaustion_keeps_pr_number(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _err(stderr="transient gh failure"),
            _ok(stdout=_pr_json(armed=True)),
        ]
    )
    outcome, _, naps = _dispatch(runner=runner, repo=tmp_path, attempts=2)
    assert (outcome.status, outcome.stage) == ("failed", "merge-poll")
    assert outcome.pr_number == 7
    assert naps == [0.5]


def test_engine_post_merge_failures_carry_merge_evidence(tmp_path: Path) -> None:
    cases = [
        (["pull broke"], "pull-primary"),
        ([None, "janitor broke"], "janitor-post-merge"),
        ([None, None, "reap broke"], "worktree-remove"),
    ]
    for tail_specs, stage in cases:
        tail = [_ok() if spec is None else _err(stderr=spec) for spec in tail_specs]
        runner = _FakeRunner(
            queue=[
                _ok(),
                _ok(),
                _ok(),
                _ok(),
                _ok(stdout=_pr_json(armed=True)),
                _ok(stdout=_pr_json(state="MERGED", sha="cafe05")),
                *tail,
            ]
        )
        outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
        assert (outcome.status, outcome.stage) == ("failed", stage)
        assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe05")


def test_engine_runs_configured_janitor_in_repo(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe06")),
            _ok(),
            _ok(),
            _ok(),
        ]
    )
    _, _, _ = _dispatch(runner=runner, repo=tmp_path)
    janitor_call = runner.calls[7]
    assert janitor_call[0] == ["mise", "exec", "--", "just", "check"]
    assert janitor_call[1] == tmp_path


# ---------------------------------------------------------------------------
# IO seams
# ---------------------------------------------------------------------------


def test_shell_runner_captures_exit_and_streams(tmp_path: Path) -> None:
    runner = ShellCommandRunner()
    code = "import sys; sys.stdout.write('out'); sys.stderr.write('err'); sys.exit(3)"
    result = runner.run(argv=[sys.executable, "-c", code], cwd=tmp_path, timeout_seconds=30.0)
    assert (result.exit_code, result.stdout, result.stderr) == (3, "out", "err")


def test_shell_runner_converts_timeouts(tmp_path: Path) -> None:
    runner = ShellCommandRunner()
    result = runner.run(
        argv=[sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        timeout_seconds=0.2,
    )
    assert result.exit_code == 124
    assert "timeout after" in result.stderr


def test_decode_handles_bytes_str_and_none() -> None:
    assert _decode(raw=b"x") == "x"
    assert _decode(raw="y") == "y"
    assert _decode(raw=None) == ""


def test_journal_file_appends_jsonl_with_timestamps(tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "nested" / "journal.jsonl")
    journal.append(record={"stage": "one"})
    journal.append(record={"stage": "two"})
    lines = (tmp_path / "nested" / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [record["stage"] for record in parsed] == ["one", "two"]
    assert all(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", record["at"]) for record in parsed
    )


def test_utc_now_iso_shape() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now_iso())


# ---------------------------------------------------------------------------
# CLI surface — ledger-check
# ---------------------------------------------------------------------------


def test_ledger_check_clean_human_and_json(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["ledger-check"]) == 0
    assert "(no ledger findings)" in capsys.readouterr().out
    assert main(["ledger-check", "--project-root", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_ledger_check_reports_findings(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    append_work_item(path=_config(), item=_item(depends_on=("ghost-1",)))
    assert main(["ledger-check", "--project-root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "no-orphan-dependency" in out
    assert main(["ledger-check", "--project-root", str(tmp_path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["check"] == "no-orphan-dependency"
    assert payload[0]["severity"] == "fail"


# ---------------------------------------------------------------------------
# CLI surface — spec-check
# ---------------------------------------------------------------------------


def test_spec_check_cli_skips_without_spec_tree(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["spec-check"]) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "no-stale-gap-tied" in out
    assert main(["spec-check", "--project-root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {entry["severity"] for entry in payload} == {"skipped"}


def test_spec_check_cli_reports_findings(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(id="g-stale", origin="gap-tied", gap_id="gap-gone1234"),
    )
    assert main(["spec-check", "--project-root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "WARN  no-stale-gap-tied  g-stale" in out
    assert "FAIL  unresolved-spec-commitment  hint-filed" in out
    exit_code = main(
        ["spec-check", "--project-root", str(tmp_path), "--spec-root", str(spec), "--json"]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    checks = {entry["check"] for entry in payload}
    assert checks == {"no-stale-gap-tied", "unresolved-spec-commitment"}


# ---------------------------------------------------------------------------
# CLI surface — janitor-check
# ---------------------------------------------------------------------------


def test_janitor_check_cli_skips_outside_git_repo(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["janitor-check"]) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "no-stale-worktree" in out
    assert main(["janitor-check", "--repo", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {entry["severity"] for entry in payload} == {"skipped"}


# ---------------------------------------------------------------------------
# CLI surface — dispatch and loop
# ---------------------------------------------------------------------------


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text("_version = 1\n", encoding="utf-8")
    return repo, workflow


def _green_outcome(*, item_id: str, sha: str | None = "feed01") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=11,
        merge_sha=sha,
        detail="merged",
    )


@dataclass(kw_only=True)
class _FakeRunDispatch:
    outcomes: dict[str, DispatchOutcome]
    seen: list[dict[str, object]] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        self.seen.append(kwargs)
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        return self.outcomes[plan.work_item_id]


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(read_work_items(path=_config()))


def test_dispatch_green_closes_item_and_journals(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    monkeypatch.setattr(
        "livespec_impl_beads.commands.dispatcher.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    exit_code = main(
        [
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "green"
    stored = _stored()[item.id]
    assert (stored.status, stored.resolution) == ("closed", "completed")
    assert stored.audit is not None
    assert (stored.audit.merge_sha, stored.audit.pr_number) == ("feed01", 11)
    goal_text = (tmp_path / f"fabro-goal-{item.id}.md").read_text(encoding="utf-8")
    assert "A ready task" in goal_text
    journal_lines = (
        (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8").splitlines()
    )
    stages = [json.loads(line)["stage"] for line in journal_lines]
    assert stages == ["ledger-close", "outcome"]
    poll = fake.seen[0]["poll"]
    assert isinstance(poll, PollPolicy)
    assert (poll.attempts, poll.interval_seconds) == (80, 30.0)


def test_dispatch_green_without_sha_closes_without_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id, sha=None)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    assert (
        main(["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]) == 0
    )
    stored = _stored()[item.id]
    assert (stored.status, stored.audit) == ("closed", None)


def test_dispatch_failed_outcome_leaves_item_open(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    failed = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="fabro exploded",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={item.id: failed}))
    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    assert "failed at fabro-run" in capsys.readouterr().out
    assert _stored()[item.id].status == "open"


def test_dispatch_no_close_on_merge_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    exit_code = main(
        [
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    assert _stored()[item.id].status == "open"


def test_dispatch_rejects_not_ready_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    blocker = _item(id="blocker-1")
    blocked = _item(id="blocked-2", depends_on=("blocker-1",))
    append_work_item(path=_config(), item=blocker)
    append_work_item(path=_config(), item=blocked)
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={}))
    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", "blocked-2", "--workflow", str(workflow)]
    )
    assert exit_code == 3
    assert (
        main(["dispatch", "--repo", str(repo), "--item", "ghost", "--workflow", str(workflow)]) == 3
    )


def test_dispatch_precondition_failures(tmp_path: Path) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    assert (
        main(
            [
                "dispatch",
                "--repo",
                str(tmp_path / "nope"),
                "--item",
                "x",
                "--workflow",
                str(workflow),
            ]
        )
        == 3
    )
    assert (
        main(
            [
                "dispatch",
                "--repo",
                str(repo),
                "--item",
                "x",
                "--workflow",
                str(tmp_path / "missing.toml"),
            ]
        )
        == 3
    )


def test_dispatch_bad_janitor_is_usage_error(tmp_path: Path) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    base = ["dispatch", "--repo", str(repo), "--item", "x", "--workflow", str(workflow)]
    assert main([*base, "--janitor", "not json"]) == 2
    assert main([*base, "--janitor", '{"a": 1}']) == 2
    assert main([*base, "--janitor", '["ok", 1]']) == 2


def test_dispatch_passes_custom_janitor_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    exit_code = main(
        [
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--janitor",
            '["echo", "ok"]',
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    plan = fake.seen[0]["plan"]
    assert isinstance(plan, DispatchPlan)
    assert plan.janitor == ("echo", "ok")


def test_dispatch_ledger_gate_blocks_and_skip_flag_bypasses(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    append_work_item(path=_config(), item=_item(id="orphaned-9", depends_on=("ghost-7",)))
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    base = ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    assert main(base) == 1
    err = capsys.readouterr().err
    assert "pre-dispatch ledger checks failed" in err
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert "ledger-check" in journal_text
    assert main([*base, "--skip-ledger-check", "--no-close-on-merge"]) == 0


def test_dispatch_default_workflow_resolves_to_repo_fabro_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    exit_code = main(["dispatch", "--repo", str(repo), "--item", item.id, "--no-close-on-merge"])
    assert exit_code == 0
    plan = fake.seen[0]["plan"]
    assert isinstance(plan, DispatchPlan)
    assert plan.workflow_toml.name == "workflow.toml"
    assert "implement-work-item" in str(plan.workflow_toml)


def test_dispatch_custom_journal_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    journal_path = tmp_path / "elsewhere.jsonl"
    exit_code = main(
        [
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--journal",
            str(journal_path),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    assert journal_path.is_file()


def test_loop_shadow_requires_explicit_items(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    exit_code = main(["loop", "--repo", str(repo), "--budget", "5", "--workflow", str(workflow)])
    assert exit_code == 0
    assert "(nothing dispatched)" in capsys.readouterr().out


def test_loop_shadow_dispatches_named_items_within_budget(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    first = _item(id="a-1", priority=1)
    second = _item(id="b-2", priority=2)
    append_work_item(path=_config(), item=first)
    append_work_item(path=_config(), item=second)
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1")})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
            "--item",
            "a-1",
            "--item",
            "b-2",
            "--no-close-on-merge",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [entry["work_item_id"] for entry in payload] == ["a-1"]
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    pick = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "loop-pick"
    )
    assert pick["picked"] == ["a-1"]
    assert pick["mode"] == "shadow"


def test_loop_autonomous_parallel_mixed_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    first = _item(id="a-1", priority=1)
    second = _item(id="b-2", priority=2)
    append_work_item(path=_config(), item=first)
    append_work_item(path=_config(), item=second)
    failed = DispatchOutcome(
        work_item_id="b-2",
        status="failed",
        stage="merge-poll",
        pr_number=12,
        merge_sha=None,
        detail="poll budget",
    )
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1"), "b-2": failed})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--parallel",
            "2",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 1
    assert len(fake.seen) == 2


def test_loop_precondition_usage_and_ledger_gate(
    tmp_path: Path,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    assert (
        main(
            ["loop", "--repo", str(tmp_path / "nope"), "--budget", "1", "--workflow", str(workflow)]
        )
        == 3
    )
    assert (
        main(
            [
                "loop",
                "--repo",
                str(repo),
                "--budget",
                "1",
                "--workflow",
                str(workflow),
                "--janitor",
                "broken",
            ]
        )
        == 2
    )
    append_work_item(path=_config(), item=_item(id="orphaned-9", depends_on=("ghost-7",)))
    assert main(["loop", "--repo", str(repo), "--budget", "1", "--workflow", str(workflow)]) == 1


def test_loop_parallel_floor_of_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--parallel",
            "0",
            "--workflow",
            str(workflow),
            "--item",
            item.id,
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0


def test_ledger_finding_dataclass_shape() -> None:
    finding = LedgerFinding(check="c", item_id="i", message="m")
    assert (finding.check, finding.item_id, finding.message, finding.severity) == (
        "c",
        "i",
        "m",
        "fail",
    )
    skipped = LedgerFinding(check="c", item_id="i", message="m", severity="skipped")
    assert skipped.severity == "skipped"
