"""The attention snapshot reads run attribution and dispatch factories ONCE (bd-ib-tzbdd3).

Measured 2026-10-25 on livespec-orchestrator-beads-fabro: `needs_attention.py` exited 124
at the 900 s budget, twice. `_needs_attention_needs_human_question._run_handle` called
`repo_run_attribution(repo)` once PER blocked item, and each call re-read the whole
dispatch journal (150,548,134 bytes, 197,541 lines; 19.6 s and 17.5 s for two consecutive
calls) plus the ledger's run-id metadata, so 42 blocked items cost ~760 s before any
other gather ran. Beside it, `_stamped_factory_name` issued one guarded `bd show` per
blocked item (60 observed, 1.6-4.6 s each) for a marker the snapshot's own `bd list`
already carries. Both are properties of the SNAPSHOT: read once, reuse for every item.

Fixtures are copied from `test_needs_attention_needs_human_question.py` rather than
imported: a Red commit is exactly one new test file.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_factory import record_dispatch_factory
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_needs_attention_needs_human_question.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_needs_human_question"
_STORE_MODULE_NAME = "livespec_orchestrator_beads_fabro._store_dispatch_factory"

_HP_SERVER = "https://hp.example:32276"
_VPS_SERVER = "https://vps.example:32276"
_RUN_ID = "01NEEDSHUMAN"
_ITEM = "bd-ib-blocked"
_TITLE = "b3.S1 — publish the needs-human question"
_DEFAULT = f"Resolve human-needed block for work-item {_ITEM}: {_TITLE}"
_PROMPT = "loop cannot auto-resolve this work-item; run terminated, work preserved by reference"
_REF = f"refs/heads/needs-human/{_RUN_ID}"
_BACKGROUNDED_COMMAND = "mise exec -- just check-coverage 2>&1 | tail -200"
_BACKGROUNDED_CAUSE = (
    f"ACP tool call toolu_012SANITIZED ({_BACKGROUNDED_COMMAND}) continued in "
    "background as task bai98447y; Fabro terminated the turn before the agent "
    "could start conflicting work"
)
_PLAIN_CAUSE = "review script exited 1: the implementation does not satisfy criterion 3"


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI, keyed by the run id the argv names."""

    inspect_by_run: dict[str, str] = field(default_factory=dict)
    exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(
            exit_code=self.exit_code,
            stdout=self.inspect_by_run.get(argv[2], "[]"),
            stderr="",
        )


def _terminated_runner() -> _Runner:
    """A fake `fabro inspect` for a run that terminated at the needs_human node, engine-routed."""
    checkpoint: dict[str, object] = {
        "next_node_id": "needs_human",
        "loop_failure_signatures": {"review|deterministic|acp turn failed": 1},
    }
    record: dict[str, object] = {
        "run_id": _RUN_ID,
        "status": {"kind": "failed"},
        "checkpoints": [{"checkpoint": checkpoint}],
        "nodes": [
            {
                "id": "needs_human",
                "output": {
                    "stderr": f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_REF}\nLIVESPEC_NEEDS_HUMAN: {_PROMPT}"
                },
            }
        ],
    }
    return _Runner(
        inspect_by_run={_RUN_ID: json.dumps([record]), "01STAMPED": json.dumps([record])}
    )


def _repo(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    journal_runs: tuple[str, ...] = (_RUN_ID,),
    default_factory: str = "hp",
) -> Path:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "fabro")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "default_factory": default_factory,
                        "factories": {
                            "hp": {"server": _HP_SERVER},
                            "vps": {"server": _VPS_SERVER},
                            "ambient": {},
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True)
    # A sibling item's run rides the same journal, so the item filter is
    # exercised rather than assumed.
    records = [{"work_item_id": "bd-ib-sibling", "run_id": "01SIBLING"}]
    records.extend({"work_item_id": _ITEM, "run_id": run_id} for run_id in journal_runs)
    _ = path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return repo


