"""Integration-tier acceptance for the parts of Scenario 136 this slice delivers.

Binds the sub-scenarios of `SPECIFICATION/scenarios.md` "Scenario 136 — A
host-captured assertion holds the item in acceptance until an independent host
replay verifies it against the released build" that requirement carrier R2's
first slice lands: "A Host-captured sub-heading without a Reason line blocks
ready", the parking half of "The item is admitted under ai-only and parks after
merge with the host leg pending", and "The accept valve refuses while the host
leg is pending". The ratified rules are the per-assertion-proof-mode and
derived-routing clauses of the effective-acceptance-criteria section of
`SPECIFICATION/contracts.md`, and the host-captured leg of its post-merge
acceptance section.

WHAT THIS FILE DOES NOT BIND, and why the heading's coverage row therefore stays
a TODO. Scenario 136 also states the host-record POSTING primitive, the
identity-independence refusal, the release-containment check, the
`host_not_reproduced` FAIL route, and the `reconcile-merged` re-run that closes
the item — all of which need the primitive that publishes a host record, which is
the next slice's deliverable. A row claiming the heading from this file would
report eight unexercised sub-scenarios as covered.

EVERY CASE DRIVES A REAL COMMAND-LINE ENTRY POINT — `drive.main(argv=["--action",
"approve:<id>"])`, `dispatcher.main(argv=["dispatch", ...])` and
`drive.main(argv=["--action", "accept:<id>"])` — against the in-memory
`FakeBeadsClient` (`LIVESPEC_BEADS_FAKE=1`), which is this repository's hermetic
ledger surface. Two seams are stood in and nothing else: `run_dispatch`, so no
factory sandbox launches, and the `CommandRunner` each surface shells its forge
reads through, so no `gh` / `git` subprocess runs. The parse, the wall, the
verdict, the parking record and every ledger read-back are production code.

THE PARKING COMMENT IS READ BACK THROUGH `bd comments`, never through `bd show`.
The show surface carries only `comment_count` and no bodies at all, so a test
that verified the write through it would report every successful append as lost.
`read_work_item_comments` is the store's own `bd comments --json` seam and indexes
`text`, which is the key the body actually lives under.
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
    drive,
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
from livespec_orchestrator_beads_fabro.commands.dispatcher import main as dispatcher_main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-hostleg"
_INVOKER = "human:cw"
_RUN_ID = "01M3HOSTLEGRUN"
# A uuid4 hex per invocation otherwise, and the proof leg's own reason NAMES every
# identifier it would accept a record under — so an unpinned id reaches the
# parking record and makes the comment unassertable.
_DISPATCH_ID = "0d15pa7c4de7e8f900000000000136aa"
_PR_NUMBER = 36
_MERGE_SHA = "ho57c0"
_FACTORY_ASSERTION = "The dispatch result reports the parked verdict."
_HOST_ASSERTION = "The released build resolves the host mode on an operator host."
_HOST_REASON = "the proof needs the released build installed on an operator host."
# Shares no significant term with either assertion, so a merged-diff vocabulary
# match could never be what produced a PASS here: the proof record is the only
# evidence leg a mode-declaring item has.
_READABLE_DIFF = "diff --git a/impl.py b/impl.py\n+rearranged an unrelated helper\n"
_RECORD_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-900"
_PARKING_TITLE = "Acceptance parking record"
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
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


def _definition_of_done(*, reason: bool = True) -> str:
    """One factory bullet plus one host bullet, with the `Reason:` line optional.

    The factory bullet is the control for every case below: a parse or a routing
    decision that applied the host mode to the WHOLE section would satisfy a check
    on the host bullet alone, and the item would then rest for a leg its other
    assertion never needed.
    """
    # Assembled by concatenation rather than through `textwrap.dedent`: a
    # multi-line interpolation into an indented template contributes an
    # unindented line, which makes the common prefix empty and leaves EVERY
    # heading indented. An indented `## Definition of Done` is not a heading, so
    # the item reads as carrying no section at all — a refusal that names the
    # wrong fault and passes a check on the refusal's mere presence.
    stated = f"Reason: {_HOST_REASON}\n\n" if reason else ""
    return (
        "Deliver the host-captured leg.\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        f"- {_FACTORY_ASSERTION}\n"
        "\n"
        "### Host-captured\n"
        "\n"
        f"{stated}"
        f"- {_HOST_ASSERTION}\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )


def _verified_record_body() -> str:
    """The merging run's `verified` record: the factory assertion, reproduced.

    It lists the host-captured assertion under a heading stating it is pending the
    host leg, which is the shape the record clause requires of a `verified` record
    on an item carrying one. The pass must reach PENDING for that assertion from
    the MODE rather than from this heading's wording.
    """
    return textwrap.dedent(f"""\
        Proof of Done — verified — run {_RUN_ID} — 2026-10-04T09:00:00Z

        ## Assertion 1 — {_FACTORY_ASSERTION}

        Proof mode: `factory_captured`

        Reproduced: yes.

        ## Pending the host leg

        - {_HOST_ASSERTION}
        """)


def _comments_payload(*, bodies: Sequence[str]) -> str:
    return json.dumps({"comments": [{"url": _RECORD_URL, "body": body} for body in bodies]})


@dataclass(kw_only=True)
class _ForgeRunner:
    """One surface's shell seam: the merged diff and the pull request's comments."""

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
def _hermetic_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("fabro-host-leg")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", _INVOKER)
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones"
        ".fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    # Pinned at the ONE source rather than at a consumer: the pre-run claim mints
    # the dispatch id and the lock it writes is what `dispatch_one` then reads.
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_self_update.run_id",
        lambda: _DISPATCH_ID,
    )
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="pending-approval",
        title="A host-captured slice",
        description=_definition_of_done(),
        origin="freeform",
        gap_id=None,
        rank="a0",
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


def _patch_acceptance_pass(*, monkeypatch: pytest.MonkeyPatch, comments: str) -> None:
    """Run the REAL acceptance pass, with only its command seam stood in."""
    runner = _ForgeRunner(comments=comments)

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

    monkeypatch.setattr(_dispatcher_completion, "run_acceptance_pass", _call)


def _dispatch_merged_item(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item: WorkItem
) -> tuple[int, Path]:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording())
    _patch_acceptance_pass(
        monkeypatch=monkeypatch, comments=_comments_payload(bodies=[_verified_record_body()])
    )
    exit_code = dispatcher_main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--invoker",
            _INVOKER,
            "--json",
        ]
    )
    return exit_code, repo


def _status_of(*, item_id: str) -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id].status


def _comment_bodies(*, item_id: str) -> list[str]:
    return [one.text for one in read_work_item_comments(path=_config(), work_item_id=item_id)]


def _emitted(*, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """The ONE dispatch result the dispatcher's `--json` envelope carried."""
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    first = payload[0]
    assert isinstance(first, dict)
    return first


