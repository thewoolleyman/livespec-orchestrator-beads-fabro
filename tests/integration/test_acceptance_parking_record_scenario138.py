"""Integration-tier acceptance for the PARKING half of Scenario 138.

Binds the acceptance sub-scenarios of `SPECIFICATION/scenarios.md` "Scenario 138
— A proof finding reaches the fix stage, and a parked acceptance verdict is
recorded with its reason and its pointer": "A parking verdict is recorded and
reported honestly", "An unchanged re-run appends nothing", "A changed pending-leg
set is recorded once", "A parked PASS reports green at acceptance, not at done",
"Only a closed item reports done", and "A missing pointer on a verified item is
surfaced and repaired". The ratified rule is the parking-verdict clause of the
post-merge acceptance section of `SPECIFICATION/contracts.md`.

Every case drives a REAL command-line entry point — `dispatcher.main(argv=
["dispatch", ...])`, `dispatcher.main(argv=["reconcile-merged", ...])` and
`needs_attention.main(argv=[...])` — against the in-memory `FakeBeadsClient`
(`LIVESPEC_BEADS_FAKE=1`), which is this repository's hermetic ledger surface.
Two seams are stood in and nothing else: `run_dispatch`, so no factory sandbox
launches, and the `CommandRunner` each surface shells its forge reads through, so
no `gh` / `git` subprocess runs. The verdict, the disposition, the parking
record, the pointer write and every ledger read-back are production code.

THE COMMENTS ARE READ BACK THROUGH `bd comments`, never through `bd show`. The
show surface carries only `comment_count` and no bodies at all, so a test that
verified the write through it would report every successful append as lost — the
trap `CLAUDE.md` records. `read_work_item_comments` is the store's own
`bd comments --json` seam and indexes `text`, which is the key the body actually
lives under.
"""

from __future__ import annotations

import json
import tempfile
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_completion,
    _dispatcher_loop,
    needs_attention,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    AcceptancePassResult,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)
_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)

_RUN_ID = "01M3PARKRUN"
# The dispatch id is a uuid4 hex per invocation, and the proof leg's own reason
# NAMES every identifier it would accept a record under — so it reaches the
# parking record and an unpinned one would make the comment unassertable. Pinning
# it is also the only way the attribution leg stays a FACT of these cases rather
# than a value that differs per run.
_DISPATCH_ID = "0d15pa7c4de7e8f900000000000138aa"
_PR_NUMBER = 11
_MERGE_SHA = "feed01"
_ASSERTION = "The dispatched slice lands its change."
# Shares no significant term with the assertion, so a vocabulary match could
# never be what produced a PASS here: the proof record is the only evidence leg.
_READABLE_DIFF = "diff --git a/impl.py b/impl.py\n+rearranged an unrelated helper\n"
_RECORD_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-700"
_PARKING_TITLE = "Acceptance parking record"


def _definition_of_done() -> str:
    return textwrap.dedent(f"""\
        Implement the slice.

        ## Definition of Done

        - {_ASSERTION}

        References: ## Effective acceptance criteria
        """)


def _record_body(*, verdict: str) -> str:
    return textwrap.dedent(f"""\
        Proof of Done — {verdict} — run {_RUN_ID} — 2026-10-01T09:00:00Z

        ## Assertion 1 — {_ASSERTION}

        Proof mode: `factory_captured`

        Reproduced: yes.
        """)


def _comments_payload(*, bodies: Sequence[str]) -> str:
    return json.dumps({"comments": [{"url": _RECORD_URL, "body": body} for body in bodies]})


@dataclass(kw_only=True)
class _ForgeRunner:
    """The acceptance pass's command seam: the merged diff and the PR's comments."""

    comments: str
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
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        if "comments" in argv:
            return CommandResult(exit_code=0, stdout=self.comments, stderr="")
        return CommandResult(exit_code=0, stdout=_READABLE_DIFF, stderr="")


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("fabro-parking-record")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_launch.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    # Pinned at the ONE source rather than at a consumer: the pre-run claim in
    # `_dispatcher_admission` mints the dispatch id and the lock it writes is what
    # `dispatch_one` then reads, so patching `dispatch_one`'s own re-export leaves
    # the minted id untouched and the pin silently does nothing.
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_self_update.run_id",
        lambda: _DISPATCH_ID,
    )
    # The reconcile valve resolves its janitor checkout under `Path.home()`, and
    # claims a REAL lock file beside it. Every case here reuses one repo dir name
    # and one item id, so `tmp_path` isolation alone does not separate them under
    # `pytest -n`: the loser of the claim gets `janitor-env-degraded` with exit 1,
    # a flake whose message describes a host problem rather than the collision.
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


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
        id="bd-ib-parkrecord",
        type="task",
        status="pending-approval",
        title="A dispatched slice",
        description=_definition_of_done(),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"compat": {"pinned": "master"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _green_recording() -> Callable[..., DispatchOutcome]:
    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=_PR_NUMBER,
            merge_sha=_MERGE_SHA,
            detail="merged",
            fabro_run_id=_RUN_ID,
        )

    return _run_dispatch


