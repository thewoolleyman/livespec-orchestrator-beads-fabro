"""Consumer-tier acceptance for the two provider-spend-containment scenarios.

Binds `SPECIFICATION/scenarios.md` Scenario 60 and Scenario 61 through the real
`dispatcher.main(argv=[...])` CLI and the real store/client seam against the
in-memory `FakeBeadsClient`, with `run_dispatch` replaced by a recording
stand-in so no Fabro sandbox launches. Every case here drives the Dispatcher's
own entry point rather than the admission helper it calls, because the clause
under test — the provider spend containment clause of
`SPECIFICATION/contracts.md` — is a
statement about what a dispatch DOES, and a helper-level call cannot fail the
way a wired-up pass can.

- Scenario 60 — an observed provider exhaustion refuses admission and expires:
  an unexpired record refuses without disposing the item, an expired one
  refuses nothing, an uncovered provider is admitted, the record names the
  vendor that actually refused, admission is decided without reading credential
  material, and no refusal disposes of a needs-human item.
- Scenario 61 — a dead implementer does not spend the second vendor: the
  workflow graph the Dispatcher actually materializes for the sandbox routes an
  unchanged tree to the terminal breaker before any review, review-fix or
  disposition round, keeps the changed-tree path intact, and the Dispatcher
  journals the truncation against the work-item without disposing of it.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop, needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    active_provider_exhaustion,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.needs_attention import SpecNextOutput

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHIPPED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"

# The governing condition the containment records carry, and the sentinel the
# workflow's own terminal breaker emits. Both are literals of the system under
# test rather than of this file: the first is asserted against the record the
# Dispatcher writes, the second against the graph the Dispatcher materializes.
_GOVERNING_CONDITION = "provider_usage_limit"
_DEAD_IMPLEMENTER_MARKER = "LIVESPEC_DEAD_IMPLEMENTER"

_UNEXPIRED = "2099-01-01T00:00:00Z"
_EXPIRED = "2000-01-01T00:00:00Z"

# The two vendors' ceilings verbatim, reproduced from real `fabro inspect
# --json` payloads on the hp factory (2026-08-22). They are the INPUT the
# production classifier is fed here: nothing in this file writes a provider
# NAME, because a hand-written one proves selectivity against a value no
# production path can produce.
_ACP_WRAPPER = "ACP protocol error"
_ANTHROPIC_SPEND_LIMIT = (
    "Internal error: You've hit your org's monthly spend limit "
    "· ask your admin to raise it at claude.ai/settings/usage"
)

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

# A minimal workflow graph for the payload materializer to render: one node
# timeout plus the run-level stall watchdog. Scenario 61 deliberately does NOT
# use it — that scenario is about the SHIPPED graph — but every Scenario 60 case
# needs a dispatch to reach the admission valve and nothing more.
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
    """Hermetic C-mode dispatch environment + fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-spend-containment")
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
        acceptance_policy="ai-then-human",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _repo(*, tmp_path: Path, workflow: Path | None = None) -> tuple[Path, Path]:
    """A dispatch target plus the committed workflow config it dispatches."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 5}}}',
        encoding="utf-8",
    )
    if workflow is not None:
        return repo, workflow
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, committed


def _seed_journal(*, repo: Path, records: list[dict[str, object]]) -> None:
    journal = repo / _JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _exhaustion_record(*, provider: str, expires_at: str) -> dict[str, object]:
    return {
        "stage": "provider-exhaustion-observed",
        "work_item_id": "bd-ib-earlier",
        "provider": provider,
        "governing_condition": _GOVERNING_CONDITION,
        "record_expires_at": expires_at,
    }


def _journal_records(*, repo: Path) -> list[dict[str, Any]]:
    text = (repo / _JOURNAL).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _green_recording(calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in that records each launch and returns green."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=11,
            merge_sha="feed01",
            detail="merged",
        )

    return _run_dispatch


def _ceiling_recording(*, cause: str) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in whose terminal is built by PRODUCTION code.

    Only the vendor's own sentence is supplied here. The classification, the
    provider attribution and the terminal outcome all come from
    `fabro_run_terminal_outcome` — the same function a live run's terminal goes
    through — so the exhaustion record this drives is written from an input the
    system genuinely produces rather than from a provider value hand-written
    into a fixture.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        payload: list[object] = [
            {
                "status": {"kind": "failed"},
                "failure": {"causes": [_ACP_WRAPPER, cause], "category": "transient_infra"},
            }
        ]
        outcome = fabro_run_terminal_outcome(
            outcome_type=DispatchOutcome,
            plan=plan,
            run_id="01CEILING",
            inspect=FabroInspectResult(
                command=CommandResult(exit_code=0, stdout="", stderr=""),
                payload=payload,
                status_kind=fabro_status_kind_from_payload(payload=payload),
                failure=fabro_failure_detail_from_payload(payload=payload),
            ),
            exit_code=1,
            stderr="",
        )
        assert outcome is not None
        return outcome

    return _run_dispatch


def _graph_recording(graphs: list[str]) -> Callable[..., DispatchOutcome]:
    """A stand-in that captures the graph the Dispatcher hands the sandbox.

    The payload is torn down when the run returns, so the capture happens
    HERE — at the moment the launcher would read it — rather than after
    `main` returns, when the rendered graph no longer exists.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        overlay = plan.workflow_toml.read_text(encoding="utf-8")
        graph = workflow_graph_path(
            committed_text=overlay,
            workflow_dir=plan.workflow_toml.parent,
        )
        assert graph is not None
        graphs.append(graph.read_text(encoding="utf-8"))
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=11,
            merge_sha="feed01",
            detail="merged",
        )

    return _run_dispatch


