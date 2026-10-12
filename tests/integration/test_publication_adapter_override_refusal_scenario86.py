"""A per-dispatch `pr` adapter override refuses before claim (Scenario 86).

Binds the "Publication is independent of the implementer adapter" and
"A shared repository can configure groom publication without changing code
publication" gherkin scenarios of `SPECIFICATION/scenarios.md` Scenario 86, and
the clause they realize — `SPECIFICATION/contracts.md` section
"ACP node adapter configuration" -> "Publication adapter by selected workflow
kind": an explicit per-dispatch `--acp-node pr=...` override on an implementation
workflow "MUST refuse before claim with a removal remedy, because it requests an
adapter for a command stage", while the same override "applies normally for a
groom-kind ACP `pr`" and "in a mixed-workflow loop this refusal is evaluated per
item before claim".

WHY THIS TIER, AND WHY THE WHOLE CLI. "Refuses BEFORE claim" is a claim about
what did NOT happen, and a dispatch can exit non-zero having already created a
run — so it is read off three independent instruments rather than off an exit
code: the launch seam was never entered, the ledger row is still `ready` with no
assignee, and the journal carries neither of the two records a claim leaves
behind. A unit assertion on the refusal function can reach none of those.

THE ADMITTING CONTROLS ARE WHAT GIVE THE REFUSAL ITS MEANING, and there are two
because the refusal has two ways to be vacuously correct. An override of a
DIFFERENT node must be admitted, or the case is equally consistent with a wall
that refuses every `--acp-node`; and the same `pr` override against a GROOM-kind
selection must be admitted, or it is equally consistent with a wall that refuses
the node unconditionally and makes the ratified groom configuration unreachable.
Both controls are graded on the seam being ENTERED, not on an exit code.

THE REPOSITORY-LEVEL ENTRY IS CARRIED BY EVERY LEG, deliberately. It is the
compatibility setting the same clause says must be IGNORED-and-journaled rather
than refused, so a build that conflated the two layers would refuse the
admitting controls too. Its not-applied row is asserted on the admitted
implementation leg, which is the one place both halves of the clause are
observable at once.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_IMPLEMENT_ITEM = "bd-ib-pub86impl"
_GROOM_ITEM = "bd-ib-pub86groom"

_SPEC_HEADING = "## ACP node adapter configuration"

_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The dispatch refuses an explicit publication adapter override before any claim.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)

# The two journal stages a CLAIM leaves behind: the ledger admission that sets the
# assignee, and the dispatch id the pre-run claim mints. Either one present beside
# a refusal would mean the item was claimed before the wall ran.
_CLAIM_STAGES = ("ledger-admit", "dispatch-id")

_POLICY_STAGE = "acp-publication-policy"
_NODES_STAGE = "acp-nodes"

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)
_RESERVED_DIR = ".fabro/workflows/implement-work-item"
_GROOM_DIR = ".fabro/workflows/groom-work-item"
_GROOM_WORKFLOW_NAME = "groom-work-item"

# The reserved workflow declares the implementer-class adapter inputs the
# admitting control's override targets, and NO `pr_adapter` — which is the v121
# shape and the reason a `pr` override has nothing to apply to.
_IMPLEMENT_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\n'
    'review_fix_adapter = "npx -y @agentclientprotocol/claude-agent-acp"\n\n'
    '[run.environment]\nid = "fabro-sandbox"\n'
)
# The groom variant declares its KIND, which is what scopes the policy; the
# reserved workflow above declares none, which is the shape of every variant
# registered before that key existed and the one the exemption must not open on.
_GROOM_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n'
    'pr_adapter = "npx -y @agentclientprotocol/claude-agent-acp"\n\n'
    '[run.environment]\nid = "fabro-sandbox"\n'
)
_GRAPH = (
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

# A complete manual-form adapter: the override has to be WELL-FORMED, or the
# refusal under test is indistinguishable from the generic malformed-entry one.
_PR_OVERRIDE = "pr=npx -y @agentclientprotocol/claude-agent-acp"
_REVIEW_FIX_OVERRIDE = "review_fix=npx -y @agentclientprotocol/claude-agent-acp"


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment plus a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("publication-adapter-override-refusal")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:publication-adapter-override-refusal")
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


def _seed_item(*, item_id: str, workflow_name: str | None) -> None:
    """Seed one ready item, optionally pinned to the groom-kind variant."""
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=item_id,
            type="task",
            status="ready",
            title="Exercise the publication-adapter override wall",
            description=_SECTION,
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-11T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
        ),
    )
    if workflow_name is not None:
        record_dispatch_workflow(path=_config(), work_item_id=item_id, workflow=workflow_name)


def _repo(*, tmp_path: Path) -> Path:
    """A governed target registering BOTH workflow kinds and configuring `pr`.

    The repository-level `acp_nodes.pr` entry is what the clause says an
    implementation dispatch must IGNORE while a groom dispatch applies it. It is
    present on every leg so no case can pass by having removed it.
    """
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
                        "workflows": {_GROOM_WORKFLOW_NAME: _GROOM_DIR},
                        "acp_nodes": {
                            "pr": {"command": "npx -y @agentclientprotocol/claude-agent-acp"}
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
    for directory, run_config in ((_RESERVED_DIR, _IMPLEMENT_TOML), (_GROOM_DIR, _GROOM_TOML)):
        workflow = repo / directory
        workflow.mkdir(parents=True)
        _ = (workflow / "workflow.toml").write_text(run_config, encoding="utf-8")
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
    """The journal this dispatch writes, NAMED rather than defaulted.

    Passed explicitly on every invocation so the read below cannot be a read of
    a path nothing wrote: an absent file reads as "no records", which satisfies
    every must-not-contain assertion in this module while establishing nothing.
    """
    return repo / "dispatch-journal.jsonl"


def _drive(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv_tail: list[str],
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
    """Every journal record this dispatch wrote, in order.

    The file MUST exist: every invocation in this module reaches at least the
    stage that writes one, so an absent journal is a broken fixture rather than
    a dispatch that recorded nothing.
    """
    journal = _journal_path(repo=repo)
    assert journal.is_file(), f"no journal was written at {journal}"
    return [
        json.loads(line)
        for line in journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _row(*, item_id: str) -> WorkItem:
    [row] = [item for item in read_work_items(path=_config()) if item.id == item_id]
    return row


def test_an_implementation_dispatch_refuses_a_pr_override_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal, read off three instruments rather than off an exit code."""
    repo = _repo(tmp_path=tmp_path)
    _seed_item(item_id=_IMPLEMENT_ITEM, workflow_name=None)

    code, calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["dispatch", "--item", _IMPLEMENT_ITEM, "--acp-node", _PR_OVERRIDE],
    )
    stderr = capsys.readouterr().err

    assert code == EXIT_PRECONDITION_ERROR
    assert calls == []
    row = _row(item_id=_IMPLEMENT_ITEM)
    assert row.status == "ready"
    assert row.assignee is None
    records = _journal_records(repo=repo)
    assert [record for record in records if record.get("stage") in _CLAIM_STAGES] == []
    [refusal] = [record for record in records if record.get("stage") == _POLICY_STAGE]
    assert refusal["result"] == "refused"
    assert refusal["layer"] == "dispatch"
    assert refusal["node"] == "pr"
    assert refusal["work_item_ids"] == [_IMPLEMENT_ITEM]
    # The removal remedy the clause requires, and the node's own reason.
    assert "remove the override" in stderr
    assert "command stage" in stderr
    assert _IMPLEMENT_ITEM in stderr


