"""Integration-tier acceptance for the post-merge half of Proof of Done.

Binds the post-merge gherkin scenarios of `SPECIFICATION/scenarios.md`
"Scenario 132 — A factory-captured proof is captured on a draft pull request,
reviewed, replayed and published" and "Scenario 133 — A mixed item is refused
ai-only from every entry path, parks for its human-attested leg, and the accept
valve refuses until the record exists".

Every case drives the REAL `dispatcher.main(argv=["dispatch", ...])` CLI, the
REAL `run_acceptance_pass` and the REAL store/client seam against the in-memory
`FakeBeadsClient`. Two seams are stood in: `run_dispatch`, so no factory sandbox
launches, and the acceptance pass's `CommandRunner`, so the merged diff and the
pull request's comments are canned instead of shelled out for. The verdict, the
disposition and every ledger write are production code.

THE REWORK COUNTER IS READ OFF THE RAW LEDGER ROW, not off the materialized
`WorkItem`. `acceptance_failed_ai_passes` lives in the metadata JSON column and
the materialized record does not surface it, so asserting "the cap was not
consumed" through the projection would pass just as well against a build that
consumed it — the one failure mode the unevidenceable-assertion clause exists to
prevent. The `rework:pending` marker is checked beside it because the two are
written by the same disposition and either alone would read as "no rework
happened".
"""

from __future__ import annotations

import json
import tempfile
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion, _dispatcher_loop
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

_RUN_ID = "01M3POINTERRUN"
_PR_NUMBER = 11
_FACTORY_ASSERTION = "The dispatched slice lands its change."
# Deliberately shares no significant term with the assertion: a diff the
# vocabulary matcher could satisfy would make a PASS ambiguous about which leg
# produced it, and the whole point of the proof leg is that the diff is not it.
_READABLE_DIFF = "diff --git a/impl.py b/impl.py\n+rearranged an unrelated helper\n"
_RECORD_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-700"


def _definition_of_done() -> str:
    return textwrap.dedent(f"""\
        Implement the slice.

        ## Definition of Done

        - {_FACTORY_ASSERTION}

        References: ## Effective acceptance criteria
        """)


def _record_body(*, verdict: str, run_id: str = _RUN_ID) -> str:
    return textwrap.dedent(f"""\
        Proof of Done — {verdict} — run {run_id} — 2026-10-01T09:00:00Z

        ## Assertion 1 — {_FACTORY_ASSERTION}

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
    scratch = tmp_path_factory.mktemp("fabro-proof-of-done")
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
        id="bd-ib-proofpointer",
        type="task",
        status="pending-approval",
        title="A dispatched slice",
        description=_definition_of_done(),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
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
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
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
            merge_sha="feed01",
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
    ) -> AcceptancePassResult:
        return run_acceptance_pass(
            repo=repo, item=item, outcome=outcome, runner=runner, raw_labels=raw_labels
        )

    return _call


def _dispatch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, comments: str, item: WorkItem
) -> tuple[int, list[dict[str, object]]]:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording())
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        _acceptance_pass_over(runner=_ForgeRunner(comments=comments)),
        raising=False,
    )
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return exit_code, [json.loads(line) for line in text.splitlines() if line.strip()]


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _raw_record(*, item_id: str) -> dict[str, Any]:
    return dict(make_beads_client(config=_config()).show_issue(issue_id=item_id))


def _record(*, records: list[dict[str, object]], stage: str) -> dict[str, object]:
    return next(one for one in records if one.get("stage") == stage)


def test_an_unevidenced_assertion_parks_without_consuming_the_rework_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 133 — "An unevidenced assertion parks without consuming the rework cap".

    The pull request carries a `captured` record for the merging run and no
    `verified` one, which is exactly the shape a run that was reviewed but never
    replayed leaves behind. A `captured` record is NOT the proof evidence leg, so
    the assertion is unevidenced — and the discriminating control is that the
    record it DOES carry names the assertion and says `Reproduced: yes.`: a build
    that read any record rather than the `verified` one would PASS here.
    """
    item = _item()

    exit_code, records = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="captured")]),
        item=item,
    )

    assert exit_code == 0
    ai_pass = _record(records=records, stage="acceptance-ai-pass")
    assert ai_pass["verdict"] == "NEEDS_ATTENTION"
    assert ai_pass["absent_evidence"] == [f"proof of done record for {_FACTORY_ASSERTION!r}"]
    # The verdict parks under `ai-only`, which is the AI-DISPOSITIVE policy: the
    # delegation it grants is authority to act ON evidence, not without it.
    parked = _stored()[item.id]
    assert (parked.status, parked.resolution, parked.blocked_reason) == ("acceptance", None, None)
    # The cap was NOT consumed, read off the raw ledger row where it lives.
    raw = _raw_record(item_id=item.id)
    metadata = raw.get("metadata")
    assert isinstance(metadata, dict)
    assert "acceptance_failed_ai_passes" not in metadata
    assert "rework:pending" not in raw.get("labels", [])
    # And nothing routed the item to rework at all.
    assert [one.get("stage") for one in records].count("acceptance-rework") == 0


