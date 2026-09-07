"""The apply phase's cut, filed HOST-SIDE by the seam that holds the credential.

`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration" ->
"Consensus-gated automated groom cut" requires the apply phase to file the
approved slices via the capture path with dependency edges linked, spec-change
slices routed rather than filed, and the original regroomed-out. It does NOT
say where that call executes, and a factory sandbox is deliberately given no
ledger credential — so an apply node that filed would reach for a secret it is
designed never to hold. Measured 2026-09-07 on run 01M1XNN6C8WHCW4EGDC7CWK6WW:
every node up to the filing succeeded and the filing died on the absent
credential wrapper with the ledger untouched.

WHAT IS MEASURED HERE IS THE LEDGER, never the return value alone. The whole
claim of this change is that the approved slices EXIST afterwards and the
original closed against them, so each case drives a real terminated-run account
through `record_groom_draft` — the same seam the propose phase's draft goes
through — and then reads the tenant back.

AND THE CREDENTIAL IS REMOVED FROM THE ENVIRONMENT FIRST, in the case that
matters most. `BEADS_DOLT_PASSWORD` is deleted before the filing runs, because
"the filing no longer needs a sandbox credential" is the assertion, and a test
that left the variable set would pass for a reason it never checked.

THE PROPOSE PATH IS ASSERTED UNCHANGED in its own case. Both phases publish
over one channel and the payload's leading marker is the only discriminator; if
that discrimination regressed toward "everything is a plan", a propose run's
draft would be filed as a cut, and if it regressed the other way an apply run's
plan would land as a fresh draft comment and revoke the approval it was
published under. Neither failure announces itself, so both directions are
covered.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PARK_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_groom_park"
_APPLY_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_groom_apply.py"
)
_PLAN_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_groom_filing_plan.py"
)

_ITEM_ID = "bd-ib-groom-apply"
_RUN_ID = "01M1APPLYRUN"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
# The sandbox clone's directory name IS the repo identity a slice's `repo=`
# field is matched against, so the fixture repo is named to match the plan.
_LOCAL_REPO = "repo"
_APPROVER = "thewoolleyman"
_ROUTE = "resolve-blocked ready valve plus the answer comment"
_FIRST_SLICE = "Move the filing host-side"
_SECOND_SLICE = "Refuse a plan the parser cannot reproduce"
_SPEC_SLICE = "Say so in the ratified clause"
_BEADS_PASSWORD_VAR = "BEADS_DOLT_PASSWORD"
# The two credentials the overlay DOES project, spelled as the fleet's other
# overlay cases spell them so the values are recognisably fixtures.
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"

# ONE LINE, in the draft's own grammar, because the channel the Dispatcher
# reads it off is a stderr LINE and a plan spanning several lines would arrive
# truncated to its first — silently, and having already been filed.
_PLAN = (
    f"livespec-groom-plan | approver={_APPROVER} | route={_ROUTE}"
    f" ;; slice={_FIRST_SLICE} | tier=factory | repo={_LOCAL_REPO}"
    " | acceptance=The Dispatcher files the cut. | blockers=none | spec=no"
    " | scope=Read the plan off the terminated run and file it."
    f" ;; slice={_SECOND_SLICE} | tier=factory | repo={_LOCAL_REPO}"
    " | acceptance=A malformed plan files nothing. | blockers="
    f"{_FIRST_SLICE} | spec=no | scope=Raise rather than guess."
    f" ;; slice={_SPEC_SLICE} | tier=human-gated | repo={_LOCAL_REPO}"
    " | acceptance=The clause names the seam. | blockers=none | spec=yes"
    " | scope=Route this one to propose-change."
)
_SENTINEL_LINE = f"LIVESPEC_NEEDS_HUMAN: {_PLAN}"
_DRAFT = "slice=A | layer=1 | tier=factory | repo=repo | acceptance=It lands. | blockers=none"
_DRAFT_SENTINEL_LINE = f"LIVESPEC_NEEDS_HUMAN: {_DRAFT}"


def _noop(**kwargs: object) -> None:
    """A stand-in for one post-run disposition this case is not measuring."""
    _ = kwargs


def _park_module() -> Any:
    """Import the seam under test, proving BOTH new modules exist first.

    The `is_file()` assertions come before the import deliberately: a bare
    top-level import of a module that does not exist yet dies at COLLECTION,
    which proves only unimportability rather than that the behaviour is
    unimplemented.
    """
    assert _APPLY_MODULE_PATH.is_file()
    assert _PLAN_MODULE_PATH.is_file()
    return importlib.import_module(_PARK_MODULE_NAME)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(frozen=True, kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(kw_only=True)
class _Runner:
    """A fake `fabro` CLI returning one canned `inspect` payload."""

    payload: str
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> _Command:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return _Command(exit_code=0, stdout=self.payload, stderr="")


@dataclass(frozen=True, kw_only=True)
class _Factory:
    server: str | None


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / _LOCAL_REPO
    target = repo / _GROOM_DIR
    target.mkdir(parents=True)
    _ = (target / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n',
        encoding="utf-8",
    )
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"workflows": {_GROOM_VARIANT: _GROOM_DIR}},
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _filed(*, status: str = "active") -> WorkItem:
    """The regroom target as an apply dispatch finds it: `active`, groom-pinned."""
    reset_fake_singleton()
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="An epic under an apply dispatch",
        description="Its cut was drafted and a human approved it.",
        origin="freeform",
        gap_id=None,
        rank="m",
        assignee="dispatcher",
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=_config(), item=item)
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=_GROOM_VARIANT)
    return item


def _args() -> argparse.Namespace:
    return argparse.Namespace(fabro_bin="fabro", fabro_factory_target=_Factory(server=_SERVER))


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="the run terminated carrying its filing plan",
        fabro_run_id=_RUN_ID,
    )


def _inspect_payload(*, line: str) -> str:
    return json.dumps({"run": {"id": _RUN_ID, "stderr": line}})


def _tenant() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _drive(
    *,
    tmp_path: Path,
    line: str,
    journal: _RecordingJournal,
    monkeypatch: pytest.MonkeyPatch,
    status: str = "active",
) -> object:
    """Run one terminated-run account through the seam with NO beads credential.

    The variable is deleted for every case, not only the happy one: a refusal
    path that reached for the credential would be the same defect wearing a
    different outcome.
    """
    monkeypatch.delenv(_BEADS_PASSWORD_VAR, raising=False)
    module = _park_module()
    return module.record_groom_draft(
        args=_args(),
        repo=_repo(tmp_path=tmp_path),
        item=_filed(status=status),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload=_inspect_payload(line=line)),
    )


def test_the_approved_cut_is_filed_with_no_beads_credential_in_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two factory slices EXIST in the tenant afterwards; the spec slice does not."""
    journal = _RecordingJournal()

    filed = _drive(tmp_path=tmp_path, line=_SENTINEL_LINE, journal=journal, monkeypatch=monkeypatch)

    titles = {item.title for item in _tenant().values()}
    assert _FIRST_SLICE in titles
    assert _SECOND_SLICE in titles
    assert _SPEC_SLICE not in titles
    assert filed is True
    stages = [row["stage"] for row in journal.records]
    assert stages == ["groom-cut-filed"]
    assert journal.records[0]["spec_change_slices"] == [_SPEC_SLICE]


