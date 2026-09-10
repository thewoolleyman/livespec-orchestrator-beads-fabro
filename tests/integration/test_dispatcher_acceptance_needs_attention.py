"""Integration-tier acceptance for the NEEDS_ATTENTION acceptance park.

Drives the ratified post-merge-acceptance evidence rule and NEEDS_ATTENTION
verdict of `SPECIFICATION/contracts.md`
through the real `dispatcher.main(argv=[...])` CLI, the real
`run_acceptance_pass` verdict function, and the real store/client seam against
the in-memory `FakeBeadsClient` (the hermetic CI backend). Only two seams are
stood in for: `run_dispatch` (so no fabro sandbox launches) and the acceptance
pass's `CommandRunner` (so no `gh` / `git` subprocess runs) — the verdict, the
disposition, and the ledger writes are the production code paths.

- An item whose telemetry leg is unobservable while its merged diff is readable
  parks with a NEEDS_ATTENTION verdict, under the AI-dispositive `ai-only`
  policy, and stays reachable by the human `accept` and `reject` valves.
- An item whose effective criteria parse to zero gradeable assertions is
  neither auto-accepted nor reworked: nothing is disposed from absent evidence,
  and `acceptance_rework_cap` is not consumed.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

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
from livespec_orchestrator_beads_fabro.commands.drive import run_action
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

# A merged diff carrying the criterion's own vocabulary, so the criteria leg
# grades cleanly and the ONLY thing missing is the leg each case removes.
_READABLE_DIFF = (
    "diff --git a/impl.py b/impl.py\n" "+the parking record names the absent evidence leg\n"
)


@dataclass(kw_only=True)
class _StubRunner:
    """The acceptance pass's command seam, standing in for `gh` / `git`."""

    stdout: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic C-mode dispatch environment + fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-needs-attention")
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
        id="bd-ib-na",
        type="task",
        status="pending-approval",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
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


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _green_recording(*, pr_number: int | None) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in returning a green terminal for one item."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=pr_number,
            merge_sha="feed01",
            detail="merged",
        )

    return _run_dispatch


def _acceptance_pass_over(
    *, stdout: str, criteria_removed_after_dispatch: bool = False
) -> Callable[..., AcceptancePassResult]:
    """The REAL acceptance pass, with only its command seam stood in.

    `criteria_removed_after_dispatch` models the one production shape that can
    still reach the acceptance pass with zero gradeable assertions now that the
    pre-dispatch wall exists: an item that carried gradeable criteria when it
    was dispatched and had them edited away before the post-merge pass read the
    ledger row back.
    """
    runner = _StubRunner(stdout=stdout)

    def _call(
        *,
        repo: Path,
        item: WorkItem,
        outcome: DispatchOutcome,
        raw_labels: Sequence[str] = (),
    ) -> AcceptancePassResult:
        judged = (
            replace(item, acceptance_criteria=None) if criteria_removed_after_dispatch else item
        )
        return run_acceptance_pass(
            repo=repo, item=judged, outcome=outcome, runner=runner, raw_labels=raw_labels
        )

    return _call


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _record(*, records: list[dict[str, object]], stage: str) -> dict[str, object]:
    return next(record for record in records if record.get("stage") == stage)


@pytest.mark.parametrize(
    ("valve", "expected_status"),
    [("accept:{item}", "done"), ("reject:{item}:rework", "active")],
)
def test_unobservable_telemetry_with_readable_diff_parks_needs_attention(
    valve: str,
    expected_status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(
        acceptance_criteria="The parking record names the absent evidence leg.",
    )
    append_work_item(path=_config(), item=item)
    # A green run with no merged PR number: the run/telemetry leg cannot be
    # observed, while the merged diff reads cleanly off the merge sha.
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(pr_number=None))
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        _acceptance_pass_over(stdout=_READABLE_DIFF),
        raising=False,
    )

    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 0
    parked = _stored()[item.id]
    # `ai-only` is AI-DISPOSITIVE for a judged verdict, and still parks here:
    # the delegation it grants is authority to act ON evidence, not without it.
    assert (parked.status, parked.resolution, parked.blocked_reason) == ("acceptance", None, None)
    records = _journal_records(repo=repo)
    ai_pass = _record(records=records, stage="acceptance-ai-pass")
    assert ai_pass["verdict"] == "NEEDS_ATTENTION"
    assert ai_pass["absent_evidence"] == ["telemetry"]
    assert ai_pass["telemetry"] == {
        "observed": False,
        "passed": False,
        "reason": "merged PR number unavailable",
    }
    assert ai_pass["diff"] == {
        "observed": True,
        "bytes": len(_READABLE_DIFF.encode()),
        "reason": "merged diff read",
    }
    park = _record(records=records, stage="acceptance-parked")
    assert park["acceptance_verdict"] == "NEEDS_ATTENTION"
    # The parking record names the absent leg, so the attention surface can say
    # WHY the item cannot be judged rather than only that it is waiting.
    assert park["absent_evidence"] == ["telemetry"]

    # The parked item is still reachable by BOTH existing human valves.
    result = run_action(repo=repo, action_id=valve.format(item=item.id))

    assert result["status"] == "green"
    assert result["target_status"] == expected_status
    assert _stored()[item.id].status == expected_status


def test_zero_gradeable_assertions_is_neither_auto_accepted_nor_reworked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    # The item is DISPATCHABLE — the pre-dispatch wall (the
    # effective-acceptance-criteria clause of contracts.md) refuses an
    # AI-dispositive item whose criteria parse to zero gradeable assertions, so
    # this case can no longer be built by
    # filing one without criteria at all. Its criteria are removed between
    # dispatch and the post-merge pass instead, which is the shape that still
    # reaches the pass vacuously: no acceptance_criteria field and no `Exit
    # criteria` description section by the time the pass reads it.
    item = _item(
        id="bd-ib-nocrit",
        acceptance_criteria="The parking record names the absent evidence leg.",
    )
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(pr_number=11))
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        _acceptance_pass_over(stdout=_READABLE_DIFF, criteria_removed_after_dispatch=True),
        raising=False,
    )

    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 0
    stored = _stored()[item.id]
    # Not auto-accepted (`done`) under `ai-only`, and not reworked (`active`):
    # a vacuous check set is absent evidence, not passing or failing evidence.
    assert (stored.status, stored.resolution, stored.blocked_reason) == ("acceptance", None, None)
    records = _journal_records(repo=repo)
    ai_pass = _record(records=records, stage="acceptance-ai-pass")
    assert ai_pass["verdict"] == "NEEDS_ATTENTION"
    assert ai_pass["absent_evidence"] == ["effective criteria"]
    assert ai_pass["criteria"] == {"observed": False, "checks": []}
    stages = {record.get("stage") for record in records}
    assert "ledger-accept" not in stages
    assert "acceptance-auto-rework" not in stages
    assert "acceptance-rework-cap-exceeded" not in stages
    park = _record(records=records, stage="acceptance-parked")
    assert park["absent_evidence"] == ["effective criteria"]
    # acceptance_rework_cap is not consumed: the failed-pass counter the cap
    # reads against is the ledger write the FAIL route makes, and it is absent.
    ledger_record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert "acceptance_failed_ai_passes" not in ledger_record["metadata"]
