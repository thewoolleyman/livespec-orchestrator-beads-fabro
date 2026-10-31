"""Scenario 206's human way through a misjudged spec-change-tier hold.

`SPECIFICATION/scenarios.md` Scenario 206 gives a held feature a human way
through: "A human attests an existing clause and releases a misjudged hold", "An
attested release of a held pending-rework item keeps it active for rework", "An
attested release refuses a heading the specification does not carry", and "An
attestation survives an unrelated revision and a rejected proposal, and voids on a
changed clause or input". Every case drives the real `release-spec-tier` human
valve through `run_human_valve_action`, over the real intake route, the real
pre-dispatch wall, the real spec tree and the real store/client seam.

THE JUDGE IS STOOD IN AT THE EXECUTABLE and the Definition-of-Done rubric judgement
is stood DOWN, so the judge's reply sequence lines up with the spec-change-tier
classification alone: the rubric is not this scenario's subject, and its calls
would otherwise consume replies the classification is waiting for.

EVERY REFUSAL IS ASSERTED TOGETHER WITH THE HOLD STANDING. A valve that refused and
released anyway returns the same refusal payload; only the wall still refusing the
item, and the ledger carrying no attestation, show that nothing was written.

THE WALL IS DRIVEN, NOT THE GATE, because "the pre-dispatch wall treats the
citation as stated" is a claim about what the wall does NOT refuse, and a gate
returning a verdict cannot show that.
"""

from __future__ import annotations

import argparse
import json
import stat
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro import intake_dor
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    update_work_item_rework_pending,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.unsafe import unsafe_perform_io

_ITEM = "bd-ib-release"
_HEADING = "## A governing clause"
_TOPIC = "a-new-observable-behaviour"
_TITLE = "A new observable behaviour"
_ACTION = f"release-spec-tier:{_ITEM}:{_HEADING}"
_ACTOR = InvokerIdentity(invoker="human:chad", invoker_source="flag")
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_STAGE = "human-valve-release-spec-tier"
_EARLIER_WALL_ROWS = (
    "implementation_pr_override_refusal",
    "fabro_currency_refusal",
    "pre_dispatch_criteria_refusal",
    "dod_judgement_refusal",
    "definition_of_done_workflow_refusal",
    "proof_assets_refusal_for_items",
    "proof_credentials_refusal_for_items",
    "codex_credential_refusal_for_items",
)


def _unstated(*, heading: str = _HEADING) -> str:
    return (
        '{"kind": "unstated", "stated_by": [], "generalization_target": '
        f'"{heading}", "rationale": "the ratified text does not state it"}}'
    )


@dataclass(frozen=True, kw_only=True)
class _Run:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(kw_only=True)
class _Runner:
    """The injected valve seam: every `fabro ps` answers the one canned result."""

    result: _Run = field(default_factory=lambda: _Run(returncode=0, stdout="[]"))
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> _Run:
        self.calls.append(argv)
        _ = cwd
        return self.result


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    monkeypatch.setattr(
        intake_dor,
        "judge_item_definition_of_done",
        lambda **_kwargs: SimpleNamespace(holds=False),
    )
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _spec_text(*, heading: str = _HEADING, body: str = "The clause body.") -> str:
    return f"# Contracts\n\n{heading}\n\n{body}\n"


def _repo(*, tmp_path: Path, heading: str = _HEADING) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001" / "proposed_changes").mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"tenant": "livespec-impl-beads",'
        ' "prefix": "bd-ib", "server_user": "livespec-impl-beads",'
        ' "database": "livespec-impl-beads", "bd_path": "bd", "fake": true},'
        ' "dispatcher": {"auto_approve_ready": true,'
        ' "acp_nodes": {"dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}}}}}',
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(_spec_text(heading=heading), encoding="utf-8")
    return repo


def _revise(*, repo: Path, version: int, text: str, decision: str | None = None) -> None:
    """Land a new specification version, optionally carrying a decided proposal."""
    changes = repo / "SPECIFICATION" / "history" / f"v{version:03d}" / "proposed_changes"
    changes.mkdir(parents=True, exist_ok=True)
    _ = (repo / "SPECIFICATION" / "contracts.md").write_text(text, encoding="utf-8")
    if decision is not None:
        _ = (changes / f"{_TOPIC}.md").write_text("the proposal\n", encoding="utf-8")
        _ = (changes / f"{_TOPIC}-revision.md").write_text(
            f"---\nproposal: {_TOPIC}.md\ndecision: {decision}\n---\n", encoding="utf-8"
        )


