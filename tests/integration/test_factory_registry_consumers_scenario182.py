"""Scenario 182 — every factory-address CONSUMER reads the one host registry.

`test_factory_registry_resolution_scenario182.py` beside this file binds the
RESOLUTION: that a registry-backed entry's address comes from the host registry,
reaches the launch argv and the ledger, and refuses before any claim when it
does not resolve. This file binds the other half of the same clause — the
sentence that says "Every surface that turns a declared factory into an address
MUST use this one resolution, and every surface whose behaviour depends on
whether a factory is remote MUST treat a registry-backed entry as naming a
server", together with the failure behaviour each of those surfaces owes.

WHY THESE SURFACES NEED CASES OF THEIR OWN AT ALL, given that the resolution is
shared. Because the shared resolution answers with `FactoryTarget.server` of
`None` for a registry it could not resolve — and `None` is the SAME value an
unconfigured repository carries, which every one of these surfaces already reads
as "this factory declares no server" and therefore as the AMBIENT LOCAL Fabro.
So the resolution being correct is not evidence that a consumer is: a consumer
that opened a port on that `None` would survey whichever engine the dispatching
host runs, answer cleanly, and report a factory as holding no runs on the
strength of a reading taken from the wrong machine. That is the wrong-population
trap this repository catalogues, arriving through a default rather than through a
typo, and the only place it is settled is at each consumer.

WHY THE UNREADABLE-BYTES CASE IS HERE RATHER THAN BESIDE THE RESOLUTION'S OWN
REFUSAL CASES. A registry file whose bytes are not valid UTF-8 is not a refusal
at all: `Path.read_text(encoding="utf-8")` raises `UnicodeDecodeError`, which is
a `ValueError` and not an `OSError`, so it escapes the reading entirely and
reaches every consumer as an exception. Measured on the pre-fix build: the
per-factory survey, the plan liveness read, the merge-hold guard and the
telemetry classification each died with a traceback, and the needs-human valve
lane — whose absorbed-error set is `OSError` and the beads family — lost the
whole valve list rather than one item's enrichment. The clause's own words for
this are "rather than raising", so it belongs with the consumers it raises
through.

WHY EACH CASE ASSERTS A NEGATIVE BESIDE ITS VERDICT. An unobservable verdict is
reachable two ways: by refusing to address a factory that did not resolve, and
by addressing the wrong engine and being told nothing useful. The two are
indistinguishable at the return value, and only one of them is correct — the
second has already contacted a machine this factory never named. So every
liveness case also asserts that no process was launched for that factory, which
is the only place that difference is observable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, record_claim_stamp
from livespec_orchestrator_beads_fabro.commands import _plan_run_liveness as plan_liveness
from livespec_orchestrator_beads_fabro.commands._acp_factory_hold_evidence import (
    LISTING_UNREADABLE,
    factory_hold_evidence,
)
from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import FactoryRunReader
from livespec_orchestrator_beads_fabro.commands._acp_projection_run import (
    resolve_projection_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_claim_lane import (
    reconcile_claim_lane,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs import reconcile_runs
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_factories import (
    reconcile_factory_targets,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_telemetry_export import (
    RUN_TURN_UNOBSERVABLE_REMOTE_FACTORY,
    factory_run_turn_observation,
    run_turn_telemetry_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import DOCKER_BIN
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_arm_guard import (
    ARM_REFUSAL_LIVE_RUN,
    arm_refusal_for_release,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_needs_human_question import (
    needs_human_question_summary,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orch-beads-fabro"
_PREFIX = "bd-ib"

# The registry-backed factory under test, and a committed-`server` sibling whose
# engine answers. The sibling is what makes "one unresolvable factory MUST NOT
# prevent the reconcile survey from observing the other declared factories" a
# claim with a control beside it rather than an absence nobody could falsify.
_FACTORY = "petri"
_LEGACY = "legacy"
_LEGACY_SERVER = "https://legacy.example:32276"
_REGISTRY_SERVER = "https://registry-override.example:32276"
_REGISTRY_DOCKER_HOST = "ssh://cwoolley@gmktec.example"
_REGISTRY_PATH_ENV_VAR = "LIVESPEC_FABRO_FACTORY_REGISTRY"
_FACTORY_SELECTION_ENV_VAR = "LIVESPEC_FABRO_FACTORY"

_PETRI_ITEM = "bd-ib-onpetri"
_LEGACY_ITEM = "bd-ib-onlegacy"
_PETRI_RUN = "01M5PETRIRUN"
_LEGACY_RUN = "01M5LEGACYRUN"
_HOST = "reconciling-host"
_NOW = "2026-10-19T00:00:00Z"

# The survey's own reason for a factory it holds no address for, spelled here
# rather than imported so this file keeps naming the record it means to read.
_ERROR_NO_SERVER_URL = "factory-server-url-missing"
_HOLD_FACTORY_UNOBSERVABLE = "factory-unobservable"
_HOLD_RUN_LIVE = "run-live"
_SWEEP_STAGE = "sandbox-container-sweep"


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch) -> object:
    """A fresh in-memory tenant, with neither routing variable inherited.

    Both deletions are load-bearing rather than hygiene, for the reason the
    resolution suite beside this one gives: `LIVESPEC_FABRO_FACTORY` overrides
    every selection these cases declare, and the registry path variable is how
    each one points the resolution at its own fixture file. A value leaking in
    from the dispatch that runs this suite would decide the cases instead of the
    configuration they write.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:factory-registry-consumers")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "fabro")
    monkeypatch.delenv(_FACTORY_SELECTION_ENV_VAR, raising=False)
    monkeypatch.delenv(_REGISTRY_PATH_ENV_VAR, raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """One fake CLI for every binary a pass reaches, recording each argv.

    Keyed on `argv[0]` before the verb, because `fabro ps` and `docker ps` are
    both `ps`: a fake that read the verb first would answer a factory inventory
    to a container listing.

    `ps_by_server` is keyed by the `--server` operand rather than answering one
    listing to every caller, which is what lets a case assert that a factory the
    registry could not resolve was never addressed at all — the one place the
    difference between refusing to address it and addressing the ambient local
    engine is observable.
    """

    ps_by_server: dict[str, str] = field(default_factory=dict)
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
        if argv[0] == DOCKER_BIN:
            return CommandResult(exit_code=0, stdout="", stderr="")
        return CommandResult(
            exit_code=0, stdout=self.ps_by_server.get(_server_of(argv=argv), "[]"), stderr=""
        )

    @property
    def servers_addressed(self) -> list[str]:
        """Every `--server` operand a `fabro` call carried, in order."""
        return [
            _server_of(argv=argv)
            for argv in self.calls
            if argv[0] != DOCKER_BIN and "--server" in argv
        ]

    @property
    def bare_fabro_calls(self) -> list[list[str]]:
        """Every `fabro` call that named NO server — the ambient local engine."""
        return [argv for argv in self.calls if argv[0] != DOCKER_BIN and "--server" not in argv]

    @property
    def docker_argv_heads(self) -> list[list[str]]:
        """Each docker call's binary, daemon address and verb, in order."""
        return [argv[:4] for argv in self.calls if argv[0] == DOCKER_BIN]


def _server_of(*, argv: list[str]) -> str:
    index = argv.index("--server") if "--server" in argv else -1
    return "" if index < 0 else argv[index + 1]


@dataclass(frozen=True, kw_only=True)
class _Completed:
    """One finished command in the shape the merge-hold valve's runner returns."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(kw_only=True)
class _ValveRunner:
    """The merge-hold valve's OWN runner shape — `(argv, cwd)` in, a run out.

    A separate recorder from `_Runner` rather than an adapter, because the valve
    hands its runner a tuple and no timeout while the Fabro port's seam takes
    keyword `cwd` and `timeout_seconds`: one object satisfying both would have to
    branch on which caller it was, which is the thing no fake should know.

    Every call answers an empty JSON list, which is a valid `fabro ps -a --json`
    listing and a valid `gh pr view` payload alike. That is deliberate: the claim
    these cases make is about WHICH engine the guard addressed and whether it
    addressed one at all, so an answer that settled the guard's later head
    comparison would decide a question this module is not asking.
    """

    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> _Completed:
        _ = cwd
        self.calls.append(argv)
        return _Completed(returncode=0, stdout="[]", stderr="")


def _journal(*, repo: Path) -> JournalFile:
    """The pass journal, on disk, because the claim lane reads it back.

    A real `JournalFile` rather than an in-memory double: the claim lane is
    handed the same writer it reads its own earlier rows through, so a write-only
    stand-in would exercise a lane that could never grade a repeated claim.
    """
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return JournalFile(path=path)


def _rows(*, journal: JournalFile, stage: str) -> list[dict[str, Any]]:
    """Every record of one stage, read back off the journal file.

    Unguarded on the file's existence on purpose: the one caller reads back a
    record the pass it just drove appended, so an absent file is that pass having
    written nothing — which must raise here rather than return the empty list a
    stage-filter miss also produces.
    """
    return [
        record
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line)).get("stage") == stage
    ]


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def _fake(*, repo: Path) -> FakeBeadsClient:
    client = make_beads_client(config=_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)
    return client


def _write_config(*, repo: Path, factories: dict[str, Any], default_factory: str) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_BLOCK: {
                    "connection": {"tenant": _TENANT, "prefix": _PREFIX, "fake": True},
                    "dispatcher": {"factories": factories, "default_factory": default_factory},
                }
            }
        ),
        encoding="utf-8",
    )


def _registry_repo(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: object,
    entry: dict[str, Any] | None = None,
    factories: dict[str, Any] | None = None,
    registry_bytes: bytes | None = None,
) -> Path:
    """A repo declaring `petri` as registry-backed, beside a registry file.

    `registry_bytes` writes the file as RAW BYTES, which is the only way to
    express a registry whose contents are not decodable text — the case whose
    whole point is that it never reaches the JSON reader at all.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    declared: dict[str, Any] = {"registry": True}
    declared.update(entry or {})
    table = {_FACTORY: declared}
    table.update(factories or {})
    _write_config(repo=repo, factories=table, default_factory=_FACTORY)
    path = repo / "fabro-factories.json"
    if registry_bytes is not None:
        _ = path.write_bytes(registry_bytes)
    else:
        _ = path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, str(path))
    return repo


