"""The PRE-CLAIM Codex credential freshness gate (`bd-ib-tyqklx`).

`SPECIFICATION/scenarios.md` Scenario 19 requires the Dispatcher to refuse a
dispatch whose covered credential cannot outlive the run budget, and to surface
that the host credential needs renewal rather than projecting one that may
expire mid-run. The `credential-freshness-redesign` plan adds the POSITION that
refusal has to land in: before the selected item is claimed.

WHY THE POSITION IS THE WHOLE POINT. The decision used to run inside
`materialize_overlay`, which `dispatch_one` reaches only AFTER
`admit_and_select` has moved the item `ready -> active` and set its assignee. A
refusal there leaves an `active` row nobody is working, which is the stranded
shape the plan's own definition of done rules out. These tests therefore assert
on the ORDER of observable interactions -- what the gate did against what the
claim-and-launch surface recorded -- not merely on the exit code, because an
implementation that refused one step too late would produce the identical code.

THE REFUSAL TEXT IS ASSERTED HERE TOO, at the gate rather than at the
projection, for the reason the gate's own refusal spells out: an expiry that did
not advance and a renewal request that was never answered are not equivalent
evidence, and only one of them says anything at all about the credential.
Collapsing them is what turned an absent observation into a false demand for a
human `codex login` on 2026-10-05.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_codex_credential_gate,
    _dispatcher_dispatch_tail,
    _dispatcher_loop_command,
    _dispatcher_run_commands,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import Admission
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = 1_000_000

# The remaining lifetime measured on the host when a dispatch was refused at
# stage run-config-overlay on 2026-10-04 — below the floor, inside the refresh
# guard, so the bounded renewal is eligible.
_BELOW_FLOOR_REMAINING = 13_517

# The lifetime the dispatch freshness gate requires: run budget plus margin.
_REQUIRED_REMAINING = 18_000

# The resolved requirement these cases hand the gate. The gate no longer derives
# the figure itself -- its caller resolves it from the selected workflow and
# passes it in -- so a case exercising the gate has to supply one, and supplying
# it HERE keeps `_REQUIRED_REMAINING` above as the single place the floor these
# cases are positioned against is written down. `detail` is deliberately a plain
# marker rather than a copy of the production sentence: no assertion in this
# module reads it, and a transcribed copy would quietly rot against the real one.
_REQUIREMENT = CredentialLifetimeRequirement(
    allowance_seconds=_REQUIRED_REMAINING - CODEX_FRESHNESS_MARGIN_SECONDS,
    margin_seconds=CODEX_FRESHNESS_MARGIN_SECONDS,
    detail="test-resolved requirement",
)

# The renewal request is bounded at two minutes, so the clock can move by that
# much between the pre-request reading and the post-request grading.
_RENEWAL_ELAPSED = 120

# The host's own refresh token. It must never reach a journal record, which is
# what the projection's inert sentinel exists to guarantee one layer down.
_HOST_REFRESH_TOKEN = "host-refresh-token"

_GATE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_credential_gate"
_GATE_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_credential_gate.py"
)

# The ONE pre-dispatch wall both dispatch paths run. It was two byte-identical
# private functions, one per command module, until the credential gate became
# the fourth refusal in each and pushed the single-dispatch module past its file
# LLOC ceiling; the duplicate is what made "both paths refuse" a claim about two
# independently drifting sequences rather than about one.
_WALL_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall"
_WALL_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_pre_dispatch_wall.py"
)

_ANSWERED_DETAIL = "the renewal request was answered by the host Codex app-server"
_UNANSWERED_DETAIL = "codex app-server could not be started: codex"


def _auth_json_with_exp(*, exp: int) -> str:
    """Build a host Codex `auth.json` whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": _HOST_REFRESH_TOKEN,
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


class _StubOutcome:
    """A stand-in `CodexRenewalOutcome` carrying the two fields diagnostics read."""

    def __init__(self, *, answered: bool, detail: str) -> None:
        self.answered = answered
        self.detail = detail