def _item(*, heading: str = _HEADING, **overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": _ITEM,
        "type": "bug",
        "status": "pending-approval",
        "title": _TITLE,
        "description": (
            f"## Definition of Done\n\n- The slice lands its change.\n\nReferences: {heading}\n"
        ),
        "origin": "freeform",
        "gap_id": None,
        "rank": "a0",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-10-28T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "acceptance_policy": "ai-only",
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _install_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]
) -> None:
    ledger = tmp_path / "judge-calls"
    script = tmp_path / "fake-judge"
    arms = "\n".join(
        f"{index})\n  cat <<'REPLY'\n{reply}\nREPLY\n  ;;"
        for index, reply in enumerate(replies, start=1)
    )
    _ = script.write_text(
        "#!/bin/sh\n"
        f"echo call >> {ledger}\n"
        f"calls=$(wc -l < {ledger} | tr -d ' ')\n"
        f"case $calls in\n{arms}\n*)\n  exit 1\n  ;;\nesac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))
    for name in _EARLIER_WALL_ROWS:
        monkeypatch.setattr(wall, name, lambda **_kwargs: None)


def _route(*, repo: Path) -> str:
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )
    return unsafe_perform_io(
        apply_intake_dor(path=_config(repo=repo), item_id=_ITEM, checklist=checklist).unwrap()
    )


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))[_ITEM]


def _comments(*, repo: Path) -> str:
    return "\n".join(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM)
    )


def _wall(*, repo: Path, tmp_path: Path) -> int | None:
    return wall.pre_dispatch_wall_exit(
        args=argparse.Namespace(workflow_name=None, workflow=None, items=[]),
        repo=repo,
        items=[_stored(repo=repo)],
        journal=JournalFile(path=tmp_path / "journal.jsonl", identity="role:test"),
    )


def _release(
    *, repo: Path, action: str = _ACTION, runner: _Runner | None = None
) -> dict[str, object]:
    return run_human_valve_action(
        repo=repo,
        action_id=action,
        runner=_Runner() if runner is None else runner,
        identity=_ACTOR,
    )


def _held(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: object) -> Path:
    """A repository holding one filed feature held for its linked proposal."""
    repo = _repo(tmp_path=tmp_path)
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _unstated(), "feature", _unstated()),
    )
    append_work_item(path=_config(repo=repo), item=_item(**overrides))
    assert _route(repo=repo) == "pending-approval"
    assert _wall(repo=repo, tmp_path=tmp_path) == EXIT_UNGRADEABLE_CRITERIA
    return repo


def test_a_human_release_routes_an_auto_item_to_ready_and_the_wall_stops_refusing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _release(repo=repo)

    assert result["status"] == "green", result
    assert result["target_status"] == "ready"
    assert _stored(repo=repo).status == "ready"
    recorded = _comments(repo=repo)
    assert "livespec-spec-tier-attestation" in recorded
    assert "actor: human:chad" in recorded
    assert f"heading: {_HEADING}" in recorded
    assert "spec-file: contracts.md" in recorded
    assert "spec-version: 1" in recorded
    assert "clause-digest: sha256:" in recorded
    assert "tier: none" in recorded
    [entry] = [
        json.loads(line)
        for line in (repo / _JOURNAL).read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("stage") == _STAGE
    ]
    assert entry["work_item_id"] == _ITEM
    assert entry["heading"] == _HEADING
    assert entry["spec_file"] == "contracts.md"
    assert entry["spec_version"] == "1"
    assert str(entry["clause_digest"]).startswith("sha256:")
    assert entry["invoker"] == "human:chad"
    assert _wall(repo=repo, tmp_path=tmp_path) is None


def test_a_human_release_respects_committed_auto_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch, admission_policy="manual")

    result = _release(repo=repo)

    assert result["status"] == "green", result
    assert result["target_status"] == "ready"
    assert _stored(repo=repo).status == "ready"
    assert "tier: none" in _comments(repo=repo)
    assert _wall(repo=repo, tmp_path=tmp_path) is None


def test_a_release_of_a_held_pending_rework_item_keeps_it_active_for_rework(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)
    update_work_item_status(path=_config(repo=repo), item_id=_ITEM, status="active")
    update_work_item_rework_pending(path=_config(repo=repo), item_id=_ITEM, value=True)

    result = _release(repo=repo)

    assert result["status"] == "green", result
    stored = _stored(repo=repo)
    assert stored.status == "active"
    assert stored.rework_pending is True
    assert "tier: none" in _comments(repo=repo)
    assert _wall(repo=repo, tmp_path=tmp_path) is None