def test_a_verified_record_for_the_merging_run_grades_the_assertion_and_accepts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control for the case above, through the same dispatch.

    Without it, "the unevidenced assertion parked" is equally consistent with a
    proof leg that can never evidence anything. The ONLY difference between the
    two fixtures is the record's verdict.
    """
    item = _item(id="bd-ib-proofverified")

    exit_code, records = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="verified")]),
        item=item,
    )

    assert exit_code == 0
    ai_pass = _record(records=records, stage="acceptance-ai-pass")
    assert ai_pass["verdict"] == "PASS"
    assert ai_pass["absent_evidence"] == []
    assert _stored()[item.id].status == "done"


def test_the_pointer_is_written_after_an_unchanged_definition_of_done_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 132 — "The pointer is written after merge".

    The pointer clause requires the section to sit AFTER the Definition of Done
    section, to preserve that section BYTE-FOR-BYTE, and to carry ONLY the
    pointer — "The section MUST NOT copy proof content."

    All three are asserted separately and none is redundant. The byte-for-byte
    claim is checked by slicing the stored description at the pointer heading and
    comparing the prefix to the description that was FILED, because a build that
    rewrote the section while adding the pointer would satisfy an
    `in`-containment check just as well. The no-proof-content claim is checked
    against the record's own proof vocabulary, which is present in the record
    body the same dispatch read and must be absent from the description.
    """
    item = _item(id="bd-ib-proofpointerwrite")

    exit_code, records = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        comments=_comments_payload(bodies=[_record_body(verdict="verified")]),
        item=item,
    )

    assert exit_code == 0
    description = _stored()[item.id].description
    head, _, pointer = description.partition("## Proof of Done")
    assert pointer != ""
    # Byte-for-byte: everything before the pointer heading is the filed
    # description, trailing separator aside.
    assert head.rstrip("\n") == _definition_of_done().rstrip("\n")
    assert pointer.splitlines()[1:] == [
        "",
        f"- Pull request: #{_PR_NUMBER}",
        f"- Verified record: {_RECORD_URL}",
        f"- Run: {_RUN_ID}",
        "- Timestamp: 2026-10-01T09:00:00Z",
        "- Verdict: verified",
    ]
    # The section carries the POINTER, never the proof: no reproduction step, no
    # proof mode line, no reproduction verdict from the record body.
    assert "Reproduced:" not in description
    assert "Proof mode:" not in description
    written = _record(records=records, stage="proof-pointer")
    assert written["work_item_id"] == item.id
    assert written["pull_request"] == _PR_NUMBER
    assert written["record_comment"] == _RECORD_URL
    assert written["run_id"] == _RUN_ID
