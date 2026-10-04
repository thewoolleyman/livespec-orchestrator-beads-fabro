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
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
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
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, comments: str, item: WorkItem
) -> _Dispatched:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording())
    _patch_acceptance_pass(monkeypatch=monkeypatch, comments=comments)
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    return _Dispatched(
        exit_code=exit_code,
        records=_journal_records(repo=repo),
        repo=repo,
        workflow=workflow,
    )


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
