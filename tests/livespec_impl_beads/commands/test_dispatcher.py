"""Tests for the `dispatcher` CLI (ledger-check / dispatch / loop) and its
private planning, engine, ledger-check, and io layers.

The hermetic `FakeBeadsClient` is the Ledger backend (autouse fixture).
The engine is driven through a scripted in-memory `CommandRunner`; the
production `ShellCommandRunner` is exercised with real `sys.executable -c`
subprocesses, mirroring `test_orchestrator`'s injected-CLI approach.

C-mode (Architecture C, Fabro-owned docker sandbox) specifics covered
here: the run-config overlay materialization (mode-600, absolute graph
rewrite, post-run cleanup, and the appended env table carrying the
CLAUDE_CODE_OAUTH_TOKEN value read from the Dispatcher's process env —
the overlay IS the run-scoped credential projection; fabro `{{ env }}`
interpolation cannot deliver it because the server spawns the
resolving worker under a fail-closed env allowlist), the
CLAUDE_CODE_OAUTH_TOKEN fail-fast (an absent variable leaves nothing
to project, so the Dispatcher refuses to dispatch without it), the
sandbox sibling-clone provisioning (fleet-manifest-derived depth-1
clone prepare steps plus the LIVESPEC_SIBLING_CLONES_ROOT env key in
the same overlay, so cross-repo checks resolve family siblings inside
the sandbox), the dispatch lifecycle (fabro run from the repo's
primary checkout with no host worktree prep BEFORE the run; the
post-merge janitor runs in a fresh detached worktree of the merged
ref — never the host primary's working tree — with provisioning
failures classifying as `janitor-env-degraded` green outcomes rather
than work-item failures, per livespec-impl-beads-cgd), and the
`blocked` third terminal state (run parked at the in-loop human gate;
`fabro attach` is the answer path, never auto-resumed).
"""