def _acceptance_pass_over(*, runner: _ForgeRunner) -> Callable[..., AcceptancePassResult]:
    """The REAL acceptance pass, with only its command seam stood in."""

    def _call(
        *,
        repo: Path,
        item: WorkItem,
        outcome: DispatchOutcome,
        raw_labels: Sequence[str] = (),
        journal_path: Path | None = None,
    ) -> AcceptancePassResult:
        return run_acceptance_pass(
            repo=repo,
            item=item,
            outcome=outcome,
            runner=runner,
            raw_labels=raw_labels,
            journal_path=journal_path,
        )

    return _call


@dataclass(frozen=True, kw_only=True)
class _Dispatched:
    exit_code: int
    records: list[dict[str, object]]
    repo: Path
    workflow: Path


def _dispatch(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    comments: str,
    item: WorkItem,
    as_json: bool = False,
) -> _Dispatched:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording())
    _patch_acceptance_pass(monkeypatch=monkeypatch, comments=comments)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            *(["--json"] if as_json else []),
        ]
    )
    return _Dispatched(
        exit_code=exit_code,
        records=_journal_records(repo=repo),
        repo=repo,
        workflow=workflow,
    )


def _emitted(*, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """The ONE dispatch result the `--json` envelope carried."""
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    first = payload[0]
    assert isinstance(first, dict)
    return first


def _reconcile(
    *,
    repo: Path,
    item_id: str,
    comments: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, _ReconcileRunner]:
    """Drive the REAL `reconcile-merged` supervisor over the re-accept arm.

    Its runner is handed exactly the two commands this arm may issue — the
    default-branch probe the plan resolves its contract from, and the pull-request
    resolution — so the clause's FIRST requirement, that the post-merge janitor is
    NOT re-run, is read off the seam. A janitor that ran and passed would exit 0
    too, which is why the call list and not the exit code is the evidence.
    """
    runner = _ReconcileRunner(
        queue=[
            CommandResult(exit_code=0, stdout="origin/master", stderr=""),
            CommandResult(exit_code=0, stdout=_merged_pr_json(), stderr=""),
        ]
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged"
        ".ShellCommandRunner",
        lambda: runner,
    )
    _patch_acceptance_pass(monkeypatch=monkeypatch, comments=comments)
    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item_id, "--json"])
    return exit_code, runner


def _merged_pr_json() -> str:
    return json.dumps(
        {
            "number": _PR_NUMBER,
            "state": "MERGED",
            "autoMergeRequest": {},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": _MERGE_SHA},
            "statusCheckRollup": [],
        }
    )


@dataclass(kw_only=True)
class _ReconcileRunner:
    """The reconcile valve's own shell seam, with its full call list recorded."""

    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env
        self.calls.append(list(argv))
        return self.queue.pop(0)


def _patch_acceptance_pass(*, monkeypatch: pytest.MonkeyPatch, comments: str) -> None:
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        _acceptance_pass_over(runner=_ForgeRunner(comments=comments)),
        raising=False,
    )


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _record(*, records: list[dict[str, object]], stage: str) -> dict[str, object]:
    return next(one for one in records if one.get("stage") == stage)


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _parking_comments(*, item_id: str) -> list[str]:
    """Every parking-record comment body on the item, oldest first."""
    return [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=item_id)
        if comment.text.startswith(_PARKING_TITLE)
    ]


