"""A scheduled wait survives a restart, and a passed instant does not spin.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Hold observations and their retirement evidence MUST remain
reconstructible after any repository-local dispatch journal is removed. ...
Availability evidence MUST be discoverable host-wide from the factory's native
run records." And: "the Dispatcher MUST schedule another admission evaluation.
... The scheduled evaluation falls at the earliest expiry among the holds that
empty a chain, and otherwise after
`dispatcher.credential_reprobe_interval_seconds`; no human valve is the remedy
for that wait."

RECONSTRUCTION IS ASSERTED AS A PROPERTY OF THE DERIVATION, NOT OF A SAVED
SCHEDULE. The instant is a function of the authoritative availability evidence
plus the committed cadence, so a second resolution taken with no shared process
state reproduces it exactly. That is what makes a Dispatcher restart a no-op
here -- and the sidecar assertion is the other half of the same claim, because
the clause forbids any "hold sidecar file, cache, or store" holding or
mirroring this evidence. A scheduler that persisted its own wait would satisfy
the equality assertion and violate that prohibition.

THE EVIDENCE-TRACKING CASE IS WHAT MAKES THE EQUALITY CASE MEAN SOMETHING. A
derivation that returned a CONSTANT would reproduce itself perfectly across any
number of restarts; so a sibling case retires the hold by advancing the clock
past its bounded expiry and asserts the reconstructed wait MOVES to the cadence
arm. Reproducibility and responsiveness are different properties and a single
fixture cannot test both.

A PASSED INSTANT YIELDS NO DELAY AT ALL, AND THAT IS NOT THE SAME AS ZERO. Zero
is a scheduled immediate retry, which a loop reading it would take again and
again for as long as the chain stayed empty -- the busy loop the bounded cadence
exists to prevent. `None` says there is nothing to sleep for: the ordinary pass
reevaluates once and the loop's own cadence governs what happens next. Both
cases therefore assert the EXACT value rather than truthiness, because `0` and
`None` are both falsy and the distinction between them is the whole point.

ONE PASS SCHEDULES ONE INSTANT FOR THE WHOLE WAVE. Every item an emptied chain
refuses is waiting on the same evidence, so a per-row derivation would let two
rows refused by one outage report two instants a later pass would then have to
choose between. The wave case asserts the recorded instants are identical and
that the availability evidence was read ONCE.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_availability_wait import availability_wait
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    TYPED_HOLD_SKIP,
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import HOLD_STAGE
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-15T12:00:00Z"
_INTERVAL = 900
_NOW_PLUS_INTERVAL = "2026-10-15T12:15:00Z"

_OCCURRED = "2026-10-15T11:55:00Z"
_HOLD_EXPIRY = "2026-10-15T12:10:00Z"
# Strictly after `_HOLD_EXPIRY`: the bounded expiry has elapsed, so the ledger
# no longer reports the record live.
_AFTER_EXPIRY = "2026-10-15T12:20:00Z"
_AFTER_EXPIRY_PLUS_INTERVAL = "2026-10-15T12:35:00Z"

_DOMAIN = "availability-domain"


def _delay_seconds() -> Any:
    """`availability_wait_delay_seconds`, asserted to exist before use.

    Reached through its module rather than imported at the top so this
    module's Red fails on a genuine assertion instead of at collection.
    """
    module = import_module(f"{_COMMANDS}._acp_availability_wait")
    assert hasattr(
        module, "availability_wait_delay_seconds"
    ), "availability_wait_delay_seconds is not implemented yet"
    return module.availability_wait_delay_seconds


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _item(*, item_id: str, rank: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title=f"Waiting item {item_id}",
        description="## Definition of Done\n\n- The product waits.\n",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
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
                    "dispatcher": {"credential_reprobe_interval_seconds": _INTERVAL},
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _seed_observation(*, journal: JournalFile) -> None:
    """One live schema-v1 observation, as the authoritative evidence source."""
    journal.append(
        record={
            "stage": HOLD_STAGE,
            "schema_version": 1,
            "observation_id": "acpobs-restart",
            "scope": _DOMAIN,
            "hold_key": "codex",
            "candidate_key": None,
            "cause": "quota",
            "evidence_kind": "candidate-attempt",
            "evidence_id": "run-1",
            "occurred_at": _OCCURRED,
            "expires_at": _HOLD_EXPIRY,
            "work_item_id": "bd-other",
            "node": "fix",
        }
    )


def _skip() -> SkippedCandidate:
    return SkippedCandidate(
        availability_key="codex",
        candidate_key="only",
        reason=TYPED_HOLD_SKIP,
        cause="quota",
        scope=_DOMAIN,
        hold_key="codex",
    )


def _verdict_from_journal(*, journal_path: Path, now_iso: str) -> AcpPreflightVerdict:
    """One Dispatcher's whole evaluation, read from the journal and nothing else.

    This is the reconstruction: a restarted Dispatcher holds no scheduler
    state, so its verdict and its wait come from the same evidence walk a first
    start would have taken.
    """
    ledger = read_acp_hold_ledger(journal_path=journal_path, now_iso=now_iso)
    return AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=(NodePreflight(node="fix", enabled=True, candidates=(), skipped=(_skip(),)),),
        success_critical=("implement",),
        admission_required=("implement", "fix"),
        exhausted=("fix",),
        holds=ledger.holds,
        unobservable=ledger.unobservable,
    )


def _wait_from_journal(*, journal_path: Path, now_iso: str) -> Any:
    return availability_wait(
        verdict=_verdict_from_journal(journal_path=journal_path, now_iso=now_iso),
        holds=_verdict_from_journal(journal_path=journal_path, now_iso=now_iso).holds,
        now_iso=now_iso,
        reprobe_interval_seconds=_INTERVAL,
    )


def test_the_scheduled_wait_reconstructs_from_the_journal_after_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two independent resolutions, no shared state, one identical instant."""
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    _seed_observation(journal=journal)

    first = _wait_from_journal(journal_path=journal.path, now_iso=_NOW)
    restarted = _wait_from_journal(journal_path=journal.path, now_iso=_NOW)

    assert first is not None
    assert restarted is not None
    assert restarted == first
    assert restarted.reevaluate_at == _HOLD_EXPIRY
    assert [hold.observation_id for hold in restarted.holds] == ["acpobs-restart"]