def _drive_valve(
    *, repo: Path, action: str, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, object]]:
    """Drive one `drive` valve action through its real command line and read its result."""
    exit_code = drive.main(
        argv=["--repo", str(repo), "--action", action, "--invoker", _INVOKER, "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    return exit_code, payload


# --- "A Host-captured sub-heading without a Reason line blocks ready" ----------


def test_a_host_captured_sub_heading_with_no_reason_is_refused_entry_to_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The approve valve refuses, naming the missing `Reason:` line as the finding.

    The REFUSAL and the UNCHANGED STATUS are asserted together: the clause says
    the item "does not enter ready", and a valve that refused in its message while
    writing `ready` anyway would satisfy a message-only check.
    """
    repo, _ = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(admission_policy="manual", description=_definition_of_done(reason=False)),
    )

    exit_code, payload = _drive_valve(repo=repo, action=f"approve:{_ITEM_ID}", capsys=capsys)

    assert exit_code != 0
    assert payload["status"] == "failed"
    summary = str(payload["summary"])
    assert "Host-captured" in summary
    assert "Reason:" in summary
    # The MODE the malformed declaration named, so an author reading the refusal
    # knows which `Reason:` they owe: the host surface, not the capability no
    # sandbox has.
    assert "host_captured" in summary
    assert _status_of(item_id=_ITEM_ID) == "pending-approval"


def test_the_same_item_with_a_reason_line_enters_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for the refusal above, and the reason it is evidence.

    Without it the refusal is equally consistent with a wall that refuses every
    item carrying a `### Host-captured` sub-heading at all — which would make the
    third mode undeclarable rather than merely gated.
    """
    repo, _ = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(admission_policy="manual"))

    exit_code, payload = _drive_valve(repo=repo, action=f"approve:{_ITEM_ID}", capsys=capsys)

    assert exit_code == 0
    assert payload["status"] == "green"
    assert _status_of(item_id=_ITEM_ID) == "ready"


# --- "The item is admitted under ai-only and parks with the host leg pending" ---


def test_an_ai_only_item_with_a_pending_host_leg_rests_in_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole of this slice's parking half, read off the ledger and the result.

    `ai-only` is the discriminating policy: it is the one policy that CLOSES a
    passing item, so an item that rests under it rests because of the host leg and
    not because a human was owed the acceptance. The wall admitting the dispatch at
    all is the other half of the clause — `ai-only` is NOT refused for a
    host-captured item, because the host leg is agent-performable.

    The verdict is PASS and not NEEDS_ATTENTION: the pass genuinely passed, its
    factory assertion is evidenced by the merging run's record, and the host
    assertion is PENDING rather than unevidenced. That distinction is what keeps
    the item out of the rework route and off an `acceptance_rework_cap` attempt.
    """
    exit_code, _ = _dispatch_merged_item(tmp_path=tmp_path, monkeypatch=monkeypatch, item=_item())

    assert exit_code == 0
    result = _emitted(capsys=capsys)
    assert result["stage"] == "acceptance"
    assert result["verdict"] == "PASS"
    assert result["status"] == "green"
    assert _status_of(item_id=_ITEM_ID) == "acceptance"


def test_the_parking_record_names_the_pending_host_leg_and_its_assertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The park's own record, which is what the clause requires "each pending leg" of.

    The record is the only durable surface that says WHY the item rests: the
    journal lives in the `tmp/` tree of whichever host ran the dispatch. So the
    host assertion has to be named in it, and the action has to be the host one —
    an action naming the `verified` record would send an operator to republish
    proof the item already has.
    """
    _exit_code, _repo = _dispatch_merged_item(
        tmp_path=tmp_path, monkeypatch=monkeypatch, item=_item()
    )
    _ = capsys.readouterr()

    parking = [body for body in _comment_bodies(item_id=_ITEM_ID) if _PARKING_TITLE in body]

    assert len(parking) == 1
    assert "PASS" in parking[0]
    assert _HOST_ASSERTION in parking[0]
    assert "host-captured record" in parking[0]
    assert "host_recorded" in parking[0]
    assert "host_verified" in parking[0]
    # The FACTORY assertion is not pending, and the key line is what the
    # idempotence test reads: a pending-leg set naming both would park the item for
    # a leg whose record it already holds.
    assert f"pending: host-captured record for {_HOST_ASSERTION!r}" in parking[0]


def test_a_factory_only_item_still_closes_under_ai_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for the park above: the same route, with no host-captured leg.

    Without it the park is equally consistent with a disposition that stopped
    closing ANY passing item, which would be a far larger regression than the one
    the park test could detect.
    """
    description = textwrap.dedent(f"""\
        Deliver the factory-only slice.

        ## Definition of Done

        - {_FACTORY_ASSERTION}

        References: ## Effective acceptance criteria
        """)

    exit_code, _ = _dispatch_merged_item(
        tmp_path=tmp_path, monkeypatch=monkeypatch, item=_item(description=description)
    )

    assert exit_code == 0
    assert _emitted(capsys=capsys)["stage"] == "done"
    assert _status_of(item_id=_ITEM_ID) == "done"