class _RecordingJournal:
    """A journal that keeps what was appended instead of serializing it."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, *, record: dict[str, Any]) -> None:
        self.records.append(record)


def _stub_renewal(
    *,
    monkeypatch: pytest.MonkeyPatch,
    answered: bool,
    detail: str,
) -> list[str]:
    """Stand the bounded renewal in, recording every time it is spent.

    The hermetic tier must never spawn a real `codex app-server`, and the SPEND
    COUNT is an assertion in its own right: the gate is the one surface allowed
    to request a renewal, so a second request anywhere downstream would show up
    here as a second entry.
    """
    spent: list[str] = []

    def renew() -> _StubOutcome:
        spent.append("requested")
        return _StubOutcome(answered=answered, detail=detail)

    monkeypatch.setattr(_dispatcher_codex_auth, "renew_host_codex_credential", renew, raising=False)
    return spent


def test_the_gate_separates_an_unanswered_renewal_from_an_answered_unchanged_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two refusals over one credential, distinguished, neither an auth verdict.

    The discriminator is run in BOTH directions over the SAME stale credential,
    because a refusal that named the renewal observation in only one arm -- or
    that named it in neither -- would still refuse the dispatch and still look
    correct from the exit code.
    """
    assert _GATE_MODULE_PATH.is_file()
    gate = importlib.import_module(_GATE_MODULE)
    stale = _auth_json_with_exp(exp=_NOW - 10)
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: stale)

    answered_spend = _stub_renewal(monkeypatch=monkeypatch, answered=True, detail=_ANSWERED_DETAIL)
    answered = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx",),
        clock=lambda: _NOW,
        requirement=_REQUIREMENT,
    )
    unanswered_spend = _stub_renewal(
        monkeypatch=monkeypatch, answered=False, detail=_UNANSWERED_DETAIL
    )
    unanswered = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx",),
        clock=lambda: _NOW,
        requirement=_REQUIREMENT,
    )

    # Each arm refused, and each spent exactly ONE bounded renewal request.
    assert answered is not None
    assert unanswered is not None
    assert answered_spend == ["requested"]
    assert unanswered_spend == ["requested"]
    # Codex ANSWERED and the expiry held: reported as such, and the "no response
    # came back" note is absent, because here one did.
    assert _ANSWERED_DETAIL in answered
    assert "no successful renewal response was received" not in answered
    # No successful response came back: said so, and said that it is therefore
    # no evidence about this credential at all.
    assert _UNANSWERED_DETAIL in unanswered
    assert "no successful renewal response was received" in unanswered
    assert "no evidence about this credential" in unanswered
    # NEITHER observation is reported as an authentication failure, and neither
    # sends an operator to `codex login` off a non-advancing expiry.
    for message in (answered, unanswered):
        assert "does NOT by itself establish an authentication failure" in message
        assert "cannot report an authentication failure" in message
        assert "only if Codex explicitly reports an unrecoverable authentication" in message
        assert _HOST_REFRESH_TOKEN not in message
    # The expiry genuinely held in BOTH arms here (one credential, read twice),
    # so the non-advancing wording is the truthful one for both. The arm it
    # must NOT be applied to is the advancing one below.
    for message in (answered, unanswered):
        assert "did not advance it" in message
        assert "expiry ADVANCED between the readings" not in message


