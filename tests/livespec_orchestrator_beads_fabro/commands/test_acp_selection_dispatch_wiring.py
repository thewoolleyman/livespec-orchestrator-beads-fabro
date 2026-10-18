"""The admission verdict REACHES the per-node selection on the production path.

Binds the "Per-node selection" paragraph of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -- "Selection is made once per
dispatch from one consistent read of the availability evidence" -- to the chain
of calls a real dispatch actually takes, which is the one thing
`test_acp_node_selection.py` cannot establish: that file hands `prepare_acp_nodes`
a verdict directly, so it proves the SELECTION is correct while leaving open
whether any dispatch ever supplies one.

WHY THAT GAP IS WORTH ITS OWN FILE. With no production supplier the operand
defaults to absent, every node pins to candidate zero, and the journal then
records `selected_index: 0` with no holds -- which is byte-for-byte what a
genuinely unheld chain records. So the gauge reports healthy exactly when the
condition it exists to surface is present, and a domain-held primary is admitted
and then launched. Nothing downstream can tell the two apart, which is why the
wiring is asserted here rather than left to the selection's own tests.

THE VERDICT COMES OUT OF THE VALVE, NEVER BACK INTO IT. `admit_and_select`
resolves one verdict per pass and deliberately takes none as an input, because a
caller able to supply one is a caller able to supply a stale one. The only honest
way for the launch to select from "the same `AcpPreflightVerdict` the admission
evaluation used" is therefore for the valve to CARRY it out on its result, and
for each launch site to hand that same object down. Each link of that chain is
asserted separately below: a single end-to-end test would pass just as well with
the verdict re-resolved halfway along, which is the second read the clause
forbids.

THE BOTTOM OF THE CHAIN IS ASSERTED BEHAVIOURALLY, not by signature. The two
`materialize_dispatch` cases run the real layer merge, chain attach and selection
over a governed repository and read the adapter bytes back, so they would fail if
the operand were accepted and then dropped. The links above it are forwarding
claims, and a capture is the only thing that can state them.
"""

from __future__ import annotations

import argparse
import inspect
import json
import shutil
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility_module,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop as loop_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_record as record_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_wave as wave_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_resume_command as resume_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_launch as run_module
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import PreflightInputs
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import AcpHoldLedger
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_node_selection import ACP_NODE_SELECTION_STAGE
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
    no_fallback_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_chain_sources import (
    repository_acp_chain_sources,
    workflow_scoped_dispatcher_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    RecoveryRouting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_command import (
    _admit_and_dispatch_resume,  # pyright: ignore[reportPrivateUsage]
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_launch import (
    admit_and_dispatch_target,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHIPPED_WORKFLOW = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_VARIANT_DIR = ".fabro/workflows/implement-work-item"

_NODE = "implement"
_PRIMARY_DOMAIN = "primary-domain"
_PRIMARY_KEY = "primary-model"
_FALLBACK_DOMAIN = "fallback-domain"
_FALLBACK_KEY = "fallback-model"
_PRIMARY_COMMAND = "primary-acp --stdio"
_FALLBACK_COMMAND = "fallback-acp --stdio"


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-wvj4rk",
        type="task",
        status="ready",
        title="A dispatchable item",
        description="## Definition of Done\n\n- It dispatches.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(*, item_id: str) -> DispatchOutcome:
    """A stand-in launch result, so a capture need not run a Fabro dispatch."""
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=None,
        merge_sha=None,
        detail="captured",
    )


def _unused(**_kwargs: object) -> None:
    """A seam this file deliberately does not exercise."""
    return None


def _no_labels(**_kwargs: object) -> tuple[str, ...]:
    """The label read, reduced to the empty set it would return for a bare item."""
    return ()


def _same_args(**kwargs: object) -> object:
    """A per-dispatch ledger pin reduced to the identity on the args it is given."""
    return kwargs["args"]


def _assert_verdict_operand(*, function: object, name: str) -> None:
    """Prove the seam even HAS the operand before handing it one.

    Calling a function with a keyword it does not declare raises `TypeError`,
    which reports an unimplemented thread as a crash rather than as the claim
    that failed. This is the genuine assertion instead.
    """
    assert "verdict" in inspect.signature(cast("Any", function)).parameters, (
        f"{name} declares no `verdict` operand, so the admission verdict has no "
        "route to the per-node selection"
    )


def _candidate(*, key: str, domain: str, command: str) -> dict[str, object]:
    executable, _, argument = command.partition(" ")
    return {
        "display_name": f"{key} adapter",
        "candidate_key": key,
        "availability_key": domain,
        "command": executable,
        "args": [argument],
    }


def _chained_repo(*, tmp_path: Path) -> Path:
    """A governed repository whose `implement` node declares a two-link chain.

    The workflow is a real copy of the shipped one, so the graph that decides
    which nodes are admission-required is the production graph rather than a
    fixture that might make the configured node unreachable.
    """
    repo = tmp_path / "repo"
    variant = repo / _VARIANT_DIR
    variant.parent.mkdir(parents=True)
    _ = shutil.copytree(_SHIPPED_WORKFLOW, variant)
    chain = {
        **_candidate(key=_PRIMARY_KEY, domain=_PRIMARY_DOMAIN, command=_PRIMARY_COMMAND),
        "fallbacks": [
            _candidate(key=_FALLBACK_KEY, domain=_FALLBACK_DOMAIN, command=_FALLBACK_COMMAND)
        ],
    }
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": {_NODE: chain}}},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _primary_held_verdict(*, repo: Path) -> AcpPreflightVerdict:
    """The verdict admission would resolve while the primary's domain is held.

    Built through `build_acp_preflight_verdict` over this repository's OWN
    resolved chains, for the reason `test_acp_node_selection.py` gives: a
    hand-assembled `NodePreflight` proves a parameter is read, while the real
    machinery proves the candidate objects the two halves exchange compare
    equal -- the one way the thread can be wired correctly and still select the
    wrong position.
    """
    hold = AcpAvailabilityHold(
        schema_version=1,
        observation_id="acp-obs-0123456789abcdef",
        scope="availability-domain",
        hold_key=_PRIMARY_DOMAIN,
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-16T10:00:00Z",
        expires_at="2026-10-16T22:00:00Z",
    )
    block = workflow_scoped_dispatcher_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    return build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=AcpHoldLedger(holds=(hold,), unobservable=(), observation_ids=frozenset()),
        inputs=PreflightInputs(holds=(hold,), builtin_pairs=builtin_pairs),
    )


class _RecordingJournal:
    """Collects journal records so a dispatch's own selection record can be read."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _selection_record(*, journal: _RecordingJournal) -> dict[str, Any]:
    """The configured node's row out of this dispatch's one selection record."""
    [record] = [
        entry for entry in journal.records if entry.get("stage") == ACP_NODE_SELECTION_STAGE
    ]
    selections = cast("dict[str, dict[str, Any]]", record["selections"])
    return selections[_NODE]


def test_the_admission_valve_carries_out_the_verdict_its_own_evaluation_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The valve's result names the one verdict the pass evaluated.

    Identity, not equality: the whole guarantee is that the launch selects from
    the SAME object, and two separately-built verdicts over an unchanged
    repository compare equal, so an equality assertion would pass against a
    second resolution.
    """
    assert "verdict" in {field.name for field in fields(admission_module.Admission)}, (
        "Admission carries no `verdict`, so the evaluation that admitted an item "
        "cannot reach the dispatch that launches it"
    )
    evaluated = no_fallback_verdict()

    def _evaluate(**_kwargs: object) -> AcpPreflightVerdict:
        return evaluated

    def _config(**_kwargs: object) -> Path:
        return tmp_path

    monkeypatch.setattr(admission_module, "resolve_acp_preflight", _evaluate)
    monkeypatch.setattr(admission_module, "store_config", _config)
    monkeypatch.setattr(admission_module, "update_work_item_status", _unused)
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", _no_labels)

    admission = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        enforce_cap=False,
    )

    assert admission.verdict is evaluated