def test_an_override_of_another_node_is_admitted_and_pr_config_is_journaled_unapplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for "not every override", and the ignored-repository half.

    One invocation carries both halves of the clause: the dispatch is ADMITTED
    with a well-formed override of a different node, and the repository's `pr`
    entry — present throughout — is journaled as not applied rather than
    refusing this dispatch or acquiring an adapter for a command stage.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_item(item_id=_IMPLEMENT_ITEM, workflow_name=None)

    code, calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["dispatch", "--item", _IMPLEMENT_ITEM, "--acp-node", _REVIEW_FIX_OVERRIDE],
    )

    assert code == 0
    assert calls == [_IMPLEMENT_ITEM]
    records = _journal_records(repo=repo)
    assert [record for record in records if record.get("stage") == _POLICY_STAGE] == []
    [nodes] = [record for record in records if record.get("stage") == _NODES_STAGE]
    assert nodes["not_applied"] == [
        {
            "layer": "repository",
            "node": "pr",
            "entry": "dispatcher.acp_nodes.pr",
            "workflow_kind": "implement",
            "reason": "implementation-publication-is-scripted",
        }
    ]


def test_a_groom_selection_applies_the_same_pr_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control that the refusal is scoped by KIND, not by node name.

    Without it, the refusal above is equally consistent with a wall that refuses
    `pr` unconditionally — which would make the groom variant's ratified ACP
    publisher unconfigurable from the per-dispatch layer.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_item(item_id=_GROOM_ITEM, workflow_name=_GROOM_WORKFLOW_NAME)

    code, calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["dispatch", "--item", _GROOM_ITEM, "--acp-node", _PR_OVERRIDE],
    )

    assert code == 0
    assert calls == [_GROOM_ITEM]
    records = _journal_records(repo=repo)
    assert [record for record in records if record.get("stage") == _POLICY_STAGE] == []
    [nodes] = [record for record in records if record.get("stage") == _NODES_STAGE]
    assert "not_applied" not in nodes


def test_the_drain_path_refuses_the_same_override_per_item_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second dispatch entry path reaches the wall through its own call site.

    The clause says the refusal is evaluated per item before claim "in a
    mixed-workflow loop", so this leg is graded on the same three instruments as
    the hand-picked one: no launch, an unclaimed row, and no claim record.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_item(item_id=_IMPLEMENT_ITEM, workflow_name=None)

    code, calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=[
            "loop",
            "--item",
            _IMPLEMENT_ITEM,
            "--acp-node",
            _PR_OVERRIDE,
            "--budget",
            "1",
        ],
    )

    assert code == EXIT_PRECONDITION_ERROR
    assert calls == []
    row = _row(item_id=_IMPLEMENT_ITEM)
    assert row.status == "ready"
    assert row.assignee is None
    records = _journal_records(repo=repo)
    assert [record for record in records if record.get("stage") in _CLAIM_STAGES] == []
    assert [record for record in records if record.get("stage") == _POLICY_STAGE]
