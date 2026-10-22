"""The selection-to-execution replay one reconciliation pass performs.

Binds the half of `SPECIFICATION/contracts.md` — cited at FILE level, because a
heading-level citation rots the moment the heading is reworded — that v127 left
undischarged: fallback observation is taken from "the Dispatcher's own
decisions", and reconciliation "replay[s] selection-to-execution observation
idempotently using factory, run, node attempt and selection identity".

EVERY CASE DRIVES `reconcile_runs`, never the pure reading underneath it, and
that is the whole point of this module. The pure reading was already correct and
already covered when this was filed; what was absent was any caller, so
`ingest_model_fallback_warning` had no production reader at all and the lane
reported a repository where no fallback had ever run. A case built on a
hand-written outcome map cannot fail for that reason — it passes against a
dispatcher that never looks at a run — so the outcome maps here are produced by
the real port out of real `fabro inspect` stdout.

THE OUTCOME KEYS ARE VISIT-QUALIFIED, which is the second thing a hand-built
map hides. Petri records its stage map as `<node>@<visit>` and the port returns
the keys as the engine wrote them, while a selection record names the CONFIGURED
node; comparing the two directly matches nothing, and matching nothing is
silent. So the `inspect` fixtures here spell `implement@1` rather than
`implement`, and a fixture that spelled the bare node would pass against the
build this module was written to red.

TWO NODES ARE SELECTED AND ONLY ONE IS EXECUTED throughout, because "the run
executed it" is a condition that cannot fail on a one-node fixture: a build that
minted a warning for every selected node would satisfy every assertion about the
executed one. The unexecuted node is the clause's own "an unexecuted preflight
selection for a node never reached emits no fallback warning" arriving as a
control rather than as a separate case.

EVERY RETIREMENT CASE SITS BESIDE THE NEAR-MISS IT MUST REFUSE, because each one
has a plausible wrong answer that looks exactly like the right one. A primary
run that STARTED BEFORE the warning, and one that executed but did not succeed,
both produce a well-formed executed primary attempt; a fallback-only chain edit
produces a live warning whose full-chain digest no longer matches anything the
repository declares. A build that cleared or superseded on any of the three
would report the lane clean while the primary was still falling over.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs as reconcile
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback import (
    model_fallback_warning_items,
)

_HP = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=None)
# A SECOND configured factory, which is what makes "the stamp names the factory
# that ran it" a condition that can fail: a replay addressing every factory with
# every run reads the same run twice and would mint from whichever answered.
_VPS = FactoryTarget(name="vps", server="https://vps.example:32276", dev_token=None)

_ITEM = "bd-ib-augqc2"
_NODE = "implement"
# The node the selection also rendered a fallback for and the run never reached.
_UNREACHED_NODE = "review"
_FALLBACK_RUN = "01SELECTED"
_PRIMARY_RUN = "01PRIMARY"
_WARNING_STAGE = "acp-model-fallback-observed"
_CLEARED_STAGE = "acp-model-fallback-cleared"
_SUPERSEDED_STAGE = "acp-model-fallback-superseded"
_UNAVAILABLE_STAGE = "acp-selection-outcomes-unavailable"
_FACT_ID = f"hygiene:model-fallback:target:{_NODE}"

_WARNED_AT = "2026-10-22T08:00:00Z"
_BEFORE_WARNING = "2026-10-22T07:00:00Z"
_AFTER_WARNING = "2026-10-22T09:00:00Z"
_GENERATION = "primary-1"


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI, recording every subcommand it was asked to run.

    `inspect_by_run` answers the engine record VERBATIM, so the outcome map the
    replay reads is produced by the real port rather than supplied to it; a run
    it does not name answers the non-zero exit an unreachable factory gives.
    Every other subcommand — the inventory this survey opens with — answers the
    empty listing, because no case here needs an orphan and the `ps` arm is
    exactly what makes "no inspect was spent" observable.
    """

    inspect_by_run: dict[str, str] = field(default_factory=dict)
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
        if argv[1] != "inspect":
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        answered = self.inspect_by_run.get(argv[2])
        if answered is None:
            return CommandResult(exit_code=7, stdout="", stderr="no such run")
        return CommandResult(exit_code=0, stdout=answered, stderr="")