def _dead_implementer_recording(causes: list[str]) -> Callable[..., DispatchOutcome]:
    """A stand-in returning the terminal a dead-implementer truncation produces.

    The surfaced cause is the implementer breaker's own sentinel, which the
    shipped graph emits on stderr before exiting non-green; the paired case
    asserts that same literal is present in the graph the Dispatcher
    materialized, so producer and consumer are compared rather than each being
    asked about itself.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        cause = (
            f"{_DEAD_IMPLEMENTER_MARKER}: unchanged tree after implementer; "
            "no janitor/review/disposition rounds will run against dispatch base"
        )
        causes.append(cause)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail=cause,
            fabro_run_id="01DEADIMPL",
            fabro_failure_cause=cause,
            fabro_failure_category="deterministic",
            fabro_failure_signature="fabro|deterministic|dead-implementer",
        )

    return _run_dispatch


def _loop(*, repo: Path, workflow: Path) -> int:
    return main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _attention(*, repo: Path, monkeypatch: pytest.MonkeyPatch) -> list[AttentionItem]:
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    return build_attention(project_root=repo, repo_name="repo", include_hygiene=False)


# ---------------------------------------------------------------------------
# Scenario 60 — an observed provider exhaustion refuses admission, and expires.
# ---------------------------------------------------------------------------


def test_scenario60_unexpired_exhaustion_refuses_admission_without_disposing_the_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpired record refuses the dispatch and leaves the item ready."""
    repo, workflow = _repo(tmp_path=tmp_path)
    item = _item(id="bd-ib-codex-held")
    append_work_item(path=_config(), item=item)
    _seed_journal(
        repo=repo,
        records=[_exhaustion_record(provider="codex", expires_at=_UNEXPIRED)],
    )
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    exit_code = _loop(repo=repo, workflow=workflow)

    # Not admitted and no sandbox run launched.
    assert exit_code == 1
    assert calls == []
    stored = _stored()[item.id]
    # The item is neither started nor disposed: still ready, never blocked.
    assert (stored.status, stored.assignee, stored.resolution) == ("ready", None, None)
    records = _journal_records(repo=repo)
    assert "ledger-admit" not in {record.get("stage") for record in records}
    [refusal] = [
        record for record in records if record.get("stage") == "provider-exhaustion-refusal"
    ]
    # The refusal is journaled with all four fields the contract requires of a
    # containment refusal: the work-item, the condition, the provider, the expiry.
    assert (
        refusal.items()
        >= {
            "work_item_id": item.id,
            "governing_condition": _GOVERNING_CONDITION,
            "provider": "codex",
            "record_expires_at": _UNEXPIRED,
        }.items()
    )


def test_scenario60_an_expired_record_refuses_nothing_on_a_later_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once the record's expiry has passed, admission resumes normally."""
    repo, workflow = _repo(tmp_path=tmp_path)
    item = _item(id="bd-ib-after-expiry")
    append_work_item(path=_config(), item=item)
    _seed_journal(
        repo=repo,
        records=[_exhaustion_record(provider="codex", expires_at=_EXPIRED)],
    )
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    exit_code = _loop(repo=repo, workflow=workflow)

    assert exit_code == 0
    assert calls == [item.id]
    assert _stored()[item.id].status == "active"
    assert "provider-exhaustion-refusal" not in {
        record.get("stage") for record in _journal_records(repo=repo)
    }