def _unresolvable_repo(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factories: dict[str, Any] | None = None,
) -> Path:
    """`petri` registry-backed, beside a registry holding no entry for it."""
    return _registry_repo(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        registry={"someone-else": {"server": _LEGACY_SERVER}},
        factories=factories,
    )


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="feature",
        status="active",
        title=f"A dispatched slice claimed under {item_id}",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at=_NOW,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _claimed(
    *, repo: Path, item_id: str, run_id: str, factory: str, server: str | None
) -> WorkItem:
    """One `active` item holding a claim stamped to `factory`'s run."""
    item = _item(item_id=item_id)
    append_work_item(path=_config(repo=repo), item=item)
    record_claim_stamp(
        path=_config(repo=repo),
        work_item_id=item_id,
        stamp=ClaimStamp(
            dispatch_id=f"01DISPATCH{item_id}",
            dispatching_host=_HOST,
            run_id=run_id,
            factory_name=factory,
            factory_server=server,
        ),
    )
    return item


def _inputs(
    *,
    repo: Path,
    runner: _Runner,
    journal: JournalFile,
    items: tuple[WorkItem, ...],
    claim_lane_armed: bool,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=repo,
        fabro_bin="fabro",
        id_prefix=_PREFIX,
        items=items,
        journaled=journaled_runs(text=""),
        runner=runner,
        journal=journal,
        ledger=make_beads_client(config=_config(repo=repo)),
        blocked_run_grace_seconds=0,
        claim_host=_HOST,
        claim_journal=journal if claim_lane_armed else None,
        # The lane is INJECTED, exactly as the two reconciliation surfaces inject
        # it: the run lane cannot import it without closing a runtime cycle.
        claim_lane=reconcile_claim_lane if claim_lane_armed else None,
    )