@dataclass(kw_only=True)
class _Ledger:
    """A ledger fake that CAN record a write, so "no write" is a real finding.

    The replay lane writes the dispatch journal and nothing else, so every
    assertion that it touched no work-item rests on this fake being able to
    record one; `test_the_ledger_fake_records_a_write` is that control.
    """

    verbs: list[str] = field(default_factory=list)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        self.verbs.append(f"list_comments:{issue_id}")
        return []

    def add_comment(self, *, issue_id: str, body: str) -> None:
        _ = body
        self.verbs.append(f"add_comment:{issue_id}")


def _selection(
    *,
    at: str,
    dispatch_id: str,
    index: int,
    generation: str = _GENERATION,
    identity: str = "selection-1",
) -> dict[str, Any]:
    """One dispatch's per-node selection, as `append_acp_node_selection` writes it."""
    choice: dict[str, Any] = {
        "selection_identity": identity,
        "selected_index": index,
        "selected_candidate_key": "glm-acp-agent/zai/glm-5.1",
        "selected_availability_key": "zai",
        "primary_generation_digest": generation,
        "full_chain_digest": "chain-1",
    }
    return {
        "at": at,
        "stage": "acp-node-selection",
        "work_item_id": _ITEM,
        "dispatch_id": dispatch_id,
        "selections": {_NODE: choice, _UNREACHED_NODE: dict(choice)},
    }


def _run_stamp(
    *, dispatch_id: str, run_id: str, factory: FactoryTarget = _HP, at: str = _WARNED_AT
) -> dict[str, Any]:
    """The launch stamp that joins one selection to the run and factory it got."""
    return {
        "at": at,
        "stage": "dispatch-run-stamp",
        "work_item_id": _ITEM,
        "dispatch_id": dispatch_id,
        "run_id": run_id,
        "dispatch_factory": factory.name,
        "dispatch_factory_server": factory.server,
        "stamped": True,
    }


def _standing_warning(
    *, generation: str = _GENERATION, full_chain: str = "chain-1"
) -> dict[str, Any]:
    """One warning already on the journal, as an earlier pass appended it."""
    return {
        "at": _WARNED_AT,
        "stage": _WARNING_STAGE,
        "schema_version": 1,
        "warning_id": "acpwarn-standing",
        "node": _NODE,
        "occurred_at": _WARNED_AT,
        "candidate_display_name": "GLM 5.1",
        "candidate_key": "glm-acp-agent/zai/glm-5.1",
        "candidate_index": 1,
        "availability_key": "zai",
        "hold_key": "zai",
        "cause": "dispatcher-selection",
        "scope": "node",
        "primary_generation": generation,
        "full_chain": full_chain,
        "event_id": "selection:01EARLIER:selection-0",
        "work_item_id": _ITEM,
    }


def _stages(*, state: str = "succeeded") -> str:
    """One `fabro inspect` record whose stage map is keyed `<node>@<visit>`."""
    return json.dumps([{"run_id": _FALLBACK_RUN, "stages": {f"{_NODE}@1": {"state": state}}}])


def _checkpoint_outcomes(*, status: str = "succeeded") -> str:
    """One pinned-engine record, whose `node_outcomes` carry no visit suffix.

    The other shape the port resolves, and the one a visit-stripping reading
    must leave alone: a key carrying no `@` is already a node id, so the same
    division has to be a no-op here while it is load-bearing on Petri.
    """
    return json.dumps(
        [
            {
                "run_id": _FALLBACK_RUN,
                "checkpoints": [{"checkpoint": {"node_outcomes": {_NODE: {"status": status}}}}],
            }
        ]
    )