def test_a_materialized_dispatch_renders_the_candidate_the_verdict_selected(
    tmp_path: Path,
) -> None:
    """Scenario 127, through the seam a dispatch materializes its adapters with.

    The primary's own bytes are asserted ABSENT as well as the fallback's
    present: a materialization that rendered both, or that recorded the
    fallback while rendering the primary, satisfies every claim about the
    fallback on its own.
    """
    _assert_verdict_operand(function=materialize_dispatch, name="materialize_dispatch")
    repo = _chained_repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    materialized = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-wvj4rk-selected",
        journal=journal,
        verdict=_primary_held_verdict(repo=repo),
    )

    assert not isinstance(materialized, MaterializationRefusal), materialized
    rendered = materialized.acp_nodes.nodes[_NODE].rendered
    assert rendered.endswith(_FALLBACK_COMMAND), rendered
    assert "primary-acp" not in rendered, rendered
    selection = _selection_record(journal=journal)
    assert selection["selected_index"] == 1
    assert selection["selected_candidate_key"] == _FALLBACK_KEY
    assert [hold["availability_key"] for hold in selection["holds"]] == [_PRIMARY_DOMAIN]


def test_a_materialized_dispatch_with_no_verdict_keeps_its_configured_primary(
    tmp_path: Path,
) -> None:
    """The control, and the additive guarantee for every caller that has none.

    Without it an implementation that always rendered the LAST candidate would
    satisfy the case above exactly as well as a correct one -- and the reconcile
    and check subcommands, which resolve no verdict, would silently move bytes
    nobody asked them to move.
    """
    repo = _chained_repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    materialized = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-wvj4rk-primary",
        journal=journal,
    )

    assert not isinstance(materialized, MaterializationRefusal), materialized
    rendered = materialized.acp_nodes.nodes[_NODE].rendered
    assert rendered.endswith(_PRIMARY_COMMAND), rendered
    assert "fallback-acp" not in rendered, rendered
    selection = _selection_record(journal=journal)
    assert selection["selected_index"] == 0
    assert selection["selected_candidate_key"] == _PRIMARY_KEY


