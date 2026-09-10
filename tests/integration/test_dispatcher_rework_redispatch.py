"""Integration-tier acceptance for the Dispatcher's rework-pending re-dispatch.

Binds the executor half of the ratified rework-pending re-dispatch contract in
`SPECIFICATION/contracts.md` through the real `dispatcher.main(argv=[...])` CLI
and the real store/client seam against the in-memory `FakeBeadsClient` (the
hermetic CI backend), with `run_dispatch` replaced by a recording stand-in so
no fabro sandbox launches:

- The drain drives marked, lock-less `active` rows BEFORE admitting any new
  `ready` item, in `(rank, id)` order — proven with a marked row whose rank is
  WORSE than the ready item it still precedes, so the assertion cannot pass on
  rank alone.
- The capacity condition excludes the marked item's OWN `active` row: it runs
  under a `wip_cap` of 1 with no other claim, and defers under the same cap
  once another `active` row holds a live dispatch lock. `wip_cap: 0` admits
  nothing.
- `dispatch --item` accepts a marked item and still refuses a bare `active`
  one as a precondition error.
- Starting a rework dispatch journals the admission and leaves the marker
  stamped; only the terminal disposition clears it.
- A rework dispatch that dies before publishing leaves the row marked and
  lock-less, and a LATER drain pass selects it again. The control is the
  second pass: without it, "still marked" could not tell a self-healing park
  apart from a re-stranded one.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion, _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_EXIT_PRECONDITION_ERROR = 3
# Seeded through the raw label the store materializes the field from, so each
# fixture states the ledger fact rather than borrowing the writer under test.
_REWORK_PENDING_LABEL = "rework:pending"
_REWORK_ADMIT_STAGE = "ledger-rework-admit"

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


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-rework-redispatch")
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
        id="bd-ib-s1",
        type="task",
        status="ready",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _marked(*, item_id: str, rank: str) -> WorkItem:
    """Seed an `active` row already stamped `rework:pending`, as a rework park."""
    item = _item(id=item_id, status="active", rank=rank, assignee="fabro")
    append_work_item(path=_config(), item=item)
    make_beads_client(config=_config()).update_issue(
        issue_id=item_id, add_labels=[_REWORK_PENDING_LABEL]
    )
    return item


def _repo_with_workflow(*, tmp_path: Path, wip_cap: int) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        (
            '{"git_author": {"operator_name": "Chad Woolley", '
            '"operator_email": "thewoolleyman@gmail.com"}, '
            '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
            f' "dispatcher": {{"wip_cap": {wip_cap}, "acceptance_mode": "ai-only"}}}}}}'
        ),
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _stored(*, item_id: str) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id]


def _recording(
    *, calls: list[str], outcome: Callable[[str], DispatchOutcome]
) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in that records each launch, in launch order."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return outcome(plan.work_item_id)

    return _run_dispatch


def _green(work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="green",
        stage="done",
        pr_number=11,
        merge_sha="feed01",
        detail="merged",
    )


def _died_before_publishing(work_item_id: str) -> DispatchOutcome:
    """A pre-publish death: no PR, no merge sha, a non-terminal-lifecycle stage."""
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage="implement",
        pr_number=None,
        merge_sha=None,
        detail="sandbox died before publishing",
    )


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def _loop_argv(*, repo: Path, workflow: Path, budget: int) -> list[str]:
    return [
        "loop",
        "--repo",
        str(repo),
        "--budget",
        str(budget),
        "--workflow",
        str(workflow),
        "--no-close-on-merge",
    ]


def test_drain_drives_marked_rows_in_rank_order_before_new_admissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=3)
    # The marked rows rank WORSE than the ready one, so leading them cannot be
    # explained by rank: it is the rework leg running first.
    _ = _marked(item_id="bd-ib-rw-second", rank="a8")
    _ = _marked(item_id="bd-ib-rw-first", rank="a4")
    append_work_item(path=_config(), item=_item(id="bd-ib-new", status="ready", rank="a0"))
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))

    exit_code = main(argv=_loop_argv(repo=repo, workflow=workflow, budget=3))

    assert exit_code == 0
    assert calls == ["bd-ib-rw-first", "bd-ib-rw-second", "bd-ib-new"]
    # The new admission still happened; the rework leg reorders, never starves.
    assert _stored(item_id="bd-ib-new").status == "active"


def test_rework_dispatch_journals_its_admission_and_keeps_the_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=3)
    item = _marked(item_id="bd-ib-rw-journal", rank="a1")
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))

    exit_code = main(argv=_loop_argv(repo=repo, workflow=workflow, budget=3))

    assert exit_code == 0
    assert calls == [item.id]
    records = _journal_records(repo=repo)
    admits = [record for record in records if record.get("stage") == _REWORK_ADMIT_STAGE]
    assert [record["work_item_id"] for record in admits] == [item.id]
    picks = [record for record in records if record.get("stage") == "loop-pick"]
    assert picks[-1]["rework_picked"] == [item.id]
    # `--no-close-on-merge` withholds the terminal disposition, so the marker is
    # still stamped after the run: the launch never clears it.
    stored = _stored(item_id=item.id)
    assert (stored.status, stored.rework_pending) == ("active", True)


def test_terminal_disposition_clears_the_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=3)
    item = _marked(item_id="bd-ib-rw-terminal", rank="a1")
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _PassingAcceptancePass(),
    )

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "3",
            "--workflow",
            str(workflow),
        ]
    )

    assert (exit_code, calls) == (0, [item.id])
    stored = _stored(item_id=item.id)
    assert (stored.status, stored.rework_pending) == ("done", False)


class _PassingAcceptancePass:
    """A stand-in AI acceptance pass that confirms the rework's own terminal."""

    verdict = "PASS"
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }


def test_rework_runs_under_wip_cap_one_because_its_own_row_is_excluded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=1)
    item = _marked(item_id="bd-ib-rw-solo", rank="a1")
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))

    exit_code = main(argv=_loop_argv(repo=repo, workflow=workflow, budget=3))

    # The parked row cannot saturate the count it must itself pass, so the
    # `wip_cap: 1` self-deadlock does not arise.
    assert (exit_code, calls) == (0, [item.id])


def test_rework_defers_when_another_active_row_fills_the_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=1)
    item = _marked(item_id="bd-ib-rw-capped", rank="a1")
    busy = _item(id="bd-ib-busy", status="active", rank="a0", assignee="fabro")
    append_work_item(path=_config(), item=busy)
    _ = write_dispatch_lock(repo=repo, work_item_id=busy.id, dispatch_id="busy-dispatch")
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))

    exit_code = main(argv=_loop_argv(repo=repo, workflow=workflow, budget=3))

    # One OTHER active row already fills the cap, so the count of active items
    # other than the marked one is NOT below it. A deferral is not a defect.
    assert (exit_code, calls) == (0, [])
    stored = _stored(item_id=item.id)
    assert (stored.status, stored.rework_pending) == ("active", True)
    deferrals = [
        record
        for record in _journal_records(repo=repo)
        if record.get("stage") == "outcome"
        and isinstance(record.get("outcome"), dict)
        and record["outcome"]["stage"] == "rework-capacity-deferred"  # type: ignore[index]
    ]
    assert len(deferrals) == 1


def test_wip_cap_zero_admits_no_rework(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=0)
    item = _marked(item_id="bd-ib-rw-off", rank="a1")
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))

    exit_code = main(argv=_loop_argv(repo=repo, workflow=workflow, budget=3))

    assert (exit_code, calls) == (0, [])
    assert _stored(item_id=item.id).rework_pending is True


def test_dispatch_item_accepts_a_marked_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=3)
    item = _marked(item_id="bd-ib-rw-override", rank="a1")
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))

    exit_code = main(
        argv=[
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

    assert (exit_code, calls) == (0, [item.id])
    # Admitted through the rework leg exactly once — not also as a fresh
    # `ready -> active` admission of the same row.
    records = _journal_records(repo=repo)
    assert [record.get("stage") for record in records].count(_REWORK_ADMIT_STAGE) == 1
    assert [record.get("stage") for record in records].count("ledger-admit") == 0


def test_dispatch_item_still_refuses_an_unmarked_active_item(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=3)
    item = _item(id="bd-ib-bare-active", status="active", rank="a1", assignee="fabro")
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls, outcome=_green))

    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert (exit_code, calls) == (_EXIT_PRECONDITION_ERROR, [])
    assert item.id in capsys.readouterr().err


def test_pre_publish_death_leaves_the_row_marked_and_a_later_drain_reselects_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=3)
    item = _marked(item_id="bd-ib-rw-died", rank="a1")
    calls: list[str] = []
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _recording(calls=calls, outcome=_died_before_publishing),
    )

    first = main(argv=_loop_argv(repo=repo, workflow=workflow, budget=3))

    assert (first, calls) == (1, [item.id])
    after_death = _stored(item_id=item.id)
    # Marked, still `active`, and holding no live dispatch lock: the three
    # conditions the next drain's selection reads.
    assert (after_death.status, after_death.rework_pending) == ("active", True)
    assert live_dispatch_lock(repo=repo, work_item_id=item.id) is None

    second = main(argv=_loop_argv(repo=repo, workflow=workflow, budget=3))

    # Self-healing rather than re-stranded: the SAME row is selected again.
    assert (second, calls) == (1, [item.id, item.id])