def _price(*, model: str, multiplier: float) -> dict[str, Any]:
    """A complete per-model price table, so the declared chain resolves at all."""
    return {
        "model": model,
        "input_usd_per_million": 1.0 * multiplier,
        "output_usd_per_million": 2.0 * multiplier,
        "cache_write_usd_per_million": 0.5 * multiplier,
        "cache_read_usd_per_million": 0.1 * multiplier,
    }


def _configured_repo(*, tmp_path: Path) -> Path:
    """A dispatch target whose `implement` chain the supersede pass can resolve.

    The supersede pass compares each live warning against the repository's
    CURRENT primary, so a repository declaring no chain at all retires nothing —
    which is the right answer there and no answer at all here. Every other case
    in this module therefore uses a bare `tmp_path`, so nothing it mints can be
    retired by a configuration it never meant to exercise.
    """
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    block: dict[str, Any] = {
        "default_factory": _HP.name,
        "factories": {_HP.name: {"server": _HP.server}},
        "model_catalog": {
            f"zai/{model}": {"display_name": model, "pricing": _price(model=model, multiplier=1.0)}
            for model in ("glm-5.1", "glm-5.2")
        },
        "acp_nodes": {
            _NODE: {
                "agent": "glm-acp-agent",
                "model": "glm-5.2",
                "fallbacks": [{"agent": "glm-acp-agent", "model": "glm-5.1"}],
            }
        },
    }
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": block}}), encoding="utf-8"
    )
    return repo


def _resolved_generation(*, repo: Path) -> str:
    """This repository's CURRENT `implement` primary generation, read not transcribed.

    Computed through the production resolver so a configuration change that
    moved the digest makes the fallback-only control stop matching, rather than
    leaving it agreeing with a constant nobody rechecks.
    """
    # Imported lazily, exactly as the integration tier that reads this does:
    # `_dispatcher_acp_preflight` sits on a module-level cycle through
    # `_dispatcher_engine`, so it must not be the first `_dispatcher_*` module a
    # fresh interpreter imports.
    from livespec_orchestrator_beads_fabro.commands import (
        _dispatcher_acp_preflight as preflight,
    )

    return preflight.resolve_acp_primary_generations(repo=repo)[_NODE]


def _journal_at(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def _inputs(
    *, repo: Path, journal_path: Path, runner: _Runner, ledger: _Ledger | None = None
) -> ReconcileInputs:
    """A pass whose journal WRITER and journal READING are one file, as production's are.

    No HTTP transport is supplied, which is a claim rather than an omission: the
    routes a reconciliation pass sends are an orphan's own, and no case here
    produces one, so a transport double would be a seam nothing reaches.
    """
    return ReconcileInputs(
        repo=repo,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=[],
        journaled=journaled_runs(
            text=journal_path.read_text(encoding="utf-8"), source_path=journal_path
        ),
        runner=runner,
        journal=JournalFile(path=journal_path),
        ledger=_Ledger() if ledger is None else ledger,
    )


def _stages_written(*, journal_path: Path) -> list[str]:
    return [
        str(json.loads(line)["stage"])
        for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]


def _fact_ids(*, repo: Path, journal_path: Path) -> list[str]:
    return [
        item.id
        for item in model_fallback_warning_items(
            project_root=repo, repo="target", journal_path=journal_path
        )
    ]


def test_the_replay_mints_one_idempotent_warning_from_a_visit_qualified_outcome(
    tmp_path: Path,
) -> None:
    """The one node the run executed earns a warning, and a re-run appends none."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN),
        ),
    )
    runner = _Runner(inspect_by_run={_FALLBACK_RUN: _stages()})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP, _VPS])
    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP, _VPS])

    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == [_FACT_ID]
    assert _stages_written(journal_path=journal_path).count(_WARNING_STAGE) == 1
    assert [call[1] for call in runner.calls].count("inspect") == 2


def test_unreadable_outcomes_are_recorded_unavailable_and_leave_the_warning_standing(
    tmp_path: Path,
) -> None:
    """A read nobody could take retires nothing, and the next pass asks again."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _standing_warning(),
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN),
        ),
    )
    runner = _Runner()
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])
    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    written = _stages_written(journal_path=journal_path)
    assert written.count(_UNAVAILABLE_STAGE) == 2
    assert written.count(_WARNING_STAGE) == 1
    assert [call[1] for call in runner.calls].count("inspect") == 2
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == [_FACT_ID]