def _running_listing(*, run_id: str, item_id: str) -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "goal": f"Work-item: {item_id}\nRepo: /tmp/repo",
                "status": {"kind": "running"},
            }
        ]
    )


def _survey(
    *,
    repo: Path,
    runner: _Runner,
    journal: JournalFile,
    items: tuple[WorkItem, ...] = (),
    claim_lane_armed: bool = False,
) -> Any:
    """One reconcile pass over every DECLARED factory, resolved from the config.

    The factories come from `reconcile_factory_targets` rather than being
    constructed, because the address a factory is surveyed through has to come
    from the same declaration the reconciler enumerates it by — and the whole
    question here is what that resolution yields for a registry-backed entry.
    """
    return reconcile_runs(
        inputs=_inputs(
            repo=repo,
            runner=runner,
            journal=journal,
            items=items,
            claim_lane_armed=claim_lane_armed,
        ),
        factories=reconcile_factory_targets(repo=repo),
    )


def test_the_reconcile_survey_reports_an_unresolvable_registry_backed_factory_and_still_observes_the_others(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 182's reconcile-survey case, with the sibling factory as control.

    THREE CLAIMS, and the third is what the other two are worth nothing without.
    The survey has to report `petri` as unobservable AND name it — a reason with
    no factory on it sends an operator to read every declared entry — and it must
    not report it as holding no runs, which is the reading that let a factory
    nobody reached pass as a clean one. But a survey that reported `petri` and
    then stopped would satisfy both while silently abandoning the inventory this
    pass exists to take, so `legacy`'s own run is asserted in the same pass.

    The ADDRESSES are asserted beside the verdicts because they are the only
    place the fail-open is visible: a survey that addressed the ambient local
    engine for `petri` would have contacted a machine that factory never named,
    and its error row would read exactly like this one.
    """
    repo = _unresolvable_repo(
        tmp_path=tmp_path, monkeypatch=monkeypatch, factories={_LEGACY: {"server": _LEGACY_SERVER}}
    )
    legacy = _claimed(
        repo=repo,
        item_id=_LEGACY_ITEM,
        run_id=_LEGACY_RUN,
        factory=_LEGACY,
        server=_LEGACY_SERVER,
    )
    runner = _Runner(
        ps_by_server={_LEGACY_SERVER: _running_listing(run_id=_LEGACY_RUN, item_id=_LEGACY_ITEM)}
    )
    journal = _journal(repo=repo)

    summary = _survey(
        repo=repo, runner=runner, journal=journal, items=(legacy,), claim_lane_armed=True
    )

    assert [(error.factory_name, error.reason) for error in summary.errors] == [
        (_FACTORY, _ERROR_NO_SERVER_URL)
    ]
    # `legacy` answered, and the run it holds is reported — the survey was not
    # abandoned by the factory it could not resolve.
    assert [(held.factory_name, held.run_id, held.hold_reason) for held in summary.held_claims] == [
        (_LEGACY, _LEGACY_RUN, _HOLD_RUN_LIVE)
    ]
    # Exactly one engine was addressed, and it was the one that declared an
    # address. No bare call: the unresolvable factory was never surveyed through
    # whichever Fabro this host happens to run.
    assert runner.servers_addressed == [_LEGACY_SERVER]
    assert runner.bare_fabro_calls == []


def test_a_journal_liveness_read_of_an_unresolvable_registry_backed_factory_is_unobservable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 182's journal-liveness case: held, naming the factory, not gone.

    The claim's own stamp is the journal row that names `petri` as its run's
    factory, so this is the liveness question the clause asks "of each factory a
    journal names". The hold reason and the item's surviving status are asserted
    together because either alone passes while the other fails in the expensive
    direction: a hold with the wrong reason sends an operator to the wrong remedy,
    and a released item has had its run treated as gone — which re-dispatches
    work a live run may still be doing on a machine nobody could read.
    """
    repo = _unresolvable_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    petri = _claimed(
        repo=repo, item_id=_PETRI_ITEM, run_id=_PETRI_RUN, factory=_FACTORY, server=None
    )
    runner = _Runner()
    journal = _journal(repo=repo)

    summary = _survey(
        repo=repo, runner=runner, journal=journal, items=(petri,), claim_lane_armed=True
    )

    assert [(held.factory_name, held.run_id, held.hold_reason) for held in summary.held_claims] == [
        (_FACTORY, _PETRI_RUN, _HOLD_FACTORY_UNOBSERVABLE)
    ]
    assert summary.recovered_claims == ()
    # The run was not treated as gone: the claim stands exactly as it was found.
    held_item = next(iter(read_work_items(path=_config(repo=repo))))
    assert (held_item.status, held_item.assignee) == ("active", "fabro")
    assert runner.bare_fabro_calls == []


def test_plan_run_liveness_reports_an_unresolvable_registry_backed_factory_as_unobservable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan pointer's liveness gauge refuses to answer for a factory it cannot address.

    `not-live` is the one verdict this gauge may not reach here, because it is
    the verdict that authorizes a SECOND dispatch against a target that may
    already be driven by a live run. The module's own docstring says so: every
    arm that could not MEASURE answers `unobservable` and names what failed.

    The launched-process assertion is what separates the right unobservable from
    the wrong one. A gauge that opened a port on the unresolved `None` would ask
    the ambient local engine about a run that lives elsewhere, and the clean
    not-found it gets back is exactly how a confident wrong answer is produced.
    """
    repo = _unresolvable_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.chdir(repo)
    client = _fake(repo=repo)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_PETRI_ITEM,
            issue_type="task",
            title="A plan target stamped to a registry-backed factory",
            description="Factory target.",
            assignee=None,
            created_at=_NOW,
        )
    )
    client.update_issue(
        issue_id=_PETRI_ITEM,
        metadata={
            "dispatch_fabro_run_id": _PETRI_RUN,
            "dispatch_factory": {"name": _FACTORY, "server": None},
        },
    )
    runner = _Runner()
    monkeypatch.setattr(plan_liveness, "ShellCommandRunner", lambda: runner)

    seen = plan_liveness.observe_target_run(
        config=_config(repo=repo),
        epic_id="bd-ib-plan",
        action=NextAction(kind="impl", ref=_PETRI_ITEM, text="Dispatch it."),
    )

    assert seen.verdict == plan_liveness.LIVENESS_UNOBSERVABLE
    assert seen.run_id is None
    assert _FACTORY in seen.detail
    assert runner.calls == []


def test_the_merge_hold_arm_guard_refuses_on_an_unresolvable_registry_backed_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A release may not arm while the configured factory's inventory is unread.

    The guard's whole posture is that every arm that cannot measure refuses, and
    an unresolvable registry is the one shape of that which answers with an empty
    run set rather than with an error: `fabro ps` against the ambient local
    engine exits zero and lists nothing, so the guard would read "no run of this
    item is live", arm the pull request, and let the forge merge a head a live
    run on another machine is about to rewrite.

    The refusal CODE is asserted rather than only its presence, because the two
    codes name different remedies — a live run is waited out, an unproved head
    is re-proved — and this refusal belongs to the liveness measurement.

    THE CONTROL IS THE SAME GUARD OVER A FACTORY THAT DECLARES AN ADDRESS, and
    it is what makes the refusal evidence about the registry. A guard that had
    simply stopped asking anything would satisfy the refusal and the
    nothing-was-launched assertion together, and would refuse every release this
    fleet ever makes; the control asserts the engine IS addressed, at the
    sibling's own server, when the configuration gives the guard an address to
    use.
    """
    repo = _unresolvable_repo(
        tmp_path=tmp_path, monkeypatch=monkeypatch, factories={_LEGACY: {"server": _LEGACY_SERVER}}
    )
    runner = _ValveRunner()

    refusal = arm_refusal_for_release(
        repo=repo,
        work_item_id=_PETRI_ITEM,
        pr_number=4242,
        pr_head="c" * 40,
        runner=runner,
    )

    assert refusal is not None
    assert refusal.error == ARM_REFUSAL_LIVE_RUN
    assert "did not answer" in refusal.message
    assert _FACTORY in refusal.message
    # Nothing was launched: the guard refused on the address it never had, not on
    # an empty listing some other engine returned.
    assert runner.calls == []

    _write_config(
        repo=repo,
        factories={_FACTORY: {"registry": True}, _LEGACY: {"server": _LEGACY_SERVER}},
        default_factory=_LEGACY,
    )

    control = arm_refusal_for_release(
        repo=repo,
        work_item_id=_PETRI_ITEM,
        pr_number=4242,
        pr_head="c" * 40,
        runner=runner,
    )

    # The engine WAS addressed, at the sibling's own server, and the liveness
    # measurement therefore succeeded: whatever this release is refused for, it
    # is no longer the unread inventory above.
    assert runner.calls[0][:4] == ("fabro", "ps", "-a", "--json")
    assert _LEGACY_SERVER in runner.calls[0]
    assert control is None or control.error != ARM_REFUSAL_LIVE_RUN


def test_the_run_event_projection_treats_an_unresolvable_registry_backed_factory_as_unread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The projection resolves no factory for an unresolvable registry-backed entry.

    `None` here is the projection's own word for an UNREAD stream, and what
    `project_run_events` does with it — record the projection-failure fact rather
    than fetch from whatever the client would have defaulted to — is already
    bound by `test_acp_projection_run.py`. What is unbound, and what this asserts,
    is that a registry-backed entry the registry cannot resolve reaches that arm
    at all instead of resolving to a target whose `server` is the ambient local
    engine's absent one.
    """
    repo = _unresolvable_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert resolve_projection_factory(repo=repo, work_item_id=_PETRI_ITEM) is None


def test_a_registry_whose_bytes_are_not_text_is_unobservable_rather_than_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registry file that does not decode is a reading, never an exception.

    `Path.read_text(encoding="utf-8")` raises `UnicodeDecodeError`, which is a
    `ValueError` and so escapes the registry reading's `OSError` arm entirely.
    Every consumer of the shared resolution therefore saw it as a traceback
    rather than as an unresolvable factory — including the needs-human valve lane,
    whose absorbed set is `OSError` and the beads family, so one undecodable byte
    in host state cost the whole valve list rather than one item's enrichment.

    Driven through the SURVEY rather than through the reading, because the reading
    returning a detail proves only that it no longer raises: the claim is that the
    pass completes and reports the factory, which is what a caller depends on.
    """
    repo = _registry_repo(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        registry=None,
        registry_bytes=b'{"petri": {"server": "https://a.example\xff"}}',
        factories={_LEGACY: {"server": _LEGACY_SERVER}},
    )
    runner = _Runner(ps_by_server={_LEGACY_SERVER: "[]"})
    journal = _journal(repo=repo)

    summary = _survey(repo=repo, runner=runner, journal=journal)

    assert [(error.factory_name, error.reason) for error in summary.errors] == [
        (_FACTORY, _ERROR_NO_SERVER_URL)
    ]
    assert runner.servers_addressed == [_LEGACY_SERVER]


def test_an_availability_evidence_read_of_an_unresolvable_registry_backed_factory_is_unobservable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 182's availability-evidence case, through the production reader.

    Both halves of "not read as an available or exhausted provider" are asserted,
    because the two failures are opposite and each is silent. An EXHAUSTED
    reading would mint a hold from a factory nobody read, emptying a chain the
    evidence says nothing about; an AVAILABLE reading would let an unobserved
    candidate stand as confirmed unheld, which the clause forbids outright. The
    unobservable entry is what makes a candidate filter able to tell the
    difference, so it is asserted by factory NAME rather than by count.
    """
    repo = _unresolvable_repo(
        tmp_path=tmp_path, monkeypatch=monkeypatch, factories={_LEGACY: {"server": _LEGACY_SERVER}}
    )
    runner = _Runner(ps_by_server={_LEGACY_SERVER: "[]"})

    evidence = factory_hold_evidence(
        repo=repo,
        reader=FactoryRunReader(repo=repo, runner=runner),
        now_iso=_NOW,
    )

    assert [dict(entry) for entry in evidence.unobservable] == [
        {"factory": _FACTORY, "reason": LISTING_UNREADABLE}
    ]
    assert (evidence.holds, evidence.successes) == ((), ())
    assert runner.bare_fabro_calls == []


def test_the_needs_human_valve_survives_an_unresolvable_registry_backed_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 182's needs-human case: the valve stands, the enrichment is lost.

    The clause's own words are that an unreadable config or an unreachable
    factory "costs the ENRICHMENT and never the valve", and the direction matters
    more than the text: a lane that vanished because a factory could not be
    addressed reads downstream as a decision that had already been made, so the
    human who was being asked is never asked again.

    The summary is asserted EQUAL to the default rather than merely containing
    it, because a partially-enriched summary — a run handle with no question, a
    factory name with no address — is the shape that reads as an answer while
    carrying none.
    """
    repo = _unresolvable_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal_path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    _ = journal_path.write_text(
        json.dumps({"work_item_id": _PETRI_ITEM, "run_id": _PETRI_RUN}) + "\n", encoding="utf-8"
    )
    default_summary = f"Resolve human-needed block for work-item {_PETRI_ITEM}"
    runner = _Runner()

    summary = needs_human_question_summary(
        project_root=repo,
        item_id=_PETRI_ITEM,
        default_summary=default_summary,
        runner=runner,
    )

    assert summary == default_summary
    assert runner.calls == []


def test_the_container_sweep_reads_a_registry_backed_factory_through_its_registry_docker_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 182's docker_host case, read off the argv the sweep actually ran.

    A return value cannot carry this claim: a sweep of the reconciling host's own
    daemon that happened to find nothing would report an identical empty
    inventory. The daemon address in the argv is the only place the question is
    settled, and it has to arrive as the GLOBAL `--host` option ahead of the verb
    because that is the one position the Docker CLI accepts it in.
    """
    repo = _registry_repo(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        registry={
            _FACTORY: {"server": _REGISTRY_SERVER, "docker_host": _REGISTRY_DOCKER_HOST},
        },
    )
    runner = _Runner(ps_by_server={_REGISTRY_SERVER: "[]"})
    journal = _journal(repo=repo)

    summary = _survey(repo=repo, runner=runner, journal=journal)

    assert summary.errors == ()
    assert [sweep.docker_host for sweep in summary.containers] == [_REGISTRY_DOCKER_HOST]
    assert runner.docker_argv_heads == [[DOCKER_BIN, "--host", _REGISTRY_DOCKER_HOST, "ps"]]


def test_a_registry_entry_with_no_docker_host_is_reported_unobserved_and_opens_no_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 182's no-docker_host case: unobserved, naming it, and no connection.

    The two assertions are not complements. A sweep reporting ZERO CONTAINERS is
    byte-identical at every field to one over a clean factory, which is precisely
    the reading that let twelve containers leak unremarked; and a sweep that
    inferred a daemon from the server url beside it would remove a container on
    the reconciling host on the strength of a status read from another machine.
    So the record has to carry the one claim the pass is entitled to — this
    host's inventory was not taken, and here is the key that would address it —
    and no daemon may be opened for it.
    """
    repo = _registry_repo(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        registry={_FACTORY: {"server": _REGISTRY_SERVER}},
    )
    runner = _Runner(ps_by_server={_REGISTRY_SERVER: "[]"})
    journal = _journal(repo=repo)

    summary = _survey(repo=repo, runner=runner, journal=journal)

    assert [(sweep.docker_host, sweep.factory_names) for sweep in summary.containers] == [
        (None, (_FACTORY,))
    ]
    detail = next(iter(summary.containers)).detail
    assert detail is not None
    assert _FACTORY in detail
    assert "docker_host" in detail
    assert runner.docker_argv_heads == []
    assert [row["factory_names"] for row in _rows(journal=journal, stage=_SWEEP_STAGE)] == [
        [_FACTORY]
    ]


def test_a_registry_backed_factory_is_classified_as_remote_for_run_turn_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 182's telemetry case: registry-backed means remote, like a server.

    The resolution is a DECLARATION question here and deliberately not a
    filesystem one: "every surface whose behaviour depends on whether a factory
    is remote MUST treat a registry-backed entry as naming a server", and a
    registry-backed entry names another machine whether or not this host can
    currently resolve which one. Reading it as local is the fail-open: the guard
    would assert that THIS host's `run_turn` sink should carry the factory's
    spans, and then report a genuinely healthy remote pipeline as an absence.

    A committed-`server` sibling is assessed in the same case, because the clause
    says "exactly as it classifies an entry carrying a server value" — a case
    asserting only the registry-backed answer could pass against a build that had
    simply started calling every factory remote.
    """
    repo = _registry_repo(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        registry={_FACTORY: {"server": _REGISTRY_SERVER}},
        factories={_LEGACY: {"server": _LEGACY_SERVER}, "ambient": {}},
    )
    block = run_turn_telemetry_block(repo=repo)

    assert factory_run_turn_observation(block=block, factory=_FACTORY) == (
        RUN_TURN_UNOBSERVABLE_REMOTE_FACTORY
    )
    assert factory_run_turn_observation(block=block, factory=_LEGACY) == (
        RUN_TURN_UNOBSERVABLE_REMOTE_FACTORY
    )
    # The implicit single-factory target runs the sandbox on THIS machine, so it
    # stays observable: the registry key widens the remote reading, it does not
    # make every factory remote.
    assert factory_run_turn_observation(block=block, factory="ambient") is None