import json
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from coverage import Coverage
from coverage.files import GlobMatcher, prep_patterns
from livespec_impl_beads._beads_client import FakeBeadsClient, make_beads_client
from livespec_impl_beads.commands import _dispatcher_reflection, dispatcher
from livespec_impl_beads.commands import next as next_command
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
    FleetMembers,
    SiblingClones,
    build_plan,
    fabro_inspect_argv,
    fabro_run_argv,
    item_sizing_warnings,
    janitor_argv_with_default,
    janitor_checkout_path,
    janitor_trust_argv,
    janitor_worktree_add_argv,
    janitor_worktree_remove_argv,
    parse_fleet_members,
    parse_pr_view,
    parse_run_id,
    parse_run_status,
    pr_arm_argv,
    pr_update_branch_argv,
    pr_view_argv,
    pull_primary_argv,
    render_goal,
    render_run_config_overlay,
)
from livespec_impl_beads.commands._dispatcher_spec_checks import run_spec_checks
from livespec_impl_beads.commands._dispatcher_spec_commitments import (
    Obligation,
    collect_obligations_and_supersedes,
)
from livespec_impl_beads.commands.detect_impl_gaps import detect_rules
from livespec_impl_beads.commands.dispatcher import (
    _fetch_fleet_manifest_text,  # pyright: ignore[reportPrivateUsage]
    _ready_items,  # pyright: ignore[reportPrivateUsage]
    main,
)
from livespec_impl_beads.errors import BeadsCommandError
from livespec_impl_beads.store import (
    WorkItemComment,
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_impl_beads.types import StoreConfig, WorkItem
from livespec_runtime.cross_repo.types import CrossRepoManifest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Canned fleet-manifest.jsonc payload the autouse fixture serves in
# place of the real `gh api` fetch (which must never run in the
# hermetic tier). Mirrors the committed shape on livespec master
# (owner + classed members, `//` comments). It includes a member named
# "repo" because `_repo_with_workflow` creates the dispatch-target
# checkout under that basename — letting dispatch-level tests assert
# the target's own clone step is excluded from the overlay.
_FLEET_MANIFEST_TEXT = (
    "// fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "livespec-dev-tooling", "class": "enforcement-suite" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

# The `_fetch_fleet_manifest_text` import above binds the production
# function object at import time, BEFORE the autouse fixture swaps the
# dispatcher module attribute for the canned text — so the real fetch
# implementation stays directly testable (with a scripted runner
# stand-in).
_real_fetch_fleet_manifest_text = _fetch_fleet_manifest_text


@pytest.fixture(autouse=True)
def fabro_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Hermetic C-mode dispatch environment for every test: an obviously
    fake CLAUDE_CODE_OAUTH_TOKEN in the process env (the Dispatcher
    fail-fasts without one, and projects the value into the run-config
    overlay's env table at dispatch), a canned fleet-manifest fetch (the
    production one shells out to `gh api`, which must never happen in
    the hermetic tier), plus a per-test temp dir so parallel
    pytest-xdist workers never collide on the dispatcher's goal/overlay
    temp files."""
    scratch = tmp_path_factory.mktemp("fabro-dispatch")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_impl_beads.commands.dispatcher._fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )


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
        janitor_checkout=repo / "janitor-co",
    )


@dataclass(kw_only=True)
class _FakeRunner:
    """Scripted CommandRunner: consumes queued results, logs invocations."""

    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        assert timeout_seconds > 0
        self.calls.append((argv, cwd))
        self.timeouts.append(timeout_seconds)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _post_merge_green_tail() -> list[CommandResult]:
    """The six all-green post-merge results: pull-primary, then the
    janitor-checkout lifecycle (preclean, add, trust, janitor run,
    remove)."""
    return [_ok() for _ in range(6)]


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


def test_build_plan_derives_publish_branch_and_default_janitor(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    assert plan.branch == "feat/x-1"
    assert plan.janitor == ("mise", "exec", "--", "just", "check")
    assert plan.janitor_checkout == tmp_path / "janitor-co"


def test_janitor_argv_with_default_passthrough_and_empty() -> None:
    assert janitor_argv_with_default(janitor=("echo", "hi")) == ("echo", "hi")
    assert janitor_argv_with_default(janitor=()) == ("mise", "exec", "--", "just", "check")


def test_janitor_checkout_path_lives_under_the_repo_worktrees_dir(tmp_path: Path) -> None:
    """The venue derives from the TARGET REPO (its `worktrees/` dispatch-
    worktree dir), never from the system temp dir — see the omit-glob
    test below for why a temp-dir venue false-reds the janitor."""
    checkout = janitor_checkout_path(repo=tmp_path / "primary", work_item_id="x-1")
    assert checkout == tmp_path / "primary" / "worktrees" / "janitor-x-1"
    assert not str(checkout).startswith(tempfile.gettempdir())


def test_janitor_checkout_venue_matches_no_coverage_omit_glob() -> None:
    """The tpu janitor false-red RCA: the venue used to be
    `/tmp/fabro-janitor-<item-id>` while pyproject's `[tool.coverage.run]`
    omit carries `/tmp/*` (a guard against measured tempfile artifacts
    that must STAY), so every source file inside the janitor checkout
    was omitted — coverage measured zero files and
    check-per-file-coverage died with NoDataError, false-redding a
    merged-green change. Pin the venue against the REAL committed omit
    configuration (read from this repo's pyproject.toml, never
    hardcoded) using coverage's own matcher: a product file inside the
    relocated janitor checkout matches no omit glob, while the same
    file under the old /tmp venue still does."""
    repo_root = Path(__file__).resolve().parents[3]
    omit = Coverage(config_file=str(repo_root / "pyproject.toml")).get_option("run:omit")
    assert isinstance(omit, list)
    matcher = GlobMatcher(prep_patterns(omit), "omit")
    probe = Path(".claude-plugin", "scripts", "livespec_impl_beads", "commands", "dispatcher.py")
    checkout = janitor_checkout_path(repo=repo_root, work_item_id="livespec-impl-beads-tpu")
    assert not matcher.match(str(checkout / probe))
    assert matcher.match(str(Path("/tmp", "fabro-janitor-livespec-impl-beads-tpu") / probe))


def test_render_goal_includes_item_fields_and_optional_gap(tmp_path: Path) -> None:
    with_gap = render_goal(item=_item(gap_id="gap-9"), repo=tmp_path, branch="feat/t")
    assert "Gap id: gap-9" in with_gap
    assert "Work-item: livespec-impl-beads-t1" in with_gap
    assert "Publish branch" in with_gap
    assert "feat/t" in with_gap
    assert "A ready task" in with_gap
    assert "Do the thing." in with_gap
    without_gap = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert "Gap id" not in without_gap


def test_argv_builders_encode_family_discipline(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    assert fabro_run_argv(plan=plan) == [
        "fabro",
        "run",
        str(tmp_path / "wf.toml"),
        "--goal-file",
        str(tmp_path / "goal.md"),
        "--no-upgrade-check",
    ]
    assert fabro_inspect_argv(plan=plan, run_id="01RUNID") == [
        "fabro",
        "inspect",
        "01RUNID",
        "--json",
    ]
    assert pr_view_argv(plan=plan)[:3] == ["gh", "pr", "view"]
    assert pr_view_argv(plan=plan)[3] == "feat/x-1"
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
    assert janitor_worktree_add_argv(plan=plan, ref="cafe01") == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "add",
        "--detach",
        str(tmp_path / "janitor-co"),
        "cafe01",
    ]
    assert janitor_worktree_remove_argv(plan=plan) == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "remove",
        "--force",
        str(tmp_path / "janitor-co"),
    ]
    assert janitor_trust_argv() == ["mise", "trust"]


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


def test_parse_run_id_reads_the_cli_run_line() -> None:
    output = "Preparing sandbox\n    Run: 01KTVX6AV677VBWPG63ERB4VH0\nmore output\n"
    assert parse_run_id(output=output) == "01KTVX6AV677VBWPG63ERB4VH0"


def test_parse_run_id_strips_ansi_and_misses_gracefully() -> None:
    dimmed = "\x1b[2mRun:\x1b[0m \x1b[2m01ABCDEF\x1b[0m\n"
    assert parse_run_id(output=dimmed) == "01ABCDEF"
    assert parse_run_id(output="no run line here") is None
    assert parse_run_id(output="") is None


def test_parse_run_status_reads_tagged_kind() -> None:
    blocked = json.dumps(
        {
            "run_id": "01A",
            "status": {"kind": "blocked", "blocked_reason": "human_input_required"},
        }
    )
    assert parse_run_status(stdout=blocked) == "blocked"
    succeeded = json.dumps({"status": {"kind": "succeeded", "reason": "completed"}})
    assert parse_run_status(stdout=succeeded) == "succeeded"
    assert parse_run_status(stdout=json.dumps({"status": "failed"})) == "failed"


def test_parse_run_status_rejects_unusable_shapes() -> None:
    assert parse_run_status(stdout="not json") is None
    assert parse_run_status(stdout=json.dumps([1, 2])) is None
    assert parse_run_status(stdout=json.dumps({"no_status": 1})) is None
    assert parse_run_status(stdout=json.dumps({"status": {"no_kind": 1}})) is None
    assert parse_run_status(stdout=json.dumps({"status": 7})) is None


# The fake token the autouse fixture plants in the process env; the
# overlay must carry it VERBATIM (and nothing else may — journals,
# argvs, and the committed config stay token-free).
_FAKE_TOKEN_LINE = 'CLAUDE_CODE_OAUTH_TOKEN = "test-oauth-token"'

# The dead interpolation channel: fabro resolves {{ env.* }} in the
# server-spawned WORKER, whose env is a fail-closed allowlist
# (fabro-server/src/spawn_env.rs), so this literal must never appear in
# a materialized overlay — it would flow through to the sandbox as-is.
_ENV_INTERPOLATION_LITERAL = "{{ env.CLAUDE_CODE_OAUTH_TOKEN }}"

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)


def test_render_run_config_overlay_rewrites_graph_and_appends_env_token(
    tmp_path: Path,
) -> None:
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        siblings=None,
    )
    assert rendered is not None
    assert f'graph = "{tmp_path / "workflow.fabro"}"' in rendered
    assert 'graph = "workflow.fabro"' not in rendered
    # The overlay IS the run-scoped credential projection: it appends
    # the [environments.<id>.env] table carrying the real token value
    # read from the Dispatcher's process env. No interpolation literal
    # may survive into it.
    assert "[environments.livespec-ci.env]" in rendered
    assert _FAKE_TOKEN_LINE in rendered
    assert _ENV_INTERPOLATION_LITERAL not in rendered


def test_render_run_config_overlay_keeps_absolute_graph_path(tmp_path: Path) -> None:
    absolute_graph = tmp_path / "elsewhere" / "g.fabro"
    committed = _COMMITTED_WORKFLOW_TOML.replace(
        'graph = "workflow.fabro"', f'graph = "{absolute_graph}"'
    )
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=committed,
        workflow_dir=tmp_path / "workflow-dir",
        token=overlay_token,
        siblings=None,
    )
    assert rendered is not None
    assert f'graph = "{absolute_graph}"' in rendered
    assert str(tmp_path / "workflow-dir") not in rendered.split("[environments")[0]


def test_render_run_config_overlay_rejects_unusable_shapes(tmp_path: Path) -> None:
    overlay_token = "test-oauth-token"
    assert (
        render_run_config_overlay(
            committed_text="_version = 1\n",
            workflow_dir=tmp_path,
            token=overlay_token,
            siblings=None,
        )
        is None
    )
    no_graph = '[workflow]\n\n[run.environment]\nid = "livespec-ci"\n'
    assert (
        render_run_config_overlay(
            committed_text=no_graph, workflow_dir=tmp_path, token=overlay_token, siblings=None
        )
        is None
    )
    # The env-table append targets [environments.<id>.env], so a config
    # without a [run.environment] id has nowhere to project the token.
    no_environment = '[workflow]\ngraph = "workflow.fabro"\n'
    assert (
        render_run_config_overlay(
            committed_text=no_environment, workflow_dir=tmp_path, token=overlay_token, siblings=None
        )
        is None
    )
    # Non-canonical whitespace: the graph value parses but the canonical
    # `graph = "<value>"` rewrite needle is absent, so the shape is refused
    # rather than silently shipping a relative graph path.
    spaced = '[workflow]\ngraph =  "workflow.fabro"\n\n[run.environment]\nid = "livespec-ci"\n'
    assert (
        render_run_config_overlay(
            committed_text=spaced, workflow_dir=tmp_path, token=overlay_token, siblings=None
        )
        is None
    )


# The sandbox sibling-clone plan the render tests exercise: clones land
# under the fabro sandbox workspace root, mirroring how livespec CI
# provisions LIVESPEC_SIBLING_CLONES_ROOT for the cross-repo wiring
# check.
_SIBLINGS = SiblingClones(
    owner="thewoolleyman",
    repos=("livespec", "livespec-dev-tooling"),
    clones_root="/workspace/siblings",
)

_LIVESPEC_CLONE_STEP_LINE = (
    'script = "mkdir -p /workspace/siblings && git clone --quiet --depth 1'
    ' https://github.com/thewoolleyman/livespec.git /workspace/siblings/livespec"'
)

_DEV_TOOLING_CLONE_STEP_LINE = (
    'script = "mkdir -p /workspace/siblings && git clone --quiet --depth 1'
    " https://github.com/thewoolleyman/livespec-dev-tooling.git"
    ' /workspace/siblings/livespec-dev-tooling"'
)

_SIBLING_ENV_LINE = 'LIVESPEC_SIBLING_CLONES_ROOT = "/workspace/siblings"'


def test_parse_fleet_members_reads_owner_and_member_repos() -> None:
    members = parse_fleet_members(manifest_text=_FLEET_MANIFEST_TEXT)
    assert members == FleetMembers(
        owner="thewoolleyman",
        repos=("livespec", "livespec-dev-tooling", "repo"),
    )


def test_parse_fleet_members_rejects_malformed_manifests() -> None:
    """Fail-fast philosophy: a manifest that does not parse into an
    owner plus a non-empty members list (with GitHub-slug-shaped names —
    the values are spliced into prepare-step scripts, so anything else
    is refused) yields None, and the caller refuses the dispatch with an
    actionable error instead of cloning from a guessed list."""
    bad_manifests = [
        "not json {{",
        json.dumps([1, 2]),
        json.dumps({"members": [{"repo": "livespec"}]}),
        json.dumps({"owner": "bad owner!", "members": [{"repo": "livespec"}]}),
        json.dumps({"owner": "o", "members": {}}),
        json.dumps({"owner": "o", "members": ["livespec"]}),
        json.dumps({"owner": "o", "members": [{"class": "core"}]}),
        json.dumps({"owner": "o", "members": [{"repo": "bad repo"}]}),
        json.dumps({"owner": "o", "members": []}),
    ]
    for manifest_text in bad_manifests:
        assert parse_fleet_members(manifest_text=manifest_text) is None


def test_render_run_config_overlay_appends_sibling_clone_steps_and_env_root(
    tmp_path: Path,
) -> None:
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        siblings=_SIBLINGS,
    )
    assert rendered is not None
    assert rendered.count("[[run.prepare.steps]]") == 2
    assert _LIVESPEC_CLONE_STEP_LINE in rendered
    assert _DEV_TOOLING_CLONE_STEP_LINE in rendered
    # The clone prepare steps are appended BEFORE the env table header,
    # and the clones-root env key lands INSIDE [environments.<id>.env]
    # (after the header) so it reaches the sandbox as container-level
    # environment alongside the credential — the single declaration
    # point TOML allows for that table.
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    assert rendered.index(_LIVESPEC_CLONE_STEP_LINE) < env_table_at
    assert rendered.index(_DEV_TOOLING_CLONE_STEP_LINE) < env_table_at
    assert rendered.index(_SIBLING_ENV_LINE) > env_table_at
    assert _FAKE_TOKEN_LINE in rendered


def test_render_run_config_overlay_without_siblings_appends_no_clone_steps(
    tmp_path: Path,
) -> None:
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        siblings=None,
    )
    assert rendered is not None
    assert "[[run.prepare.steps]]" not in rendered
    assert "LIVESPEC_SIBLING_CLONES_ROOT" not in rendered


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


_BLOCKED_INSPECT_JSON = json.dumps(
    {
        "run_id": "01RUNBLOCKED",
        "status": {"kind": "blocked", "blocked_reason": "human_input_required"},
    }
)


def test_engine_green_runs_janitor_in_fresh_checkout(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(stdout="fabro done"),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe01")),
            _ok(),  # pull-primary
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-post-merge
            _ok(),  # janitor-checkout-remove
        ]
    )
    outcome, journal, naps = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "done")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe01")
    assert naps == []
    first_argv, first_cwd = runner.calls[0]
    assert first_argv[:2] == ["fabro", "run"]
    assert first_cwd == tmp_path
    # No host worktree prep BEFORE the fabro run (Architecture C): the
    # only worktree commands belong to the post-merge janitor checkout.
    assert all("worktree" not in argv for argv, _ in runner.calls[:4])
    stages = [record["stage"] for record in journal.records]
    assert stages == [
        "fabro-run",
        "pr-view",
        "pr-view",
        "pull-primary",
        "janitor-checkout-preclean",
        "janitor-checkout-add",
        "janitor-checkout-trust",
        "janitor-post-merge",
        "janitor-checkout-remove",
    ]
    checkout = tmp_path / "janitor-co"
    add_argv, add_cwd = runner.calls[5]
    assert add_argv == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "add",
        "--detach",
        str(checkout),
        "cafe01",
    ]
    assert add_cwd == tmp_path
    remove_argv = ["git", "-C", str(tmp_path), "worktree", "remove", "--force", str(checkout)]
    assert runner.calls[4][0] == remove_argv
    assert runner.calls[8][0] == remove_argv


def test_engine_fails_when_fabro_run_fails_and_trims_detail(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_err(stderr="x" * 3000)])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    assert len(outcome.detail) == 2000


def test_engine_blocked_run_is_a_third_terminal_state(tmp_path: Path) -> None:
    parked = CommandResult(
        exit_code=1,
        stdout="",
        stderr=(
            "    Run: 01RUNBLOCKED\n"
            "Interview ended without an answer. The run is still waiting "
            "for input; reattach to answer it.\n"
        ),
    )
    runner = _FakeRunner(queue=[parked, _ok(stdout=_BLOCKED_INSPECT_JSON)])
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("blocked", "fabro-run")
    assert (outcome.pr_number, outcome.merge_sha) == (None, None)
    assert "fabro attach 01RUNBLOCKED" in outcome.detail
    inspect_argv, inspect_cwd = runner.calls[1]
    assert inspect_argv == ["fabro", "inspect", "01RUNBLOCKED", "--json"]
    assert inspect_cwd == tmp_path
    assert len(runner.calls) == 2
    assert [record["stage"] for record in journal.records] == ["fabro-run", "fabro-inspect"]


def test_engine_blocked_check_falls_back_to_exit_code_routing(tmp_path: Path) -> None:
    failed_inspect = json.dumps({"status": {"kind": "failed", "reason": "workflow_error"}})
    runner = _FakeRunner(
        queue=[
            CommandResult(exit_code=1, stdout="Run: 01RUNDEAD\n", stderr="agent died"),
            _ok(stdout=failed_inspect),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    runner = _FakeRunner(queue=[_err(stderr="hard crash, no run line")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    assert len(runner.calls) == 1
    runner = _FakeRunner(
        queue=[
            CommandResult(exit_code=1, stdout="Run: 01RUNGONE\n", stderr="boom"),
            _err(stderr="inspect broke"),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")


def test_engine_succeeded_run_with_run_id_proceeds_to_pr_flow(tmp_path: Path) -> None:
    succeeded_inspect = json.dumps({"status": {"kind": "succeeded", "reason": "completed"}})
    runner = _FakeRunner(
        queue=[
            _ok(stdout="    Run: 01RUNGREEN\n"),
            _ok(stdout=succeeded_inspect),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe07")),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "done")


def test_engine_fails_when_no_pr_found(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_ok(), _err(stderr="no pr")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")
    runner = _FakeRunner(queue=[_ok(), _ok(stdout="garbage")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")


def test_engine_arms_auto_merge_as_fallback(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=False)),
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe02")),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    armed_call = runner.calls[2][0]
    assert armed_call[:3] == ["gh", "pr", "merge"]


def test_engine_skips_arming_when_pr_already_merged(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(state="MERGED", armed=False, sha="cafe03")),
            _ok(stdout=_pr_json(state="MERGED", armed=False, sha="cafe03")),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    assert all(call[0][:3] != ["gh", "pr", "merge"] for call in runner.calls)


def test_engine_fails_when_review_after_arming_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
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
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(armed=True, merge_state="BEHIND")),
            _ok(),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe04")),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, naps = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    assert naps == [0.5]
    update_call = runner.calls[3][0]
    assert update_call == ["gh", "pr", "update-branch", "7"]


def test_engine_poll_budget_exhaustion_keeps_pr_number(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
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
        ([None, None, None, None, "janitor broke"], "janitor-post-merge"),
    ]
    for tail_specs, stage in cases:
        tail = [_ok() if spec is None else _err(stderr=spec) for spec in tail_specs]
        runner = _FakeRunner(
            queue=[
                _ok(),
                _ok(stdout=_pr_json(armed=True)),
                _ok(stdout=_pr_json(state="MERGED", sha="cafe05")),
                *tail,
            ]
        )
        outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
        assert (outcome.status, outcome.stage) == ("failed", stage)
        assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe05")


def test_engine_janitor_red_keeps_checkout_for_diagnosis(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe05")),
            _ok(),  # pull-primary
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _err(stderr="2 failed, 1 passed"),  # janitor red in the fresh checkout
        ]
    )
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "janitor-post-merge")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe05")
    checkout = tmp_path / "janitor-co"
    assert str(checkout) in outcome.detail
    assert "kept for diagnosis" in outcome.detail
    assert "2 failed, 1 passed" in outcome.detail
    # A red checkout is PRESERVED (no remove after the janitor ran):
    # the working tree is the diagnosis evidence.
    assert len(runner.calls) == 8
    assert [record["stage"] for record in journal.records][-1] == "janitor-post-merge"


def test_engine_degrades_when_janitor_checkout_provisioning_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe08")),
            _ok(),  # pull-primary
            _err(stderr="not a working tree"),  # preclean (deliberately ignored)
            _err(stderr="disk full"),  # janitor-checkout-add
        ]
    )
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe08")
    assert "DID NOT RUN" in outcome.detail
    assert "disk full" in outcome.detail
    assert "mise exec -- just check" in outcome.detail
    assert "not a work-item failure" in outcome.detail
    # The janitor itself never ran: the dispatch ends at the failed add.
    assert len(runner.calls) == 6
    assert [record["stage"] for record in journal.records][-1] == "janitor-checkout-add"


def test_engine_degrades_when_mise_trust_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe09")),
            _ok(),  # pull-primary
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _err(stderr="config not trusted"),  # janitor-checkout-trust
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert "mise trust" in outcome.detail
    assert "config not trusted" in outcome.detail
    trust_argv, trust_cwd = runner.calls[6]
    assert trust_argv == ["mise", "trust"]
    assert trust_cwd == tmp_path / "janitor-co"


def test_engine_janitor_checkout_falls_back_to_origin_master_without_sha(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha=None)),
            _ok(),  # pull-primary
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-post-merge
            _ok(),  # janitor-checkout-remove
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "done")
    add_calls = [argv for argv, _ in runner.calls if "worktree" in argv and "add" in argv]
    assert len(add_calls) == 1
    assert add_calls[0][-1] == "origin/master"


def test_engine_runs_configured_janitor_in_fresh_checkout(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe06")),
            _ok(),  # pull-primary
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-post-merge
            _ok(),  # janitor-checkout-remove
        ]
    )
    _, _, _ = _dispatch(runner=runner, repo=tmp_path)
    janitor_calls = [
        (argv, cwd) for argv, cwd in runner.calls if argv == ["mise", "exec", "--", "just", "check"]
    ]
    assert len(janitor_calls) == 1
    assert janitor_calls[0][1] == tmp_path / "janitor-co"


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
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
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
    """Stand-in for run_dispatch: records kwargs plus the materialized
    overlay (content + mode) as observed AT CALL TIME, since the real
    dispatcher deletes the overlay after the run returns."""

    outcomes: dict[str, DispatchOutcome]
    seen: list[dict[str, object]] = field(default_factory=list)
    overlay_texts: list[str] = field(default_factory=list)
    overlay_modes: list[int] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        self.seen.append(kwargs)
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        # The dispatcher materializes the overlay before every run it
        # launches, so the file always exists here (and is gone again
        # once the dispatch returns).
        self.overlay_texts.append(plan.workflow_toml.read_text(encoding="utf-8"))
        self.overlay_modes.append(stat.S_IMODE(plan.workflow_toml.stat().st_mode))
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
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    stages = [json.loads(line)["stage"] for line in journal_text.splitlines()]
    # The dispatch opens by journaling the per-dispatch correlation id
    # (29f.3 — projected into the sandbox's CC OTel OTEL_RESOURCE_ATTRIBUTES
    # so telemetry joins to this dispatch). After `outcome` come the
    # post-verdict fail-open stages: y0m's cost-gate (here `cost-gate-error`
    # because no `fabro` binary is on the hermetic PATH — the gate fails
    # open and never changes the verdict), then ddu's staged-self-update
    # gate (here `self-update-skipped`: the green outcome has a PR, but
    # `gh pr view` fails on the hermetic non-repo so the merged-file list is
    # empty — NOT a self-merge), then the mechanical reflection stage at the
    # default `observe` lever (work-item 29f.2). The ledger-close precedes
    # the post-verdict stages.
    assert stages == [
        "dispatch-id",
        "ledger-close",
        "outcome",
        "cost-gate-error",
        "self-update-skipped",
        "reflection",
    ]
    poll = fake.seen[0]["poll"]
    assert isinstance(poll, PollPolicy)
    assert (poll.attempts, poll.interval_seconds) == (80, 30.0)


def test_dispatch_materializes_mode600_overlay_and_cleans_up(
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
    plan = fake.seen[0]["plan"]
    assert isinstance(plan, DispatchPlan)
    assert plan.workflow_toml.name == f"fabro-run-config-{item.id}.toml"
    assert plan.janitor_checkout == repo / "worktrees" / f"janitor-{item.id}"
    assert not plan.workflow_toml.exists()
    assert fake.overlay_modes == [0o600]
    overlay_text = fake.overlay_texts[0]
    # The overlay is the run-scoped credential projection: it carries
    # the token value read from the Dispatcher's process env (mode-600,
    # deleted when the run returns — both asserted above). The token
    # never reaches the journal, and no dead {{ env }} interpolation
    # literal survives into the overlay.
    assert _FAKE_TOKEN_LINE in overlay_text
    assert _ENV_INTERPOLATION_LITERAL not in overlay_text
    assert f'graph = "{workflow.parent / "workflow.fabro"}"' in overlay_text
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert "test-oauth-token" not in journal_text


def test_dispatch_overlay_provisions_sibling_clones_for_fleet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The materialized overlay provisions every fleet member EXCEPT the
    dispatch target (already the sandbox workspace clone) as a depth-1
    prepare-step clone under /workspace/siblings, and projects
    LIVESPEC_SIBLING_CLONES_ROOT into the sandbox env table so
    cross-repo checks under `just check` resolve the siblings there —
    mirroring livespec CI's sibling-clone provisioning."""
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
    overlay_text = fake.overlay_texts[0]
    assert _LIVESPEC_CLONE_STEP_LINE in overlay_text
    assert _DEV_TOOLING_CLONE_STEP_LINE in overlay_text
    assert _SIBLING_ENV_LINE in overlay_text
    # The canned fleet manifest registers the dispatch target itself
    # (basename "repo"); its clone step must be excluded — the sandbox
    # already holds that repo as the workspace clone.
    assert "github.com/thewoolleyman/repo" not in overlay_text


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


def test_dispatch_default_workflow_materializes_from_repo_fabro_tree(
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
    assert plan.workflow_toml.name == f"fabro-run-config-{item.id}.toml"
    overlay_text = fake.overlay_texts[0]
    assert "implement-work-item" in overlay_text
    assert 'graph = "workflow.fabro"' not in overlay_text
    # The repo's committed run config carries NO secret and NO
    # {{ env }} interpolation (a dead channel for server-mediated runs:
    # the worker env is allowlist-scrubbed); the overlay appends the env
    # table with the token from the Dispatcher's process env.
    assert _FAKE_TOKEN_LINE in overlay_text
    assert _ENV_INTERPOLATION_LITERAL not in overlay_text


def test_dispatch_blocked_outcome_surfaces_and_leaves_item_open(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    blocked = DispatchOutcome(
        work_item_id=item.id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run 01RUNBLOCKED parked at a human gate; answer with `fabro attach 01RUNBLOCKED`",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={item.id: blocked}))
    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "blocked at fabro-run" in out
    assert "fabro attach 01RUNBLOCKED" in out
    assert _stored()[item.id].status == "open"
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert '"blocked"' in journal_text
    assert "ledger-close" not in journal_text


def test_dispatch_fails_fast_when_oauth_token_env_is_absent_or_empty(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing CLAUDE_CODE_OAUTH_TOKEN refuses the dispatch outright:
    the Dispatcher's process env is the SOURCE of the run-scoped overlay
    projection, so absence means there is nothing to project into the
    sandbox. The error names the with-livespec-env.sh wrapper as the
    fix."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={}))
    base = ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    assert main(base) == 1
    out = capsys.readouterr().out
    assert "run-config-overlay" in out
    assert "CLAUDE_CODE_OAUTH_TOKEN" in out
    assert "with-livespec-env.sh" in out
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")
    assert main(base) == 1
    assert "with-livespec-env.sh" in capsys.readouterr().out
    assert _stored()[item.id].status == "open"


def test_dispatch_fails_when_workflow_config_is_not_materializable(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bare = tmp_path / "bare.toml"
    _ = bare.write_text("_version = 1\n", encoding="utf-8")
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={}))
    exit_code = main(["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(bare)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "run-config-overlay" in out
    assert _stored()[item.id].status == "open"


@dataclass(kw_only=True)
class _FakeManifestRunner:
    """Scripted ShellCommandRunner stand-in for the fleet-manifest fetch."""

    result: CommandResult
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        assert timeout_seconds > 0
        self.calls.append((argv, cwd))
        return self.result


def test_fetch_fleet_manifest_text_shells_gh_api_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production fetch is a HOST-SIDE `gh api` raw-content read of
    fleet-manifest.jsonc from livespec master at run-config generation
    time — the canonical fleet member registry, fetched the same way the
    other family consumers (fleet conformance, release fan-out) consume
    it."""
    fake = _FakeManifestRunner(
        result=CommandResult(exit_code=0, stdout=_FLEET_MANIFEST_TEXT, stderr="")
    )
    monkeypatch.setattr(dispatcher, "ShellCommandRunner", lambda: fake)
    assert _real_fetch_fleet_manifest_text() == _FLEET_MANIFEST_TEXT
    argv, _cwd = fake.calls[0]
    assert argv[:2] == ["gh", "api"]
    assert "Accept: application/vnd.github.raw" in argv
    assert argv[-1] == "repos/thewoolleyman/livespec/contents/fleet-manifest.jsonc"


def test_fetch_fleet_manifest_text_returns_none_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = _FakeManifestRunner(
        result=CommandResult(exit_code=1, stdout="", stderr="gh: HTTP 404")
    )
    monkeypatch.setattr(dispatcher, "ShellCommandRunner", lambda: failing)
    assert _real_fetch_fleet_manifest_text() is None
    empty = _FakeManifestRunner(result=CommandResult(exit_code=0, stdout="  \n", stderr=""))
    monkeypatch.setattr(dispatcher, "ShellCommandRunner", lambda: empty)
    assert _real_fetch_fleet_manifest_text() is None


def test_dispatch_fails_fast_when_fleet_manifest_is_unfetchable(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unfetchable fleet manifest refuses the dispatch with an
    actionable error: dispatching without sibling clones would
    reintroduce the in-sandbox `:no-justfile-resolved` aggregate failure
    for every cross-repo check, and silently falling back to a hardcoded
    member list would rot as the fleet changes."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={}))
    monkeypatch.setattr(
        "livespec_impl_beads.commands.dispatcher._fetch_fleet_manifest_text",
        lambda: None,
    )
    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "run-config-overlay" in out
    assert "fleet-manifest.jsonc" in out
    assert "gh api" in out
    assert _stored()[item.id].status == "open"


def test_dispatch_fails_fast_when_fleet_manifest_is_malformed(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={}))
    monkeypatch.setattr(
        "livespec_impl_beads.commands.dispatcher._fetch_fleet_manifest_text",
        lambda: "not a fleet manifest {{",
    )
    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "run-config-overlay" in out
    assert "fleet-manifest.jsonc" in out
    assert _stored()[item.id].status == "open"


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


# ---------------------------------------------------------------------------
# bn4 — ledger comments in the goal, sizing warnings, long-haul fabro budget
# ---------------------------------------------------------------------------


def test_render_goal_renders_labeled_comments_section(tmp_path: Path) -> None:
    """Comments are operator riders (finding (c) of bn4): they must reach the
    sandbox brief under a clearly-labeled section, with per-entry provenance
    when the record carries it."""
    comments = (
        WorkItemComment(text="first rider", author="operator", created_at="2026-06-12T00:00:00Z"),
        WorkItemComment(text="author only", author="operator", created_at=None),
        WorkItemComment(text="date only", author=None, created_at="2026-06-13T00:00:00Z"),
        WorkItemComment(text="bare", author=None, created_at=None),
    )
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/t", comments=comments)
    assert "Ledger comments" in goal
    assert "treat them as part of the brief" in goal
    assert "[1] (operator, 2026-06-12T00:00:00Z) first rider" in goal
    assert "[2] (operator) author only" in goal
    assert "[3] (2026-06-13T00:00:00Z) date only" in goal
    assert "[4] bare" in goal


def test_render_goal_omits_comments_section_when_none(tmp_path: Path) -> None:
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert "Ledger comments" not in goal


# MiniJinja's three opening delimiters: expression `{{`, statement `{%`,
# comment `{#`. Fabro renders the run goal through MiniJinja (the graph's
# `goal` attribute) and into the prompts as `{{ goal }}`, so any one of
# these in untrusted item prose would re-enter template mode and the
# undefined name would raise `template_undefined_variable` at validation
# (livespec-impl-beads-ajv: three v5k-leg dispatches failed pre-flight on
# justfile recipe `{{ }}` syntax in the description). The escape
# neutralizes the OPENING delimiters, so the lexer never enters a tag.
_MINIJINJA_OPENERS = ("{{", "{%", "{#")


def _live_minijinja_openers(*, rendered: str) -> list[str]:
    """Return MiniJinja openers still LIVE in `rendered` after stripping the
    literal-emitting escape expressions render_goal inserts.

    render_goal neutralizes each opener into a literal-emitting expression
    that ALWAYS opens with `{{` (only `{{ ... }}` emits a value): `{{` ->
    `{{ "{{" }}`, `{%` -> `{{ "{%" }}`, `{#` -> `{{ "{#" }}`. Removing every
    such escape expression must leave NO opener behind: any `{{`/`{%`/`{#`
    that survives the strip is a live template construct that would
    re-enter template mode and raise `template_undefined_variable` at
    validation. Stripping the full expressions first is necessary because
    each escape itself contains the two literal opener characters inside
    its quoted string.
    """
    stripped = rendered
    for opener in _MINIJINJA_OPENERS:
        stripped = stripped.replace(f'{{{{ "{opener}" }}}}', "")
    return [opener for opener in _MINIJINJA_OPENERS if opener in stripped]


def test_render_goal_escapes_minijinja_delimiters_in_arbitrary_prose(tmp_path: Path) -> None:
    """Untrusted item prose (justfile `{{ }}`, statement/comment tags, a raw-block
    breaker, backslashes, quotes, newlines) must NOT survive into the rendered goal
    as live MiniJinja syntax — otherwise fabro raises `template_undefined_variable`
    in graph attribute `goal` (livespec-impl-beads-ajv). The escape neutralizes
    every opening delimiter into a literal-emitting expression; fabro renders those
    back to the original text, so no live `{{`/`{%`/`{#` remains."""
    adversarial = (
        'recipe target: just {{ build_dir }} && echo "go"\n'
        "stmt {% if x %}body{% endif %} comment {# note #}\n"
        "raw-block breaker {% endraw %} then {{ another }}\n"
        "backslash \\ path C:\\tmp and nested {{ {{ inner }} }}"
    )
    item = _item(title="curly {{ title_var }} bug", description=adversarial)
    comments = (WorkItemComment(text="rider with {{ comment_var }}", author=None, created_at=None),)
    goal = render_goal(item=item, repo=tmp_path, branch="feat/t", comments=comments)
    assert _live_minijinja_openers(rendered=goal) == []
    # The escape is literal-emitting (not lossy): each neutralized opener
    # is still present as the start of its escape expression.
    assert '{{ "{{" }}' in goal
    assert '{{ "{%" }}' in goal
    assert '{{ "{#" }}' in goal


def test_item_sizing_warnings_empty_for_small_item() -> None:
    assert item_sizing_warnings(item=_item()) == ()


def test_item_sizing_warnings_flags_long_description() -> None:
    [warning] = item_sizing_warnings(item=_item(description="y" * 1501))
    assert "1501" in warning
    assert "splitting" in warning


def test_item_sizing_warnings_flags_multi_part_marker() -> None:
    [warning] = item_sizing_warnings(item=_item(title="A multi-RGR refactor"))
    assert "multi-part/multi-RGR" in warning


def test_item_sizing_warnings_flags_enumerated_parts() -> None:
    enumerated = _item(description="Do (1) the first, (2) the second, (3) the third thing.")
    [warning] = item_sizing_warnings(item=enumerated)
    assert "3 enumerated parts" in warning
    two_parts = _item(description="Do (1) the first and (2) the second thing.")
    assert item_sizing_warnings(item=two_parts) == ()


def test_fabro_run_uses_long_haul_subprocess_timeout(tmp_path: Path) -> None:
    """The foreground `fabro run` subprocess budget must outlive the
    worst-case phase graph (implement 2x14400s + janitor 3x3600s +
    fix 2x3600s + pr 2x1800s = 50400s) plus provisioning slack; a budget
    below the graph's own ceiling kills the CLI mid-run."""
    runner = _FakeRunner(queue=[_err()])
    outcome, _journal, _naps = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "failed"
    assert runner.timeouts[0] == 54000.0


def test_dispatch_goal_text_carries_ledger_comments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding (c) of bn4: rider instructions added as ledger comments must
    arrive in the sandbox goal text (the dispatcher previously rendered the
    description only, so pre-authorizations never reached the agent)."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    client.seed_comment(
        issue_id=item.id,
        text="pre-authorization: also bump the dev-tooling pin",
        author="operator",
        created_at="2026-06-12T08:00:00Z",
    )
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
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    goal_text = (tmp_path / f"fabro-goal-{item.id}.md").read_text(encoding="utf-8")
    assert "Ledger comments" in goal_text
    assert "pre-authorization: also bump the dev-tooling pin" in goal_text
    assert "(operator, 2026-06-12T08:00:00Z)" in goal_text


def test_dispatch_fails_at_ledger_comments_stage_when_read_raises(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed comments read refuses the dispatch (error-as-data at the
    `ledger-comments` stage) instead of proceeding comment-blind — silently
    dropping riders is exactly the bug this stage exists to prevent."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={}))

    def _boom(*, path: StoreConfig, work_item_id: str) -> tuple[WorkItemComment, ...]:
        _ = (path, work_item_id)
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="connection lost")

    monkeypatch.setattr(
        "livespec_impl_beads.commands.dispatcher.read_work_item_comments",
        _boom,
    )
    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "ledger-comments" in out
    assert "BeadsCommandError" in out
    assert _stored()[item.id].status == "open"


def test_dispatch_warns_on_oversized_item_without_blocking(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sizing heuristics are WARN-only (journal record + stderr line): an
    oversized item still dispatches — the dispatcher never blocks on them."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(description="multi-RGR scope: " + "z" * 1600)
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
    err = capsys.readouterr().err
    assert "WARN: item-sizing" in err
    assert item.id in err
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    sizing = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "sizing-warn"
    )
    assert sizing["work_item_id"] == item.id
    assert len(sizing["warnings"]) == 2


# --------------------------------------------------------------------------
# Loop-exit reflection stage wiring (work-item 29f.2). The stage runs AFTER
# the verdict is computed and is immutable by it (best-practices §6).
# --------------------------------------------------------------------------


def test_loop_runs_reflection_stage_after_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    _dispatcher_reflection.reset_auto_trip()
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="a-1", priority=1)
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1")})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    reflection_rec = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "reflection"
    )
    assert reflection_rec["mode"] == "observe"
    assert reflection_rec["green_count"] == 1
    # The OTLP spans land in the journal's sibling spans file.
    spans_path = repo / "tmp" / "fabro-dispatch-journal-reflection-spans.jsonl"
    assert spans_path.is_file()


def test_loop_reflection_failure_never_changes_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reflection that raises must NOT alter the loop's exit code: the
    verdict is computed before the fail-open stage runs (best-practices
    §6). `reflect` is itself fail-open, but even a hypothetical raise out
    of it is contained because the exit code is already decided — the
    patched raise here proves reflect is the LAST thing the loop does,
    after the green verdict is already computed."""
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    _dispatcher_reflection.reset_auto_trip()
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="a-1", priority=1)
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1")})
    monkeypatch.setattr(dispatcher, "run_dispatch", fake)

    def _boom(**_kwargs: object) -> None:
        raise RuntimeError("reflection blew up")

    monkeypatch.setattr(dispatcher, "reflect", _boom)
    with pytest.raises(RuntimeError, match="reflection blew up"):
        _ = main(
            [
                "loop",
                "--repo",
                str(repo),
                "--budget",
                "1",
                "--mode",
                "autonomous",
                "--workflow",
                str(workflow),
                "--no-close-on-merge",
            ]
        )


def test_dispatch_runs_reflection_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    _dispatcher_reflection.reset_auto_trip()
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
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert any(json.loads(line)["stage"] == "reflection" for line in journal_text.splitlines())


# ---------------------------------------------------------------------------
# Dispatcher drain order composes the `next` ranking authority (i3jiny).
#
# The `next` ranker and the Fabro Dispatcher share the readiness filter
# (`_cross_repo.is_item_ready`) but historically DIVERGED on sort: `next`
# ranked `(priority, origin_rank, captured_at, id)` while `_ready_items`
# dropped the gap-tied preference and the FIFO `captured_at` ordering,
# sorting only `(priority, id)`. Under the dark factory's concurrency cap +
# budget + merge backpressure, drain ORDER decides which ready items run, so
# the Dispatcher silently starved gap-tied and older work relative to the
# policy `next` advertises as authoritative. Both now compose the single
# shared `_cross_repo.ready_sort_key`.
# ---------------------------------------------------------------------------


def test_ready_items_drain_order_equals_next_ranking(tmp_path: Path) -> None:
    # Equal-priority, mixed-origin, differing-captured_at fixture constructed
    # so the OLD `(priority, id)` sort orders them DIFFERENTLY from the
    # canonical `(priority, origin_rank, captured_at, id)` ranking.
    fixture = [
        _item(
            id="li-aaa",
            origin="freeform",
            gap_id=None,
            captured_at="2026-06-15T00:00:00Z",
        ),
        _item(
            id="li-bbb",
            origin="gap-tied",
            gap_id="G1",
            captured_at="2026-06-10T00:00:00Z",
        ),
        _item(
            id="li-ccc",
            origin="freeform",
            gap_id=None,
            captured_at="2026-06-01T00:00:00Z",
        ),
    ]
    # tmp_path has no `.livespec.jsonc`, so `_ready_items` sees an empty
    # cross-repo manifest and every open, dependency-free item is ready.
    drain_order = [item.id for item in _ready_items(items=fixture, repo=tmp_path)]
    next_order = [c["work_item_ref"] for c in next_command.rank_candidates(items=fixture)]
    assert drain_order == next_order
    # Pin the canonical order explicitly: gap-tied first, then freeform FIFO
    # by captured_at (oldest first). The OLD `(priority, id)` sort would have
    # produced `["li-aaa", "li-bbb", "li-ccc"]`.
    assert drain_order == ["li-bbb", "li-ccc", "li-aaa"]