def test_a_needs_attention_park_records_its_verdict_every_leg_and_the_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 138 — "A parking verdict is recorded and reported honestly".

    The pull request carries a `captured` record for the merging run and no
    `verified` one, so the single factory-captured assertion is UNEVIDENCED and
    the pass parks on NEEDS_ATTENTION. The record the park writes is asserted
    LINE BY LINE rather than by containment, because a comment that merely
    mentioned the verdict would satisfy an `in` check while telling an operator
    nothing about which leg failed to observe what, or what to do about it — and
    those three facts are exactly what the clause requires of it.

    The discriminating control is the `captured` record itself: it NAMES the
    assertion and says `Reproduced: yes.`, so a build that recorded the park
    without reading the verdict's own absent set would report the proof leg as
    OBSERVED here.
    """
    item = _item()

    dispatched = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="captured")]),
        item=item,
    )

    assert _stored()[item.id].status == "acceptance"
    assert _record(records=dispatched.records, stage="acceptance-ai-pass")["verdict"] == (
        "NEEDS_ATTENTION"
    )
    comments = _parking_comments(item_id=item.id)
    assert len(comments) == 1
    pending_leg = f"proof of done record for {_ASSERTION!r}"
    assert comments[0].splitlines() == [
        f"{_PARKING_TITLE} — NEEDS_ATTENTION — pending: {pending_leg}",
        "",
        f"The acceptance pass left work-item {item.id} resting in acceptance under"
        " acceptance_policy ai-only; it disposed of nothing.",
        "",
        "Evidence legs:",
        "",
        "- telemetry: OBSERVED — green merged dispatch with PR and merge sha",
        "- merged diff: OBSERVED — pull request diff read",
        "- effective criteria: OBSERVED — 0 assertion(s) reached a graded check",
        f"- proof of done record: NOT OBSERVED — pull request #{_PR_NUMBER} records read"
        f" for run {_RUN_ID} or {_DISPATCH_ID}",
        "",
        "Pending, and the action that would move the item:",
        "",
        f"- {pending_leg}: Publish a Proof of Done record whose first line names verified"
        f" on pull request #{_PR_NUMBER}, listing this assertion as reproduced, then re-run"
        " the acceptance pass with `dispatcher.py reconcile-merged --repo <repo> --item"
        f" {item.id} --invoker <role:name>`.",
    ]
    written = _record(records=dispatched.records, stage="acceptance-parking-record")
    assert written["acceptance_verdict"] == "NEEDS_ATTENTION"
    assert written["pending"] == [pending_leg]


def test_a_needs_attention_park_reports_needs_attention_at_acceptance_and_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario 138 — "the dispatch result reports ... and the dispatcher exits 1".

    This is the half of finding F7(b) the parking comment cannot fix: the item was
    already parked and already unjudgeable, and `drive` reported `green at done`
    anyway — so every surface downstream of the exit code read the dispatch as a
    completed close. All three result fields plus the exit code are asserted
    together, because each alone is consistent with the old build: `stage` stayed
    `done` while `status` stayed `green`, and an exit code of 1 with a `green`
    payload would be its own contradiction.
    """
    item = _item(id="bd-ib-parkresult")

    dispatched = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="captured")]),
        item=item,
        as_json=True,
    )

    assert dispatched.exit_code == 1
    emitted = _emitted(capsys=capsys)
    assert (emitted["status"], emitted["stage"], emitted["verdict"]) == (
        "needs-attention",
        "acceptance",
        "NEEDS_ATTENTION",
    )
    # The merge is still reported: the run DID merge, and an operator triaging the
    # park needs the pull request the records live on.
    assert (emitted["pr_number"], emitted["merge_sha"]) == (_PR_NUMBER, _MERGE_SHA)
    assert _stored()[item.id].status == "acceptance"