def test_a_heading_the_specification_does_not_carry_is_refused_and_the_hold_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)
    unknown = "## A clause nobody wrote"

    result = _release(repo=repo, action=f"release-spec-tier:{_ITEM}:{unknown}")

    assert result["status"] == "failed"
    assert result["domain_error"] == "unresolved-heading"
    assert unknown in str(result["summary"])
    assert _stored(repo=repo).status == "pending-approval"
    assert "livespec-spec-tier-attestation" not in _comments(repo=repo)
    assert _wall(repo=repo, tmp_path=tmp_path) == EXIT_UNGRADEABLE_CRITERIA


def test_an_item_that_is_not_held_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("bug",))
    append_work_item(path=_config(repo=repo), item=_item())
    assert _route(repo=repo) == "ready"

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == "not-held"
    assert _ITEM in str(result["summary"])
    assert "livespec-spec-tier-attestation" not in _comments(repo=repo)


def test_a_status_outside_the_valid_lanes_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)
    update_work_item_status(path=_config(repo=repo), item_id=_ITEM, status="acceptance")

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert "livespec-spec-tier-attestation" not in _comments(repo=repo)


def test_an_active_item_without_the_rework_marker_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)
    update_work_item_status(path=_config(repo=repo), item_id=_ITEM, status="active")

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"


def test_a_live_run_of_the_item_refuses_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)
    live = json.dumps([{"run_id": "01MLIVE", "status": "running", "goal": f"Work-item: {_ITEM}"}])

    result = _release(repo=repo, runner=_Runner(result=_Run(returncode=0, stdout=live)))

    assert result["status"] == "failed"
    assert result["domain_error"] == "live-run"
    assert "01MLIVE" in str(result["summary"])
    assert "livespec-spec-tier-attestation" not in _comments(repo=repo)


def test_an_unmeasurable_run_inventory_refuses_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _release(
        repo=repo, runner=_Runner(result=_Run(returncode=1, stderr="the engine did not answer"))
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "live-run"
    assert "could not be established" in str(result["summary"])
    assert "livespec-spec-tier-attestation" not in _comments(repo=repo)


def test_a_live_dispatch_ownership_lock_refuses_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = write_dispatch_lock(repo=repo, work_item_id=_ITEM, dispatch_id="dispatch-1")

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == "dispatch-lock-held"
    assert "livespec-spec-tier-attestation" not in _comments(repo=repo)


def test_a_heading_carrying_a_colon_is_released_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    heading = "## Scenario 7: a clause whose title carries a colon"
    repo = _repo(tmp_path=tmp_path, heading=heading)
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _unstated(heading=heading)),
    )
    append_work_item(path=_config(repo=repo), item=_item(heading=heading))
    assert _route(repo=repo) == "pending-approval"

    result = _release(repo=repo, action=f"release-spec-tier:{_ITEM}:{heading}")

    assert result["status"] == "green", result
    assert f"heading: {heading}" in _comments(repo=repo)


def test_a_heading_named_without_its_marker_resolves_the_same_clause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _release(repo=repo, action=f"release-spec-tier:{_ITEM}:A governing clause")

    assert result["status"] == "green", result
    assert f"heading: {_HEADING}" in _comments(repo=repo)


@pytest.mark.parametrize("action", [f"release-spec-tier:{_ITEM}", f"release-spec-tier:{_ITEM}:"])
def test_an_action_id_without_a_heading_is_not_a_valve_action(tmp_path: Path, action: str) -> None:
    result = run_human_valve_action(
        repo=_repo(tmp_path=tmp_path), action_id=action, runner=_Runner(), identity=_ACTOR
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-action-id"


def test_an_attestation_survives_a_rejected_proposal_and_voids_on_a_changed_clause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert _release(repo=repo)["status"] == "green"

    # A later revision that rejects the linked proposal and touches no cited clause.
    _revise(repo=repo, version=2, text=_spec_text(), decision="reject")
    assert _route(repo=repo) == "ready"
    assert _wall(repo=repo, tmp_path=tmp_path) is None

    # A revision that rewrites the cited clause voids the attestation: the item is
    # classified afresh and, the judgement still reporting it unstated, held again.
    _revise(repo=repo, version=3, text=_spec_text(body="The clause body, rewritten."))
    assert _wall(repo=repo, tmp_path=tmp_path) == EXIT_UNGRADEABLE_CRITERIA