def test_the_regroom_target_closes_against_the_slice_ids_that_were_filed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closed only AFTER the slices exist, and named against them.

    The reason string naming every filed id is what makes the ordering
    observable from the ledger alone: an original closed against ids that were
    never minted could not carry them.
    """
    journal = _RecordingJournal()

    _ = _drive(tmp_path=tmp_path, line=_SENTINEL_LINE, journal=journal, monkeypatch=monkeypatch)

    tenant = _tenant()
    original = tenant[_ITEM_ID]
    filed_ids = [item.id for item in tenant.values() if item.title in (_FIRST_SLICE, _SECOND_SLICE)]
    assert original.status == "done"
    assert original.resolution == "no-longer-applicable"
    assert len(filed_ids) == 2
    for slice_id in filed_ids:
        assert slice_id in (original.reason or "")


def test_a_malformed_plan_files_nothing_and_journals_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan the parser cannot reproduce is refused with the ledger untouched.

    Refusing rather than repairing is the point: a plan missing a tier is a cut
    the reviewer approved in a shape this parser cannot rebuild, and filing a
    guessed-at version of it would file something no human ever saw.
    """
    journal = _RecordingJournal()
    malformed = (
        f"LIVESPEC_NEEDS_HUMAN: livespec-groom-plan | approver={_APPROVER} | route={_ROUTE}"
        f" ;; slice={_FIRST_SLICE} | repo={_LOCAL_REPO} | acceptance=It lands. | scope=Do it."
    )

    filed = _drive(tmp_path=tmp_path, line=malformed, journal=journal, monkeypatch=monkeypatch)

    assert filed is False
    assert set(_tenant()) == {_ITEM_ID}
    assert _tenant()[_ITEM_ID].status != "done"
    assert [row["stage"] for row in journal.records] == ["groom-cut-refused"]
    assert journal.records[0]["reason"] == "GroomDraftError"