def test_the_gate_reports_a_renewal_that_advanced_short_of_the_floor_as_an_advance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the GATE, an advance that missed the floor is not called a hold.

    The gate is the surface an operator actually meets, so the truthful wording
    has to survive the whole path from the credential read to the returned
    refusal -- not merely the renderer the test above it reaches directly.

    The DISCRIMINATOR against the test above: both refuse after one ANSWERED
    renewal with a lifetime under the same floor, so neither the return type nor
    the shortfall numbers separate them. Only the expiry INSTANT does, and here
    it moves from `_NOW + 900` to `_NOW + 17970` -- the capture measured on
    2026-10-05, in which the refusal still reported no advance.

    And the wording must stop at that observation. The gate sees two readings of
    one expiry instant, so a refusal reaching through it is asserted here to
    name neither the request as the cause of the change nor a token issuance as
    its product -- both unobservable on this route, and both claimed by the
    first fix of this arm.
    """
    assert _GATE_MODULE_PATH.is_file()
    gate = importlib.import_module(_GATE_MODULE)
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 900),
            _auth_json_with_exp(exp=_NOW + 17_970),
        )
    )
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: next(reads))
    spend = _stub_renewal(monkeypatch=monkeypatch, answered=True, detail=_ANSWERED_DETAIL)

    clock = iter((_NOW, _NOW + _RENEWAL_ELAPSED))
    refusal = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx",),
        clock=lambda: next(clock),
        requirement=_REQUIREMENT,
    )

    assert refusal is not None
    # One bounded renewal; the advance did not buy a second attempt.
    assert spend == ["requested"]
    # The ADVANCE is reported and the non-advancing wording is gone.
    assert "expiry ADVANCED between the readings" in refusal
    assert "did not advance" not in refusal
    # Reported as an observation only: no cause, no issuance, no mint.
    assert "attributed neither to that request nor to any token issuance" in refusal
    assert "renewal request advanced" not in refusal
    assert "advanced its expiry" not in refusal
    assert "mint" not in refusal
    # The shortfall is still reported, against the post-request instant.
    assert str(17_970 - _RENEWAL_ELAPSED) in refusal
    assert str(_REQUIRED_REMAINING) in refusal
    # And the three guarantees the held-expiry arms carry hold here too.
    assert "does NOT by itself establish an authentication failure" in refusal
    assert "cannot report an authentication failure" in refusal
    assert _HOST_REFRESH_TOKEN not in refusal


def test_the_gate_journals_its_refusal_naming_the_unclaimed_items_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The durable record of a pre-claim refusal, carrying no credential material.

    A refusal before claim leaves no `active` row and no run, so the journal is
    the only place the pass survives in. It names the items it declined to claim
    -- the audit question a reader actually has -- and the credential it graded
    reaches it in NO form: not the access token, not the refresh token.
    """
    assert _GATE_MODULE_PATH.is_file()
    gate = importlib.import_module(_GATE_MODULE)
    stale = _auth_json_with_exp(exp=_NOW - 10)
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: stale)
    _ = _stub_renewal(monkeypatch=monkeypatch, answered=True, detail=_ANSWERED_DETAIL)
    journal = _RecordingJournal()

    refusal = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx", "bd-ib-zz6gii"),
        clock=lambda: _NOW,
        journal=journal,
        requirement=_REQUIREMENT,
    )

    assert refusal is not None
    assert len(journal.records) == 1
    record = journal.records[0]
    assert record["stage"] == gate.CODEX_CREDENTIAL_GATE_STAGE
    assert record["unclaimed_work_item_ids"] == ["bd-ib-tyqklx", "bd-ib-zz6gii"]
    serialized = json.dumps(record, sort_keys=True)
    assert _HOST_REFRESH_TOKEN not in serialized
    assert "header." not in serialized


def test_a_credential_above_the_floor_admits_on_the_dispatcher_own_clock() -> None:
    """The ordinary pass: no refusal, no renewal, nothing journaled.

    This arm reads the host credential through the gate's OWN clock rather than
    an injected one, which is the only way the production reading is exercised
    at all -- every other test here hands a clock in. The autouse
    `_hermetic_codex_home` fixture supplies a far-future `exp`, so the grade is
    taken against the real clock exactly as a dispatch takes it.
    """
    assert _GATE_MODULE_PATH.is_file()
    gate = importlib.import_module(_GATE_MODULE)
    journal = _RecordingJournal()

    admitted = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx",),
        journal=journal,
        requirement=_REQUIREMENT,
    )

    assert admitted is None
    # Nothing is recorded for an admitted pass: the overlay writes its own
    # projection record, and a second line asserting admission would duplicate
    # it while making every healthy dispatch noisier to read.
    assert journal.records == []


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="Refuse an unrenewable Codex credential before claim",
        description="Move the freshness decision ahead of admission.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _stub_credential_source(
    *,
    monkeypatch: pytest.MonkeyPatch,
    log: list[str],
    readings: tuple[str | None, ...],
) -> None:
    """Stand in the host credential, the renewal and the gate's own clock.

    Every stand-in appends to ONE log, which is what makes the ORDER of the
    renewal, the re-read and the second clock reading observable from outside.
    An end-state assertion cannot carry that claim: a build that re-read the
    credential AFTER claiming the item would reach the identical end state.
    """
    remaining = list(readings)

    def _read() -> str | None:
        log.append("read-credential")
        return remaining.pop(0)

    def _renew() -> _StubOutcome:
        log.append("renew")
        return _StubOutcome(answered=True, detail=_ANSWERED_DETAIL)

    instants = iter(range(_NOW, _NOW + 10 * _RENEWAL_ELAPSED, _RENEWAL_ELAPSED))

    def _clock() -> int:
        now = next(instants)
        log.append(f"clock:{now}")
        return now

    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", _read)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "renew_host_codex_credential", _renew, raising=False
    )
    monkeypatch.setattr(_dispatcher_codex_credential_gate, "wall_clock_epoch", _clock)