def test_a_later_primary_run_that_succeeded_clears_the_warning(tmp_path: Path) -> None:
    """The clause's one clearance: same generation, started after, succeeded."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _standing_warning(),
            _selection(at=_AFTER_WARNING, dispatch_id="dispatch-2", index=0),
            _run_stamp(dispatch_id="dispatch-2", run_id=_PRIMARY_RUN, at=_AFTER_WARNING),
        ),
    )
    runner = _Runner(inspect_by_run={_PRIMARY_RUN: _stages()})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert _stages_written(journal_path=journal_path).count(_CLEARED_STAGE) == 1
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == []


def test_a_primary_run_that_began_before_the_warning_does_not_clear_it(tmp_path: Path) -> None:
    """An older concurrent attempt is evidence about a moment already past."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _standing_warning(),
            _selection(at=_BEFORE_WARNING, dispatch_id="dispatch-0", index=0),
            _run_stamp(dispatch_id="dispatch-0", run_id=_PRIMARY_RUN, at=_BEFORE_WARNING),
        ),
    )
    runner = _Runner(inspect_by_run={_PRIMARY_RUN: _stages()})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert _CLEARED_STAGE not in _stages_written(journal_path=journal_path)
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == [_FACT_ID]


def test_a_primary_run_that_did_not_succeed_does_not_clear_the_warning(tmp_path: Path) -> None:
    """A primary that fell over is the reason the warning exists."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _standing_warning(),
            _selection(at=_AFTER_WARNING, dispatch_id="dispatch-2", index=0),
            _run_stamp(dispatch_id="dispatch-2", run_id=_PRIMARY_RUN, at=_AFTER_WARNING),
        ),
    )
    runner = _Runner(inspect_by_run={_PRIMARY_RUN: _stages(state="failed")})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert _CLEARED_STAGE not in _stages_written(journal_path=journal_path)
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == [_FACT_ID]


def test_a_stamp_naming_another_factory_is_not_replayed_through_this_one(tmp_path: Path) -> None:
    """A replay that addressed every factory would read one run on all of them."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN, factory=_VPS),
        ),
    )
    runner = _Runner(inspect_by_run={_FALLBACK_RUN: _stages()})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert "inspect" not in [call[1] for call in runner.calls]
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == []


def test_a_pinned_engine_outcome_map_mints_the_same_warning(tmp_path: Path) -> None:
    """The visit division is a no-op on a key that carries no visit."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN),
        ),
    )
    runner = _Runner(inspect_by_run={_FALLBACK_RUN: _checkpoint_outcomes()})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == [_FACT_ID]


def test_a_stamp_missing_its_dispatch_identity_is_not_replayed(tmp_path: Path) -> None:
    """A run nothing joins to a selection cannot be evidence about one."""
    stamp = _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN)
    del stamp["dispatch_id"]
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(_selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1), stamp),
    )
    runner = _Runner(inspect_by_run={_FALLBACK_RUN: _stages()})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert "inspect" not in [call[1] for call in runner.calls]
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == []


def test_a_targeted_pass_replays_only_the_item_it_names(tmp_path: Path) -> None:
    """A lifecycle-write hook narrows the pass, and the replay is narrowed with it."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN),
        ),
    )
    runner = _Runner(inspect_by_run={_FALLBACK_RUN: _stages()})
    base = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)
    inputs = replace(base, only_work_item_id="bd-ib-elsewhere")

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert "inspect" not in [call[1] for call in runner.calls]
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == []


def test_a_dry_run_replays_nothing_and_writes_nothing(tmp_path: Path) -> None:
    """A pass asked only to report must not append a warning it would have minted."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN),
        ),
    )
    runner = _Runner(inspect_by_run={_FALLBACK_RUN: _stages()})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP], dry_run=True)

    assert "inspect" not in [call[1] for call in runner.calls]
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == []


def test_an_empty_journal_replays_nothing(tmp_path: Path) -> None:
    """A pass with no recorded history reads no run and names no selection.

    The container lane of the same pass still journals its own sweep, so the
    claim is about the stages this replay owns rather than about an empty file:
    an emptiness assertion would red on a sibling lane's record and say nothing
    about this one.
    """
    journal_path = _journal_at(tmp_path=tmp_path, records=())
    runner = _Runner()
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    written = _stages_written(journal_path=journal_path)
    assert "inspect" not in [call[1] for call in runner.calls]
    assert [stage for stage in written if stage.startswith("acp-")] == []
    assert _UNAVAILABLE_STAGE not in written


def test_an_unreadable_inspect_payload_is_unavailable_rather_than_an_empty_run(
    tmp_path: Path,
) -> None:
    """A payload carrying no run record is a read that could not be taken.

    The other half of the unavailable arm, and the one a non-zero exit cannot
    reach: the engine ANSWERED, so an implementation keyed on the exit code
    alone reads the empty payload as a run that executed no node and mints
    nothing -- silently, and for exactly as long as the factory keeps answering.
    """
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN),
        ),
    )
    runner = _Runner(inspect_by_run={_FALLBACK_RUN: "[]"})
    inputs = _inputs(repo=tmp_path, journal_path=journal_path, runner=runner)

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    written = _stages_written(journal_path=journal_path)
    assert written.count(_UNAVAILABLE_STAGE) == 1
    assert _WARNING_STAGE not in written
    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == []


def test_the_replay_writes_the_journal_and_never_the_work_item_ledger(tmp_path: Path) -> None:
    """The lane's one output is a journal append; a work-item is a human's."""
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _selection(at=_WARNED_AT, dispatch_id="dispatch-1", index=1),
            _run_stamp(dispatch_id="dispatch-1", run_id=_FALLBACK_RUN),
        ),
    )
    ledger = _Ledger()
    inputs = _inputs(
        repo=tmp_path,
        journal_path=journal_path,
        runner=_Runner(inspect_by_run={_FALLBACK_RUN: _stages()}),
        ledger=ledger,
    )

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert _fact_ids(repo=tmp_path, journal_path=journal_path) == [_FACT_ID]
    assert ledger.verbs == []


def test_the_ledger_fake_records_a_write() -> None:
    """The control for the claim above: an inert fake would satisfy it too."""
    ledger = _Ledger()

    ledger.add_comment(issue_id=_ITEM, body="a write the reconciler must not make")

    assert ledger.list_comments(issue_id=_ITEM) == []
    assert ledger.verbs == [f"add_comment:{_ITEM}", f"list_comments:{_ITEM}"]


def test_a_replaced_primary_retires_its_warning_as_superseded(tmp_path: Path) -> None:
    """A warning about a primary nobody runs any more is a row nobody can act on."""
    repo = _configured_repo(tmp_path=tmp_path)
    journal_path = _journal_at(tmp_path=tmp_path, records=(_standing_warning(),))
    inputs = _inputs(repo=repo, journal_path=journal_path, runner=_Runner())

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert _stages_written(journal_path=journal_path).count(_SUPERSEDED_STAGE) == 1
    assert _fact_ids(repo=repo, journal_path=journal_path) == []


def test_a_fallback_only_edit_leaves_the_warning_standing(tmp_path: Path) -> None:
    """Only the full-chain digest moves, so the warning it was raised about stands."""
    repo = _configured_repo(tmp_path=tmp_path)
    journal_path = _journal_at(
        tmp_path=tmp_path,
        records=(
            _standing_warning(
                generation=_resolved_generation(repo=repo), full_chain="chain-before-the-edit"
            ),
        ),
    )
    inputs = _inputs(repo=repo, journal_path=journal_path, runner=_Runner())

    _ = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert _SUPERSEDED_STAGE not in _stages_written(journal_path=journal_path)
    assert _fact_ids(repo=repo, journal_path=journal_path) == [_FACT_ID]