def test_a_snapshot_reads_the_run_attribution_once_for_every_blocked_item(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """One `repo_run_attribution` read per snapshot, however many blocked items it serves."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    real = module.repo_run_attribution

    def _delegate(*, repo: Path) -> object:
        return real(repo=repo)

    counting = Mock(side_effect=_delegate)
    monkeypatch.setattr(module, "repo_run_attribution", counting)
    with module.needs_human_snapshot_scope(snapshot=module.needs_human_snapshot(project_root=repo)):
        for item_id in (_ITEM, "bd-ib-sibling"):
            _ = module.needs_human_question_summary(
                project_root=repo,
                item_id=item_id,
                default_summary=_DEFAULT,
                runner=_terminated_runner(),
            )
    assert counting.call_count == 1, counting.call_args_list


def test_a_snapshot_factory_lookup_replaces_the_per_item_ledger_show(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The factory is in the records the snapshot already loaded; no `bd show` per item."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    show = Mock(side_effect=AssertionError("bd show was issued for the item"))
    monkeypatch.setattr(module, "dispatch_factory_for", show)
    runner = _terminated_runner()
    snapshot = module.NeedsHumanSnapshot(
        attribution=module.snapshot_run_attribution(project_root=repo),
        dispatch_factories={_ITEM: "vps"},
    )
    with module.needs_human_snapshot_scope(snapshot=snapshot):
        _ = module.needs_human_question_summary(
            project_root=repo, item_id=_ITEM, default_summary=_DEFAULT, runner=runner
        )
    assert runner.calls[0][runner.calls[0].index("--server") + 1] == _VPS_SERVER
    assert show.call_count == 0


def test_an_item_absent_from_the_factory_lookup_falls_back_to_the_default_factory(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch, default_factory="hp")
    show = Mock(side_effect=AssertionError("bd show was issued for the item"))
    monkeypatch.setattr(module, "dispatch_factory_for", show)
    runner = _terminated_runner()
    snapshot = module.NeedsHumanSnapshot(
        attribution=module.snapshot_run_attribution(project_root=repo), dispatch_factories={}
    )
    with module.needs_human_snapshot_scope(snapshot=snapshot):
        _ = module.needs_human_question_summary(
            project_root=repo, item_id=_ITEM, default_summary=_DEFAULT, runner=runner
        )
    assert runner.calls[0][runner.calls[0].index("--server") + 1] == _HP_SERVER
    assert show.call_count == 0


def test_outside_a_snapshot_scope_the_per_item_reads_still_serve_a_lone_caller(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The scope is an optimisation for the composer; a single-item caller needs none."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner()
    _ = module.needs_human_question_summary(
        project_root=repo, item_id=_ITEM, default_summary=_DEFAULT, runner=runner
    )
    assert runner.calls[0][2] == _RUN_ID
    assert module.current_needs_human_snapshot() is None


def test_the_composer_scope_is_a_no_op_when_no_item_is_blocked_needs_human(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No blocked needs-human item, no journal read: the scope costs nothing."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    reading = Mock(side_effect=AssertionError("the journal was read for a snapshot nobody needs"))
    monkeypatch.setattr(module, "repo_run_attribution", reading)
    ready = WorkItem(
        id="bd-ib-ready",
        type="task",
        status="ready",
        title="r",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    with module.needs_human_snapshot_scope_for(project_root=repo, items=[ready]):
        assert module.current_needs_human_snapshot() is None
    assert reading.call_count == 0


def test_the_composer_scope_takes_the_snapshot_once_for_blocked_needs_human_items(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    real = module.repo_run_attribution

    def _delegate(*, repo: Path) -> object:
        return real(repo=repo)

    counting = Mock(side_effect=_delegate)
    monkeypatch.setattr(module, "repo_run_attribution", counting)
    blocked = WorkItem(
        id=_ITEM,
        type="task",
        status="blocked",
        title=_TITLE,
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )
    with module.needs_human_snapshot_scope_for(project_root=repo, items=[blocked, blocked]):
        assert module.current_needs_human_snapshot() is not None
    assert counting.call_count == 1


def _store_config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _seed(*, issue_id: str) -> None:
    client = make_beads_client(config=_store_config())
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title=issue_id,
            description="d",
            assignee=None,
            created_at="2026-10-25T00:00:00Z",
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )


def test_every_stamped_factory_is_read_in_one_pass_and_unstamped_items_are_absent() -> None:
    """One `bd list` answers every item's factory; `dispatch_factory_for` was one `bd show` each."""
    reset_fake_singleton()
    for issue_id in ("bd-ib-hp", "bd-ib-vps", "bd-ib-none"):
        _seed(issue_id=issue_id)
    record_dispatch_factory(path=_store_config(), work_item_id="bd-ib-hp", factory="hp")
    record_dispatch_factory(path=_store_config(), work_item_id="bd-ib-vps", factory="vps")
    # Resolved at call time so that, before the read exists, this test FAILS rather than
    # breaking the module's collection.
    read_dispatch_factories = importlib.import_module(_STORE_MODULE_NAME).read_dispatch_factories
    assert read_dispatch_factories(path=_store_config()) == {"bd-ib-hp": "hp", "bd-ib-vps": "vps"}