def _stub_wall_siblings(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize every wall refusal EXCEPT the credential gate under test.

    Reached through `importlib` rather than a module-top import so the first
    assertion of each case that needs it is a genuine check that the shared wall
    module exists, instead of a collection error that proves only
    unimportability.

    The siblings are stood in rather than exercised because each reaches the
    forge, the ledger or committed configuration for its own reasons, and any
    one of them answering first would shadow the gate this module is about.
    """
    wall = importlib.import_module(_WALL_MODULE)
    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "credential_wrapper_text", lambda **_kwargs: "")
    monkeypatch.setattr(wall, "reclaim_stale_publish_branches", lambda **_kwargs: None)


def _stub_loop(
    *,
    monkeypatch: pytest.MonkeyPatch,
    journal: _RecordingJournal,
    journal_path: Path,
    item: WorkItem,
    log: list[str],
    selected: list[WorkItem] | None = None,
) -> None:
    """Stub every drain seam AROUND the credential gate, leaving the gate live.

    `dispatch_loop_wave` is the ONE surface that claims and launches: it calls
    `admit_and_select` (ready -> active, assignee set) and then `dispatch_one`.
    Standing it in and logging its entry is therefore the measurement of "was
    the item claimed and was a run created", and it is a cheaper and more exact
    instrument than letting the real wave run against stubbed sub-seams.
    """
    module = _dispatcher_loop_command
    monkeypatch.setattr(module, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(module, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: ([item], journal))
    monkeypatch.setattr(module, "journal_path", lambda **_kwargs: journal_path)
    # `selected` is the SELECTION the drain would claim this pass. `None`
    # means the ordinary one-candidate wave; an empty list is the idle pass,
    # which is a distinct and much more common shape.
    picked = [item] if selected is None else selected
    monkeypatch.setattr(module, "candidates", lambda **_kwargs: picked)
    monkeypatch.setattr(
        module, "dispatch_loop_wave", lambda **_kwargs: log.append("claim-and-launch") or []
    )
    _stub_wall_siblings(monkeypatch=monkeypatch)


def _loop_args(*, repo: Path, journal_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal_path),
        items=None,
        budget=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
    )


def _dispatch_args(*, repo: Path, journal_path: Path, item_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal_path),
        item=item_id,
        as_json=False,
        skip_ledger_check=True,
        workflow_name=None,
    )


def test_an_idle_drain_touches_no_credential_and_reports_no_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pass with NOTHING to dispatch is a clean exit 0, and grades nothing.

    The drain reaches the pre-dispatch wall even when its selection is empty,
    and the gate answers a question about the credential a SELECTION will
    project -- so with no selection there is no question. Asking it anyway spent
    a bounded provider request on an idle pass and then refused it with a
    freshness failure, turning ordinary "no work" into exit 3.

    THE CREDENTIAL HERE IS DELIBERATELY ONE THE GATE WOULD REFUSE. That is what
    makes this a control rather than a restatement of the fixture: the autouse
    `_hermetic_codex_home` credential is far-future, so every pre-existing
    idle-loop test in this repository passed through the gate and could not have
    caught this. An instrument that cannot return a hit reports no hits.

    Its PAIR is `test_both_dispatch_paths_refuse_an_unrenewable_credential_
    before_claiming` below, over the same stale-credential shape with ONE
    candidate. Together they fix the gate's reach from both sides: a fix that
    short-circuited on an empty selection passes this case, and a fix that
    simply disabled the gate fails that one.

    `log` is the whole measurement. It stays empty of every credential
    interaction -- no read, no renewal, no clock reading -- because an idle pass
    must not be observable at the provider at all.
    """
    log: list[str] = []
    journal = _RecordingJournal()
    journal_path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    stale = _auth_json_with_exp(exp=_NOW - 10)
    _stub_credential_source(monkeypatch=monkeypatch, log=log, readings=(stale, stale))
    _stub_loop(
        monkeypatch=monkeypatch,
        journal=journal,
        journal_path=journal_path,
        item=_work_item(item_id="bd-ib-tyqklx"),
        log=log,
        selected=[],
    )

    code = _dispatcher_loop_command.run_loop_command(
        args=_loop_args(repo=tmp_path, journal_path=journal_path)
    )

    # An idle pass is healthy: nothing is broken and no item is at fault.
    assert code == 0
    # Not read, not renewed, not even clocked. The wave still runs, because it
    # owns the rework leg, which has nothing to do with the credential.
    assert log == ["claim-and-launch"]
    assert journal.records == []
    assert "C-mode dispatch refused" not in capsys.readouterr().err


def test_the_drain_rereads_and_regrades_a_renewal_before_anything_is_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The renewal, the re-read and the SECOND clock reading all precede the claim.

    The credential this drain reads back after renewing clears the floor by 60
    seconds at the PRE-request instant and misses it by 60 at the post-request
    instant. Grading it against the stale pre-request reading would credit it
    with up to two minutes of lifetime it no longer has and admit a dispatch
    whose credential is already below the floor — an error in the unsafe
    direction — so the correct answer here is a refusal, and the shortfall it
    reports is the discriminator between the two readings.

    "Before anything is claimed" is read off the wave never being entered, not
    off the exit code: a drain that claimed the item and then refused inside
    `materialize_overlay` exits with the same code and leaves the stranded
    `active` row this position exists to prevent.
    """
    assert _WALL_MODULE_PATH.is_file()
    log: list[str] = []
    journal = _RecordingJournal()
    journal_path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    item = _work_item(item_id="bd-ib-tyqklx")
    _stub_credential_source(
        monkeypatch=monkeypatch,
        log=log,
        readings=(
            _auth_json_with_exp(exp=_NOW + _BELOW_FLOOR_REMAINING),
            _auth_json_with_exp(exp=_NOW + _REQUIRED_REMAINING + 60),
        ),
    )
    _stub_loop(
        monkeypatch=monkeypatch,
        journal=journal,
        journal_path=journal_path,
        item=item,
        log=log,
    )

    code = _dispatcher_loop_command.run_loop_command(
        args=_loop_args(repo=tmp_path, journal_path=journal_path)
    )

    assert code == EXIT_PRECONDITION_ERROR
    # The whole sequence, in order, and the claim is not in it.
    assert log == [
        "read-credential",
        f"clock:{_NOW}",
        "renew",
        "read-credential",
        f"clock:{_NOW + _RENEWAL_ELAPSED}",
    ]
    assert "claim-and-launch" not in log
    # The shortfall is measured against the LATER instant, which is the only
    # reading at which this credential is short.
    refusal = journal.records[0]["refusal"]
    assert str(_REQUIRED_REMAINING + 60 - _RENEWAL_ELAPSED) in refusal
    assert journal.records[0]["unclaimed_work_item_ids"] == ["bd-ib-tyqklx"]
    # The drain reports it to the operator rather than refusing silently.
    assert "C-mode dispatch refused" in capsys.readouterr().err


def _stub_dispatch(
    *,
    monkeypatch: pytest.MonkeyPatch,
    journal: _RecordingJournal,
    journal_path: Path,
    item: WorkItem,
    log: list[str],
) -> None:
    """Stub every single-dispatch seam AROUND the credential gate.

    The two seams whose entry IS the claim and the run are logged rather than
    merely neutralized: `admit_and_select` is what moves the row `ready ->
    active` and sets its assignee, and `dispatch_one` is what creates the factory
    run. The post-verdict stages are stood in so that a build which does NOT
    refuse fails on the assertion below rather than erroring somewhere in the
    reporting tail, which would prove the wrong thing.
    """
    module = _dispatcher_run_commands
    monkeypatch.setattr(module, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(module, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: ([item], journal))
    monkeypatch.setattr(module, "ready_items", lambda **_kwargs: [item])
    _stub_wall_siblings(monkeypatch=monkeypatch)
    monkeypatch.setattr(
        module,
        "admit_and_select",
        lambda **_kwargs: log.append("claim")
        or Admission(admitted=[item], deferred=[], refused=[]),
    )
    monkeypatch.setattr(
        module,
        "args_with_dispatch_factory_target",
        lambda **kwargs: kwargs["args"],
    )
    monkeypatch.setattr(
        module,
        "args_with_dispatch_workflow_name",
        lambda **kwargs: kwargs["args"],
    )
    monkeypatch.setattr(
        module,
        "dispatch_one",
        lambda **_kwargs: log.append("launch")
        or DispatchOutcome(
            work_item_id=item.id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="stood in",
        ),
    )
    # The post-verdict stages live in the SHARED tail both single-dispatch paths
    # run, so they are stood in THERE rather than on the command module.
    tail = _dispatcher_dispatch_tail
    monkeypatch.setattr(tail, "journal_path", lambda **_kwargs: journal_path)
    monkeypatch.setattr(tail, "run_turn_sink_path", lambda **_kwargs: journal_path)
    monkeypatch.setattr(tail, "spans_path", lambda **_kwargs: journal_path)
    monkeypatch.setattr(tail, "emit_outcomes", lambda **_kwargs: None)
    monkeypatch.setattr(tail, "dispatch_exit_code", lambda **_kwargs: 0)
    monkeypatch.setattr(tail, "alarm_on_terminal_failure", lambda **_kwargs: None)
    monkeypatch.setattr(tail, "cost_gate_after_verdict", lambda **_kwargs: None)
    monkeypatch.setattr(tail, "self_update_after_verdict", lambda **_kwargs: None)
    monkeypatch.setattr(tail, "append_run_turn_checks", lambda **_kwargs: None)
    monkeypatch.setattr(tail, "reflect", lambda **_kwargs: None)
    monkeypatch.setattr(tail, "reflector_oob_after_verdict", lambda **_kwargs: None)


def test_both_dispatch_paths_refuse_an_unrenewable_credential_before_claiming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The single dispatch and the drain, over one credential, both refuse early.

    The credential is below the floor and the bounded renewal leaves it there,
    which is the only outcome at which a refusal is the right answer. Both paths
    are driven in ONE case because the Definition of Done's claim is about the
    PAIR: they reach the wall through separate call sites, and a gate wired into
    one of them leaves the other claiming items it cannot run.

    Neither half is graded on its exit code alone. Every pre-dispatch
    precondition shares that code, and a dispatch that claimed the item and then
    refused inside `materialize_overlay` returns it too -- which is exactly the
    stranded-`active` shape this position retires. The instruments are the claim
    seam, the launch seam, and the absence of a claim record in the journal.

    Both paths now reach the gate through ONE shared wall, so "wired into both"
    is a structural fact rather than two call sites that must be kept in step.
    That is why the wall module's existence is the first assertion here: without
    it there were two byte-identical private walls, and a gate added to one of
    them left the other claiming items it could not run.
    """
    assert _WALL_MODULE_PATH.is_file()
    log: list[str] = []
    journal = _RecordingJournal()
    journal_path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    item = _work_item(item_id="bd-ib-tyqklx")
    unadvanced = _auth_json_with_exp(exp=_NOW + _BELOW_FLOOR_REMAINING)
    _stub_credential_source(
        monkeypatch=monkeypatch, log=log, readings=(unadvanced, unadvanced, unadvanced, unadvanced)
    )
    _stub_dispatch(
        monkeypatch=monkeypatch, journal=journal, journal_path=journal_path, item=item, log=log
    )
    _stub_loop(
        monkeypatch=monkeypatch, journal=journal, journal_path=journal_path, item=item, log=log
    )

    dispatch_code = _dispatcher_run_commands.run_dispatch_command(
        args=_dispatch_args(repo=tmp_path, journal_path=journal_path, item_id=item.id)
    )
    loop_code = _dispatcher_loop_command.run_loop_command(
        args=_loop_args(repo=tmp_path, journal_path=journal_path)
    )

    assert (dispatch_code, loop_code) == (EXIT_PRECONDITION_ERROR, EXIT_PRECONDITION_ERROR)
    # Neither path claimed the item and neither created a run.
    assert "claim" not in log
    assert "launch" not in log
    assert "claim-and-launch" not in log
    # One refusal record per path, each naming the item it declined to claim.
    assert [record["stage"] for record in journal.records] == [
        _dispatcher_codex_credential_gate.CODEX_CREDENTIAL_GATE_STAGE,
        _dispatcher_codex_credential_gate.CODEX_CREDENTIAL_GATE_STAGE,
    ]
    assert all(record["unclaimed_work_item_ids"] == ["bd-ib-tyqklx"] for record in journal.records)
    errors = capsys.readouterr().err
    assert errors.count("C-mode dispatch refused") == 2
