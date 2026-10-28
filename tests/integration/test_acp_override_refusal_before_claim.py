"""A refused `--acp-node` override refuses before claim, so nothing is stranded.

Binds the Definition of Done of `bd-ib-csswjl` against `SPECIFICATION/contracts.md`
section "ACP node adapter configuration" and section "Dispatcher admission, WIP
cap, and post-merge acceptance": the Dispatcher validates every `--acp-node`
override against the resolved `dispatcher.acp_nodes` grammar before it claims the
work item, a refused override leaves the item's status and assignee as they were
with no Fabro run created, and a later dispatch of that item is not refused as
already claimed.

THE DEFECT IT PINS. On build 0.247.1 a legacy adapter string overriding a node
whose committed `dispatcher.acp_nodes` entry carries fallback-priority metadata was
refused at stage `acp-nodes` -- but only AFTER `ledger-admit` had set the item
`active`, so every refused dispatch stranded a claim with no run behind it.

"BEFORE CLAIM" IS A CLAIM ABOUT WHAT DID NOT HAPPEN, so it is read off independent
instruments rather than off an exit code: the launch seam was never entered, the
ledger row is still `ready` with no assignee, and the journal holds neither of the
two records a claim leaves behind. The admitting controls are what give the refusal
its meaning -- an override of a DIFFERENT node, and the same node without an
override, must both be admitted, or the case is equally consistent with a wall that
refuses every dispatch against this configuration.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-ovr0claim"

_SPEC_HEADING = "## ACP node adapter configuration"

_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The Dispatcher validates every acp-node override before it claims the work item.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)

# The two journal stages a CLAIM leaves behind: the ledger admission that sets the
# assignee, and the dispatch id the pre-run claim mints.
_CLAIM_STAGES = ("ledger-admit", "dispatch-id")

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_REFUSED_OVERRIDE = f"disposition={_CLAUDE}"
_OTHER_NODE_OVERRIDE = f"review_fix={_CLAUDE}"

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)
_RESERVED_DIR = ".fabro/workflows/implement-work-item"

_IMPLEMENT_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\n'
    f'review_fix_adapter = "{_CLAUDE}"\n'
    f'disposition_adapter = "{_CLAUDE}"\n\n'
    '[run.environment]\nid = "fabro-sandbox"\n'
)
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    '    graph [stall_timeout="7200s"]\n'
    '    start [shape=Mdiamond, label="Start"]\n'
    '    exit  [shape=Msquare, label="Exit"]\n'
    '    implement [timeout="1800s"]\n'
    '    disposition [backend="acp", acp.command="{{ inputs.disposition_adapter }}",'
    ' timeout="1800s"]\n'
    "    start -> implement\n"
    "    implement -> disposition\n"
    "    disposition -> exit\n"
    "}\n"
)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment plus a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("acp-override-refusal-before-claim")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:acp-override-refusal-before-claim")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
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


def _seed_item() -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ITEM,
            type="task",
            status="ready",
            title="Exercise the acp-node override wall",
            description=_SECTION,
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-28T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
        ),
    )


def _repo(*, tmp_path: Path) -> Path:
    """A governed target whose `disposition` node carries fallback-priority metadata."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "wip_cap": 3,
                        "acceptance_mode": "ai-only",
                        "acp_nodes": {
                            "disposition": {
                                "agent": "codex-acp",
                                "model": "gpt-5.5",
                                "effort": "high",
                            }
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    spec = repo / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nThe clause this item is graded against.\n",
        encoding="utf-8",
    )
    workflow = repo / _RESERVED_DIR
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_IMPLEMENT_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return repo


def _recording_run_dispatch(*, calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a factory run WAS created."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _journal_path(*, repo: Path) -> Path:
    """The journal this dispatch writes, NAMED so an unwritten path cannot read as empty."""
    return repo / "dispatch-journal.jsonl"


def _drive(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, argv_tail: list[str]
) -> tuple[int, list[str]]:
    """Drive one REAL dispatch entry point and report its exit code plus launches."""
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))
    argv = [
        *argv_tail,
        "--repo",
        str(repo),
        "--journal",
        str(_journal_path(repo=repo)),
        "--no-close-on-merge",
    ]
    return main(argv=argv), calls


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    journal = _journal_path(repo=repo)
    assert journal.is_file(), f"no journal was written at {journal}"
    return [
        json.loads(line)
        for line in journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _row() -> WorkItem:
    [row] = [item for item in read_work_items(path=_config()) if item.id == _ITEM]
    return row


def test_a_refused_override_leaves_the_item_unclaimed_and_creates_no_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal, read off three instruments rather than off an exit code."""
    repo = _repo(tmp_path=tmp_path)
    _seed_item()

    code, calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["dispatch", "--item", _ITEM, "--acp-node", _REFUSED_OVERRIDE],
    )
    stderr = capsys.readouterr().err

    assert code == EXIT_PRECONDITION_ERROR
    assert calls == []
    assert _row().status == "ready"
    assert _row().assignee is None
    records = _journal_records(repo=repo)
    assert [record for record in records if record.get("stage") in _CLAIM_STAGES] == []
    assert "legacy adapter string" in stderr
    assert _ITEM in stderr


def test_a_later_dispatch_is_not_refused_as_already_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stranded claim is what made the retry fail; with none, the retry launches."""
    repo = _repo(tmp_path=tmp_path)
    _seed_item()
    refused_code, refused_calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["dispatch", "--item", _ITEM, "--acp-node", _REFUSED_OVERRIDE],
    )
    assert refused_code == EXIT_PRECONDITION_ERROR
    assert refused_calls == []

    code, calls = _drive(
        repo=repo, monkeypatch=monkeypatch, argv_tail=["dispatch", "--item", _ITEM]
    )

    assert code == 0
    assert calls == [_ITEM]


def test_an_override_of_another_node_is_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for "not every override": the wall refuses by grammar, not by flag."""
    repo = _repo(tmp_path=tmp_path)
    _seed_item()

    code, calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["dispatch", "--item", _ITEM, "--acp-node", _OTHER_NODE_OVERRIDE],
    )

    assert code == 0
    assert calls == [_ITEM]


def test_the_drain_path_refuses_the_same_override_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second dispatch entry path reaches the wall through its own call site."""
    repo = _repo(tmp_path=tmp_path)
    _seed_item()

    code, calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["loop", "--item", _ITEM, "--acp-node", _REFUSED_OVERRIDE, "--budget", "1"],
    )

    assert code == EXIT_PRECONDITION_ERROR
    assert calls == []
    assert _row().status == "ready"
    assert _row().assignee is None
    records = _journal_records(repo=repo)
    assert [record for record in records if record.get("stage") in _CLAIM_STAGES] == []