def test_scenario60_a_provider_with_no_record_is_admitted_normally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Holding no unexpired record for a provider refuses nothing against it.

    The Given of this scenario is an ABSENT record, so that is what is set up.
    Its discriminator is the unexpired-record case above: a gate that refused
    nothing at all would pass here and fail there.
    """
    repo, workflow = _repo(tmp_path=tmp_path)
    item = _item(id="bd-ib-other-provider")
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    exit_code = _loop(repo=repo, workflow=workflow)

    assert exit_code == 0
    assert calls == [item.id]
    assert _stored()[item.id].status == "active"
    journal = repo / _JOURNAL
    for provider in ("anthropic", "codex"):
        assert (
            active_provider_exhaustion(
                provider=provider,
                journal_path=journal,
                now_iso="2026-08-28T00:00:00Z",
            )
            is None
        )


def test_scenario60_the_record_names_the_vendor_that_actually_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An observed Anthropic ceiling is recorded — and refuses — as Anthropic.

    Detection is vendor-agnostic, so a fixed provider label recorded this
    Anthropic ceiling under the Codex vendor: the next dispatch was then
    refused citing a Codex exhaustion that never happened, while containment
    held no record for the vendor that had actually refused.

    Both halves are asserted from ONE production-written record: the vendor
    that refused is covered, and the vendor that did not is not — the second is
    what a fixed label cannot get right, whichever constant it picks.
    """
    repo, workflow = _repo(tmp_path=tmp_path)
    observed = _item(id="bd-ib-anthropic-ceiling", rank="a1")
    append_work_item(path=_config(), item=observed)
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _ceiling_recording(cause=_ANTHROPIC_SPEND_LIMIT),
    )

    assert _loop(repo=repo, workflow=workflow) == 1

    [record] = [
        entry
        for entry in _journal_records(repo=repo)
        if entry.get("stage") == "provider-exhaustion-observed"
    ]
    assert record["provider"] == "anthropic"
    assert record["governing_condition"] == _GOVERNING_CONDITION
    journal = repo / _JOURNAL
    now = record["at"]
    assert active_provider_exhaustion(provider="codex", journal_path=journal, now_iso=now) is None
    covered = active_provider_exhaustion(
        provider="anthropic",
        journal_path=journal,
        now_iso=now,
    )
    assert covered is not None

    # The next pass is refused, and the refusal names the vendor that refused.
    held = _item(id="bd-ib-held-behind-anthropic", rank="a2")
    append_work_item(path=_config(), item=held)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    assert _loop(repo=repo, workflow=workflow) == 1

    assert calls == []
    assert _stored()[held.id].status == "ready"
    [refusal] = [
        entry
        for entry in _journal_records(repo=repo)
        if entry.get("stage") == "provider-exhaustion-refusal"
    ]
    assert refusal["provider"] == "anthropic"
    assert refusal["work_item_id"] == held.id


def test_scenario60_admission_never_reads_provider_credential_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exhaustion signal is observed, never derived from a credential file.

    Two independent instruments, because either alone has a silent failure
    mode. The credential file DECLARES an exhausted window, so a dispatcher
    deriving the signal from it would refuse — and every `Path.read_text` the
    pass performs is recorded, so a read of that file is caught even if it
    happened to change nothing.
    """
    repo, workflow = _repo(tmp_path=tmp_path)
    credential = tmp_path / "home" / ".codex" / "auth.json"
    credential.parent.mkdir(parents=True)
    _ = credential.write_text(
        json.dumps({"tokens": {"access_token": "t"}, "usage": "usage_limit_exceeded"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    item = _item(id="bd-ib-credential-control")
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    read_paths: list[str] = []
    original_read_text = Path.read_text

    def _recording_read_text(*args: Any, **kwargs: Any) -> str:
        read_paths.append(str(args[0]))
        return original_read_text(*args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _recording_read_text)

    exit_code = _loop(repo=repo, workflow=workflow)

    monkeypatch.undo()

    assert exit_code == 0
    # The instrument can see reads: the pass demonstrably read the target's own
    # configuration, so an empty credential result is a real absence.
    assert str(repo / ".livespec.jsonc") in read_paths
    assert str(credential) not in read_paths
    assert calls == [item.id]
    assert _stored()[item.id].status == "active"
    # No exhaustion record was manufactured from the credential material.
    assert "provider-exhaustion-observed" not in {
        record.get("stage") for record in _journal_records(repo=repo)
    }


def test_scenario60_a_containment_refusal_never_disposes_a_needs_human_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A needs-human block survives a containment pass and stays surfaced."""
    repo, workflow = _repo(tmp_path=tmp_path)
    blocked = _item(id="bd-ib-needs-human", status="blocked", blocked_reason="needs-human")
    held = _item(id="bd-ib-ready-held", rank="a3")
    append_work_item(path=_config(), item=blocked)
    append_work_item(path=_config(), item=held)
    _seed_journal(
        repo=repo,
        records=[_exhaustion_record(provider="codex", expires_at=_UNEXPIRED)],
    )
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    exit_code = _loop(repo=repo, workflow=workflow)

    # The containment condition fired on this pass — the ready sibling is held.
    assert exit_code == 1
    assert calls == []
    assert "provider-exhaustion-refusal" in {
        record.get("stage") for record in _journal_records(repo=repo)
    }
    # The needs-human item is not auto-resolved by that refusal.
    stored = _stored()[blocked.id]
    assert (stored.status, stored.resolution) == ("blocked", None)
    # And it is still surfaced through the needs-attention awareness surface.
    attention = _attention(repo=repo, monkeypatch=monkeypatch)
    [valve] = [item for item in attention if item.source_ref.work_item == blocked.id]
    assert valve.handoff.action_id == f"resolve-blocked:{blocked.id}:ready"