def test_the_reconstructed_wait_tracks_the_evidence_rather_than_repeating_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: a constant would reproduce perfectly and mean nothing.

    Past the record's bounded expiry the ledger stops reporting it live, so the
    reconstruction moves to the cadence arm. Expiry is the retirement route
    here -- nothing was cleared and nothing was rewritten.
    """
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    _seed_observation(journal=journal)

    before = _wait_from_journal(journal_path=journal.path, now_iso=_NOW)
    after = _wait_from_journal(journal_path=journal.path, now_iso=_AFTER_EXPIRY)

    assert before is not None
    assert after is not None
    assert before.reevaluate_at == _HOLD_EXPIRY
    assert after.reevaluate_at == _AFTER_EXPIRY_PLUS_INTERVAL
    assert after.holds == ()


def test_no_sidecar_state_is_written_for_the_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "No separate hold sidecar file, cache, or store MAY hold this evidence."

    The journal the evidence already lives in is the ONLY file the repository
    gains. A persisted schedule would satisfy every equality assertion above
    while being exactly what the clause forbids.
    """
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    _seed_observation(journal=journal)
    before = {path.name for path in repo.iterdir()}

    wait = _wait_from_journal(journal_path=journal.path, now_iso=_NOW)

    assert wait is not None
    assert {path.name for path in repo.iterdir()} == before


def test_a_passed_instant_schedules_no_delay_rather_than_an_immediate_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Reevaluated once per loop pass rather than retried in a busy loop."

    `None` and `0` are both falsy, so the exact value is asserted: `0` is a
    scheduled immediate retry a loop would take over and over while the chain
    stayed empty.
    """
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    _seed_observation(journal=journal)
    delay = _delay_seconds()
    wait = _wait_from_journal(journal_path=journal.path, now_iso=_NOW)

    assert wait is not None
    assert wait.reevaluate_at == _HOLD_EXPIRY
    assert delay(wait=wait, now_iso=_AFTER_EXPIRY) is None
    # The exact instant counts as due: the wait is over, not still running.
    assert delay(wait=wait, now_iso=_HOLD_EXPIRY) is None


def test_a_future_instant_schedules_the_remaining_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The paired positive case: a real wait reports a real, positive delay."""
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    _seed_observation(journal=journal)
    delay = _delay_seconds()
    wait = _wait_from_journal(journal_path=journal.path, now_iso=_NOW)

    assert wait is not None
    # `_NOW` to `_HOLD_EXPIRY` is ten minutes.
    assert delay(wait=wait, now_iso=_NOW) == 600


def test_an_unreadable_clock_schedules_no_delay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed: a clock nobody can read cannot authorise a sleep.

    Returning a delay here would hold the loop for a duration derived from
    text that does not parse; `None` leaves the pass to reevaluate normally.
    """
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    _seed_observation(journal=journal)
    delay = _delay_seconds()
    wait = _wait_from_journal(journal_path=journal.path, now_iso=_NOW)

    assert wait is not None
    assert delay(wait=wait, now_iso="not-an-instant") is None


def test_one_pass_schedules_one_instant_for_the_whole_refused_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every row refused by one outage waits for the same instant.

    The availability evidence is read ONCE for the pass, so a per-row
    derivation -- which would also be a per-row ledger walk -- fails both
    assertions here.
    """
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    _seed_observation(journal=journal)
    config = _config(repo_root=repo)
    items = [_item(item_id="bd-one", rank="a1"), _item(item_id="bd-two", rank="a2")]
    for item in items:
        append_work_item(path=config, item=item)

    reads: list[str] = []
    eligibility = import_module(f"{_COMMANDS}._dispatcher_admission_eligibility")
    real_resolve = eligibility.resolve_availability_wait

    def _counted(*, repo: Path, verdict: Any, now_iso: str) -> Any:
        reads.append(now_iso)
        return real_resolve(repo=repo, verdict=verdict, now_iso=now_iso)

    monkeypatch.setattr(eligibility, "resolve_availability_wait", _counted)

    _admittable, refused = filter_eligible_candidates(
        repo=repo,
        preflight=_verdict_from_journal(journal_path=journal.path, now_iso=_NOW),
        candidates=items,
        journal=journal,
    )

    assert len(refused) == 2
    records = [
        json.loads(line)
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if line and json.loads(line).get("stage") == ACP_PREFLIGHT_REFUSAL_STAGE
    ]
    assert len(records) == 2
    instants = {record["scheduled_reevaluation_at"] for record in records}
    assert instants == {_HOLD_EXPIRY}
    # ONE derivation for the pass, not one per refused row.
    assert len(reads) == 1