def test_the_dispatch_record_hands_its_verdict_to_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`record_dispatch` is the only caller of `materialize_dispatch`."""
    _assert_verdict_operand(function=record_module.record_dispatch, name="record_dispatch")
    seen: list[dict[str, object]] = []

    def _materialize(**kwargs: object) -> MaterializationRefusal:
        seen.append(kwargs)
        return MaterializationRefusal(stage="captured", detail="captured")

    monkeypatch.setattr(record_module, "read_dispatch_labels", _no_labels)
    monkeypatch.setattr(record_module, "materialize_dispatch", _materialize)
    evaluated = no_fallback_verdict()

    _ = record_module.record_dispatch(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
        identity=DispatchJournalIdentity(dispatch_id="dispatch-0", dispatch_factory=None),
        verdict=evaluated,
    )

    assert seen[0]["verdict"] is evaluated


def test_a_launched_dispatch_hands_its_verdict_to_the_dispatch_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dispatch_one` is the entry point every launch site calls."""
    _assert_verdict_operand(function=loop_module.dispatch_one, name="dispatch_one")
    seen: list[dict[str, object]] = []
    item = _item()

    def _record(**kwargs: object) -> DispatchOutcome:
        seen.append(kwargs)
        return _outcome(item_id=item.id)

    monkeypatch.setattr(loop_module, "record_dispatch", _record)
    monkeypatch.setattr(loop_module, "release_pre_run_claim_if_needed", _unused)
    evaluated = no_fallback_verdict()

    _ = loop_module.dispatch_one(
        args=argparse.Namespace(fabro_factory_target=None),
        repo=tmp_path,
        item=item,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
        verdict=evaluated,
    )

    assert seen[0]["verdict"] is evaluated


def _capture_launches(
    *, module: Any, monkeypatch: pytest.MonkeyPatch, item: WorkItem, verdict: AcpPreflightVerdict
) -> list[dict[str, object]]:
    """Stand in the valve and the launch, so only the hand-off is exercised."""
    seen: list[dict[str, object]] = []

    def _dispatch(**kwargs: object) -> DispatchOutcome:
        seen.append(kwargs)
        return _outcome(item_id=item.id)

    def _admit(**_kwargs: object) -> admission_module.Admission:
        return admission_module.Admission(admitted=[item], deferred=[], refused=[], verdict=verdict)

    monkeypatch.setattr(module, "dispatch_one", _dispatch)
    monkeypatch.setattr(module, "admit_and_select", _admit)
    monkeypatch.setattr(module, "args_with_dispatch_factory_target", _same_args)
    return seen


def test_the_loop_wave_launches_every_admitted_item_with_the_admission_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The queue-draining path: the wave launches what the valve admitted."""
    item = _item()
    evaluated = no_fallback_verdict()
    seen = _capture_launches(
        module=wave_module, monkeypatch=monkeypatch, item=item, verdict=evaluated
    )
    monkeypatch.setattr(wave_module, "args_with_dispatch_workflow_name", _same_args)
    monkeypatch.setattr(wave_module, "post_admission_publish_branch_reclaim", _unused)
    monkeypatch.setattr(wave_module, "await_usable_credential", _unused)

    _ = wave_module.dispatch_loop_wave(
        args=argparse.Namespace(budget=1, parallel=1),
        repo=tmp_path,
        items=[item],
        selected_candidates=[item],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
        rework=ReworkPass(),
    )

    assert seen[0]["verdict"] is evaluated


def test_a_targeted_dispatch_launches_with_the_admission_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dispatch --item`: the operator override narrows the selection only."""
    item = _item()
    evaluated = no_fallback_verdict()
    seen = _capture_launches(
        module=run_module, monkeypatch=monkeypatch, item=item, verdict=evaluated
    )
    monkeypatch.setattr(run_module, "args_with_dispatch_workflow_name", _same_args)
    monkeypatch.setattr(run_module, "post_admission_publish_branch_reclaim", _unused)

    _ = admit_and_dispatch_target(
        args=argparse.Namespace(),
        repo=tmp_path,
        items=[item],
        target=item,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
        marked=False,
        # The EMPTY routing, which is what a selection recovery routing never
        # measured looks like: every item reads back no route, so both pins
        # apply and nothing about recovery enters this case. The routing step's
        # own decisions are exercised in the `recovery_routing` modules; here it
        # must not shadow the verdict hand-off under test.
        routing=RecoveryRouting(routes=()),
    )

    assert seen[0]["verdict"] is evaluated


def test_a_resumed_dispatch_launches_with_the_admission_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`resume --item`: a resume is subject to the ordinary valve, so also to it."""
    item = _item()
    evaluated = no_fallback_verdict()
    seen = _capture_launches(
        module=resume_module, monkeypatch=monkeypatch, item=item, verdict=evaluated
    )

    _ = _admit_and_dispatch_resume(
        args=argparse.Namespace(),
        repo=tmp_path,
        items=[item],
        item=item,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
    )

    assert seen[0]["verdict"] is evaluated