# ---------------------------------------------------------------------------
# Scenario 61 — a dead implementer does not spend the second vendor.
# ---------------------------------------------------------------------------


def test_scenario61_the_dispatched_workflow_truncates_an_unchanged_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The graph the Dispatcher hands the sandbox stops before the second vendor."""
    repo, workflow = _repo(tmp_path=tmp_path, workflow=_SHIPPED_WORKFLOW)
    item = _item(id="bd-ib-unchanged-tree")
    append_work_item(path=_config(), item=item)
    graphs: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _graph_recording(graphs))

    exit_code = _loop(repo=repo, workflow=workflow)

    assert exit_code == 0
    [graph] = graphs
    # The implementer's output is gated on a real dispatch-base diff, and the
    # unchanged arm carries the breaker's own sentinel.
    node = re.search(r"\bimplementation_diff\s*\[(?P<body>[^\]]*)\]", graph)
    assert node is not None
    assert "git diff --quiet origin/{{ inputs.default_branch }}...HEAD" in node.group("body")
    assert re.search(r"\bimplement\s*->\s*implementation_diff\b(?![^\n]*condition=)", graph)
    assert re.search(
        r"\bimplementation_diff\s*->\s*dead_implementer\b(?![^\n]*condition=)",
        graph,
    )
    breaker = re.search(r"\bdead_implementer\s*\[(?P<body>[^\]]*)\]", graph, re.DOTALL)
    assert breaker is not None
    assert _DEAD_IMPLEMENTER_MARKER in breaker.group("body")
    # It is a terminal: nothing leaves it, so no review, review-fix or
    # disposition round can be reached from an unchanged tree.
    assert re.search(r"\bdead_implementer\s*->", graph) is None
    # And the implementer cannot reach the downstream rounds by any other edge.
    assert re.search(r"\bimplement\s*->\s*(janitor|review|review_fix|disposition)\b", graph) is None


def test_scenario61_a_changed_tree_still_reaches_review_normally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The breaker truncates nothing when the implementer did change the tree."""
    repo, workflow = _repo(tmp_path=tmp_path, workflow=_SHIPPED_WORKFLOW)
    item = _item(id="bd-ib-changed-tree")
    append_work_item(path=_config(), item=item)
    graphs: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _graph_recording(graphs))

    exit_code = _loop(repo=repo, workflow=workflow)

    assert exit_code == 0
    [graph] = graphs
    assert re.search(
        r'\bimplementation_diff\s*->\s*janitor\b[^\n]*condition="outcome=succeeded"',
        graph,
    )
    assert re.search(r'\bjanitor\s*->\s*review\b[^\n]*condition="outcome=succeeded"', graph)


def test_scenario61_the_truncation_is_journaled_and_disposes_of_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead-implementer terminal is journaled against the item, not disposed."""
    repo, workflow = _repo(tmp_path=tmp_path, workflow=_SHIPPED_WORKFLOW)
    item = _item(id="bd-ib-truncated")
    append_work_item(path=_config(), item=item)
    causes: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _dead_implementer_recording(causes))

    exit_code = _loop(repo=repo, workflow=workflow)

    assert exit_code == 1
    records = _journal_records(repo=repo)
    outcomes = [record for record in records if record.get("stage") == "outcome"]
    [truncation] = [
        record
        for record in outcomes
        if _DEAD_IMPLEMENTER_MARKER in str(record["outcome"].get("fabro_failure_cause"))
    ]
    # The truncation is journaled with the work-item id and the governing
    # condition — the two fields the contract requires of it.
    assert truncation["outcome"]["work_item_id"] == item.id
    assert _DEAD_IMPLEMENTER_MARKER in str(truncation["outcome"]["detail"])
    # Nothing is accepted, completed or closed off the back of it.
    stages = {record.get("stage") for record in records}
    assert "ledger-complete" not in stages
    assert "ledger-accept" not in stages
    stored = _stored()[item.id]
    assert (stored.status, stored.resolution) == ("active", None)
