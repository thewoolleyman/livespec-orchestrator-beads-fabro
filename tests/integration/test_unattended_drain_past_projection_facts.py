"""An unattended drain picks past a journal full of retired projection facts.

Binds the first Definition-of-Done assertion of work-item `bd-ib-qm6r1`, which
carries the v127 retirement recorded in `SPECIFICATION/contracts.md` — cited at
FILE level, because a heading-level citation rots the moment the heading is
reworded. That revision replaced the engine-failover projection with "Fallback
selection is observed from the Dispatcher's own decisions", and nothing in the
specification any longer says an unresolved projection-failure fact stops
unattended picking.

MEASURED ON v0.220.0, which is why the case drives the WHOLE invocation rather
than the selection: `loop --budget 1 --parallel 1 --dry-run` with NO `--item`
returned `[]` at exit 0 over this repository's own journal, which held 153
unresolved `acp-projection-failure` records across 18 runs. An empty report at
exit 0 is exactly what an empty ready set produces, so the stall was invisible
at every surface an operator reads, and no assertion about the selection
function could have seen it — the selection was never reached.

THE JOURNAL RECORDS ARE TRANSCRIBED, NOT BUILT. They are the artifacts a
RETIRED writer left behind, so composing them through that writer's own record
builder would bind this case to a module whose deletion is the point; the
literal below is the shape the released build appended.

THE CONTROL IS THE SAME INVOCATION OVER A CLEAN JOURNAL. Without it, "the drain
picked the ready item" is equally consistent with a build that ignores the
journal entirely for a reason unrelated to the retirement — the discriminator is
that the two journals yield the IDENTICAL pick, which is the whole claim.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
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

_ITEM_ID = "bd-ib-drain1"
_REPO_NAME = "livespec-orchestrator-beads-fabro"
_RUN_ID = "01M4Q8FDDHKZ3VE8WSHCTD1AKB"

# The stage the retired writer appended under, and the stage its loop gate
# appended when it stopped a pass. Spelled as literals because both writers are
# retired: a constant imported from the product would be a dependency on the
# very modules this retirement removes.
_FAILURE_STAGE = "acp-projection-failure"
_STOP_STAGE = "acp-projection-picking-stopped"


def _failure_record(*, node: str) -> dict[str, object]:
    """One `acp-projection-failure` line as the released build appended it."""
    return {
        "at": "2026-10-19T09:58:07Z",
        "invoker": "machine:dispatcher",
        "invoker_source": "fallback",
        "stage": _FAILURE_STAGE,
        "fact_id": f"hygiene:model-fallback-projection:{_REPO_NAME}:{_RUN_ID}:{node}",
        "repo": _REPO_NAME,
        "run_id": _RUN_ID,
        "node": node,
        "factory_name": "petri",
        "factory_server_url": "https://gmktec.perch-rudd.ts.net:32276",
        "reason": "timed-out",
        "exit_code": 124,
    }


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment plus a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("unattended-drain-projection-facts")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
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
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A ready slice an unattended drain must pick",
        description=(
            "Implement the slice.\n"
            "\n"
            "## Definition of Done\n"
            "\n"
            "- The dispatched slice lands its change.\n"
            "\n"
            "References: ## Effective acceptance criteria\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-then-human",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"dispatcher": {"wip_cap": 2}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _seed_journal(*, repo: Path, records: tuple[dict[str, object], ...]) -> Path:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            _ = handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def _journal_records(*, path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _unattended_dry_run(*, repo: Path, workflow: Path) -> int:
    """`loop --dry-run` with NO `--item`, which is the unattended shape."""
    return main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--dry-run",
            "--workflow",
            str(workflow),
        ]
    )


def test_the_unattended_dry_run_selects_the_ready_candidate_past_the_projection_facts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The drain reaches selection and reports the ready item, not an empty list."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    journal = _seed_journal(
        repo=repo,
        records=(
            _failure_record(node="implement"),
            _failure_record(node="review"),
            _failure_record(node="disposition"),
        ),
    )

    exit_code = _unattended_dry_run(repo=repo, workflow=workflow)

    out = capsys.readouterr()
    assert exit_code == 0
    # The reported selection, which is the surface that returned `[]`.
    assert f"{_ITEM_ID}  dry-run at loop-pick" in out.out
    assert "(nothing dispatched)" not in out.out
    # The journaled selection, projected from the same value the report is.
    records = _journal_records(path=journal)
    picks = [record for record in records if record.get("stage") == "loop-pick"]
    assert [record.get("picked") for record in picks] == [[_ITEM_ID]]
    # No pass was stopped, and no operator text said one was.
    assert [record for record in records if record.get("stage") == _STOP_STAGE] == []
    assert "Unattended picking is stopped" not in out.err
    # The facts themselves are untouched: the retirement removes the GATE, and
    # a pass that had quietly resolved them would be a second retirement.
    assert len([record for record in records if record.get("stage") == _FAILURE_STAGE]) == 3


def test_a_clean_journal_yields_the_identical_pick(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The control: the pick above is the ordinary pick, not a special case."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    journal = _seed_journal(repo=repo, records=())

    exit_code = _unattended_dry_run(repo=repo, workflow=workflow)

    out = capsys.readouterr()
    assert exit_code == 0
    assert f"{_ITEM_ID}  dry-run at loop-pick" in out.out
    picks = [
        record for record in _journal_records(path=journal) if record.get("stage") == "loop-pick"
    ]
    assert [record.get("picked") for record in picks] == [[_ITEM_ID]]