@pytest.mark.parametrize(
    ("policy", "expected_stage", "expected_status"),
    [("ai-then-human", "acceptance", "green"), ("ai-only", "done", "green")],
)
def test_only_a_closed_item_reports_done_and_a_parked_pass_reports_acceptance(
    policy: str,
    expected_stage: str,
    expected_status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario 138 — "A parked PASS reports green at acceptance, not at done".

    The two cases are the SAME item, the SAME verified record and the SAME verdict;
    the only difference is the policy, and therefore whether the pass closed the
    item. Neither case means anything alone — the parked one would pass against a
    build that reported `acceptance` for everything, and the closed one against a
    build that still reported `done` for everything.
    """
    item = _item(id=f"bd-ib-parked-{policy}", acceptance_policy=policy)

    dispatched = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="verified")]),
        item=item,
        as_json=True,
    )

    assert dispatched.exit_code == 0
    emitted = _emitted(capsys=capsys)
    assert (emitted["status"], emitted["stage"], emitted["verdict"]) == (
        expected_status,
        expected_stage,
        "PASS",
    )
    closed = expected_stage == "done"
    assert _stored()[item.id].status == ("done" if closed else "acceptance")
    # The PARKED case carries its record naming the human valve; the CLOSED case
    # carries none at all, because nothing parked.
    comments = _parking_comments(item_id=item.id)
    if closed:
        assert comments == []
        return
    assert len(comments) == 1
    assert comments[0].splitlines()[0] == f"{_PARKING_TITLE} — PASS — pending: nothing"
    assert comments[0].splitlines()[-1] == (
        f"- nothing is pending: the human `accept:{item.id}` valve moves the item to done,"
        f" and `reject:{item.id}:rework` returns it to active."
    )


def test_reconcile_merged_re_runs_only_acceptance_repairs_the_pointer_and_records_each_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario 138 — the re-accept arm, the pointer repair, and both idempotence arms.

    One item carries all four claims because they are one sequence and the later
    ones are only meaningful against the earlier: the dispatch parks on
    NEEDS_ATTENTION with no pointer, the FIRST reconcile re-runs the pass against
    the unchanged records and must append nothing, and the SECOND reconcile — with
    a `verified` record now on the pull request — must record exactly one new
    comment for the changed pending-leg set and write the pointer that was skipped.

    Splitting them would lose the discriminator. "No second comment" proves
    idempotence only beside a run that DOES append, and "the pointer was written"
    proves repair only beside the park that had none.
    """
    item = _item(id="bd-ib-parkreaccept", acceptance_policy="ai-then-human")
    unchanged = _comments_payload(bodies=[_record_body(verdict="captured")])

    dispatched = _dispatch(
        tmp_path=tmp_path, monkeypatch=monkeypatch, comments=unchanged, item=item, as_json=True
    )
    _ = capsys.readouterr()

    assert dispatched.exit_code == 1
    assert "## Proof of Done" not in _stored()[item.id].description
    assert len(_parking_comments(item_id=item.id)) == 1

    first_exit, first_runner = _reconcile(
        repo=dispatched.repo, item_id=item.id, comments=unchanged, monkeypatch=monkeypatch
    )
    _ = capsys.readouterr()

    # The arm issued ONLY the plan's default-branch probe and the pull-request
    # resolution: no checkout, no preclean, no check-suite run.
    assert [call[0] for call in first_runner.calls] == ["git", "gh"]
    assert first_exit == 1
    assert len(_parking_comments(item_id=item.id)) == 1
    reconcile_records = _journal_records(repo=dispatched.repo)
    assert (
        _record(records=reconcile_records, stage="acceptance-parking-record-unchanged")[
            "acceptance_verdict"
        ]
        == "NEEDS_ATTENTION"
    )
    assert not [
        one for one in reconcile_records if str(one.get("stage", "")).startswith("janitor-")
    ]

    second_exit, _ = _reconcile(
        repo=dispatched.repo,
        item_id=item.id,
        comments=_comments_payload(bodies=[_record_body(verdict="verified")]),
        monkeypatch=monkeypatch,
    )
    emitted = _emitted(capsys=capsys)

    assert second_exit == 0
    assert (emitted["status"], emitted["stage"], emitted["verdict"]) == (
        "green",
        "acceptance",
        "PASS",
    )
    comments = _parking_comments(item_id=item.id)
    assert [one.splitlines()[0] for one in comments] == [
        f"{_PARKING_TITLE} — NEEDS_ATTENTION — pending: proof of done record for {_ASSERTION!r}",
        f"{_PARKING_TITLE} — PASS — pending: nothing",
    ]
    # The pointer the park skipped is now written, at the record this pass graded.
    description = _stored()[item.id].description
    head, _, pointer = description.partition("## Proof of Done")
    assert head.rstrip("\n") == _definition_of_done().rstrip("\n")
    assert pointer.splitlines()[1:] == [
        "",
        f"- Pull request: #{_PR_NUMBER}",
        f"- Verified record: {_RECORD_URL}",
        f"- Run: {_RUN_ID}",
        "- Timestamp: 2026-10-01T09:00:00Z",
        "- Verdict: verified",
    ]


def _attention_ids(
    *,
    repo: Path,
    comments: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> list[str]:
    """Every attention fact id the REAL `needs-attention` CLI emits for the repo.

    Two seams are stood in. `spec_next` is the spec-side read, which this fixture
    has no spec tree for and which no claim here depends on. The missing-pointer
    lane's own shell runner is the forge read — the lane's whole question is what
    records the pull request carries, and that is the only external call it makes.
    """
    monkeypatch.setattr(needs_attention, "spec_next", lambda **_: None)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_missing_pointer"
        ".ShellCommandRunner",
        lambda: _ForgeRunner(comments=comments),
    )
    assert (
        needs_attention.main(
            argv=["--project-root", str(repo), "--repo-name", "repo", "--skip-hygiene", "--json"]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    return [str(one["id"]) for one in payload["attention"]]


def test_needs_attention_reports_a_verified_item_in_acceptance_carrying_no_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario 138 — "A missing pointer on a verified item is surfaced".

    The subject is built by a REAL dispatch that parks with no pointer, which is
    the shape finding F7(b) measured: the pass could not see a `verified` record
    at the time, one landed afterwards, and nothing then reported that the item
    was carrying no pointer. Three controls bound the lane, each disqualifying a
    cheaper implementation that would satisfy the positive case:

    - a `captured`-only pull request yields NO fact, so the lane keys on the
      VERIFIED record rather than on "parked without a pointer";
    - a second item resting in `acceptance` whose description already CARRIES a
      pointer yields no fact in the same snapshot, so the lane keys on the
      pointer's absence rather than on the status; and
    - the fact CLEARS once `reconcile-merged` writes the pointer, so "the fact
      appeared" is not simply "the fact always appears".
    """
    item = _item(id="bd-ib-parkpointer", acceptance_policy="ai-then-human")
    dispatched = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="captured")]),
        item=item,
    )
    _ = capsys.readouterr()
    # A sibling resting in `acceptance` whose pointer already stands: the lane
    # must not report it, and it is in every snapshot below.
    append_work_item(
        path=_config(),
        item=replace(
            _item(id="bd-ib-parkpointed"),
            status="acceptance",
            description=_definition_of_done() + _pointer_section(),
        ),
    )
    fact_id = f"hygiene:missing-proof-pointer:{item.id}"

    captured_only = _attention_ids(
        repo=dispatched.repo,
        comments=_comments_payload(bodies=[_record_body(verdict="captured")]),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    verified = _attention_ids(
        repo=dispatched.repo,
        comments=_comments_payload(bodies=[_record_body(verdict="verified")]),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert fact_id not in captured_only
    assert [one for one in verified if one.startswith("hygiene:missing-proof-pointer:")] == [
        fact_id
    ]

    exit_code, _ = _reconcile(
        repo=dispatched.repo,
        item_id=item.id,
        comments=_comments_payload(bodies=[_record_body(verdict="verified")]),
        monkeypatch=monkeypatch,
    )
    _ = capsys.readouterr()
    repaired = _attention_ids(
        repo=dispatched.repo,
        comments=_comments_payload(bodies=[_record_body(verdict="verified")]),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert exit_code == 0
    assert "## Proof of Done" in _stored()[item.id].description
    assert [one for one in repaired if one.startswith("hygiene:missing-proof-pointer:")] == []


def test_the_missing_pointer_fact_names_the_item_the_pull_request_and_the_remedy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The clause requires the fact to NAME the item and the pull request.

    Read off the composed fact rather than off the lane, because the envelope's
    own conformance rules bind what a row may carry, and a summary naming neither
    would still be a well-formed row. The handoff is asserted to be the remedy the
    same clause names — `reconcile-merged` for this item — since that is the one
    command the fact says will repair it.
    """
    item = _item(id="bd-ib-parkpointerfact", acceptance_policy="ai-then-human")
    dispatched = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="captured")]),
        item=item,
    )
    _ = capsys.readouterr()

    monkeypatch.setattr(needs_attention, "spec_next", lambda **_: None)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_missing_pointer"
        ".ShellCommandRunner",
        lambda: _ForgeRunner(comments=_comments_payload(bodies=[_record_body(verdict="verified")])),
    )
    facts = [
        fact
        for fact in needs_attention.build_attention(
            project_root=dispatched.repo, repo_name="repo", include_hygiene=False
        )
        if fact.id == f"hygiene:missing-proof-pointer:{item.id}"
    ]

    assert len(facts) == 1
    fact = facts[0]
    assert fact.kind == "hygiene"
    assert item.id in fact.summary
    assert f"#{_PR_NUMBER}" in fact.summary
    assert fact.source_ref is not None
    assert fact.source_ref.work_item == item.id
    assert fact.handoff is not None
    assert f"reconcile-merged --repo {dispatched.repo} --item {item.id}" in fact.handoff.command


def _pointer_section() -> str:
    return (
        "\n## Proof of Done\n"
        "\n"
        f"- Pull request: #{_PR_NUMBER}\n"
        f"- Verified record: {_RECORD_URL}\n"
        f"- Run: {_RUN_ID}\n"
        "- Timestamp: 2026-10-01T09:00:00Z\n"
        "- Verdict: verified\n"
    )