def test_a_propose_phase_draft_is_still_recorded_as_a_comment_and_files_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discrimination, from the other side: a draft must never be filed."""
    journal = _RecordingJournal()

    filed = _drive(
        tmp_path=tmp_path, line=_DRAFT_SENTINEL_LINE, journal=journal, monkeypatch=monkeypatch
    )

    bodies = tuple(
        comment.text for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    )
    assert filed is False
    assert len(bodies) == 1
    assert _DRAFT in bodies[0]
    assert set(_tenant()) == {_ITEM_ID}


def test_no_beads_credential_is_projected_into_the_factory_sandbox_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The posture the host-side filing exists to preserve, asserted at the overlay.

    The credential is SET in the dispatching process's own environment here, so
    the assertion is that the overlay declines to forward one it can see —
    not merely that it cannot find one.
    """
    projected = "not-for-the-sandbox"
    monkeypatch.setenv(_BEADS_PASSWORD_VAR, projected)
    committed = (
        '_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n\n'
        '[run.environment]\nid = "livespec-ci"\n'
    )
    workflow_dir = tmp_path / _GROOM_DIR
    workflow_dir.mkdir(parents=True)

    overlay = render_run_config_overlay(
        committed_text=committed,
        workflow_dir=workflow_dir,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )

    assert overlay is not None
    assert _BEADS_PASSWORD_VAR not in overlay
    assert projected not in overlay


def test_a_target_already_at_backlog_is_filed_without_a_claim_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unclaimed target needs no release, and the cut still lands.

    The claim release exists only because an apply-dispatched item is `active`
    when this seam runs; a target that is already `backlog` — a re-run after a
    refused filing released it — must not be written to for no reason.
    """
    journal = _RecordingJournal()

    filed = _drive(
        tmp_path=tmp_path,
        line=_SENTINEL_LINE,
        journal=journal,
        monkeypatch=monkeypatch,
        status="backlog",
    )

    assert filed is True
    assert {item.title for item in _tenant().values()} >= {_FIRST_SLICE, _SECOND_SLICE}


def test_a_filed_cut_is_not_then_rested_at_blocked_needs_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The post-run sequence skips the escalation once the cut is filed.

    Escalating here would move a regroom target that has already CLOSED to
    `blocked`, undoing the terminal disposition the contract assigns the apply
    run — so the sequence is asserted, not just the seam that feeds it.
    """
    escalated: list[str] = []
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "record_groom_draft",
        lambda **_: True,
    )
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "escalate_needs_human_block",
        lambda **_: escalated.append("escalated"),
    )
    monkeypatch.setattr(_dispatcher_loop_selection, "preserve_checkpointed_work_reference", _noop)
    monkeypatch.setattr(_dispatcher_loop_selection, "bounce_non_convergence_to_backlog", _noop)
    monkeypatch.setattr(_dispatcher_loop_selection, "emit_calibration", _noop)
    monkeypatch.setattr(_dispatcher_loop_selection, "record_provider_exhaustion_if_observed", _noop)
    monkeypatch.setattr(
        _dispatcher_loop_selection, "record_dead_implementer_truncation_if_observed", _noop
    )

    _dispatcher_loop_selection.post_run_dispositions(
        args=_args(),
        repo=tmp_path,
        item=_filed(),
        outcome=_outcome(),
        journal=_RecordingJournal(),
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        token_supplier=lambda: _FAKE_TOKEN,
    )

    assert escalated == []
