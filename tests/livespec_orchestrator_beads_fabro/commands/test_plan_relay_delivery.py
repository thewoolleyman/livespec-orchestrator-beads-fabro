"""A relay's deadline and sender survive every later observation of it.

The integration tier binds Scenario 149's first outline for ONE recording. This
module covers what happens on the SECOND and every later one: a distinct recheck
observes the same relay again under its ORIGINAL deadline, and a relay id reused
against a different target is refused unless an explicit supersession carries the
displaced obligation's disposition forward.

WHY THE RECHECK CASES NAME A LATER DEADLINE THAN THE FIRST RECORDING. "Retrying
the same operation identity for an existing relay MUST return its recorded
observation and MUST NOT extend the original deadline; a distinct recheck
operation MAY record a new observation for that same relay and original
deadline." A recheck asking for the deadline it already has would pass against an
implementation that simply stored whatever it was given, which is the exact
defect — a sender that keeps re-recording its own relay would roll its own
obligation forward for ever and every record would look well-formed.

WHY THE CONFLICTING-TARGET CASES CHANGE ONLY THE TARGET. The relay id, the sender
and the deadline are held constant across the conflict pair, so the refusal is
evidence about the target and not about anything else the request carries.

WHY THE SUPERSESSION SURFACE IS REACHED THROUGH AN ASSERTION RATHER THAN AN
IMPORT. `RelaySupersession` and the request field that carries it do not exist
when this module's Red is authored, and a top-level import of a name a module
does not export dies at COLLECTION — which proves only that the name is absent,
never that the behaviour is unimplemented. Asserting the surface first is the
same discipline the new-module tests apply to a path.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_relay_delivery
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_relay_delivery import (
    RelayRefusal,
    RelayRequest,
    record_relay,
)
from livespec_orchestrator_beads_fabro.commands._plan_relay_projection import read_relay_records
from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    DELIVERY_UNDELIVERED,
    RelayAcknowledgements,
    RelayRecord,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
    OBSERVATION_UNSATISFIED,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-relayepic"
_TARGET_ID = "bd-ib-relaytarget"
_OTHER_TARGET_ID = "bd-ib-relayother"
_RELAY_ID = "relay-1"
_SENDER = "relay-supervisor"
_CONSUMER = "relay-consumer"
_ORIGINAL_DEADLINE = "2026-10-20T18:00:00Z"
_LATER_DEADLINE = "2026-11-30T18:00:00Z"
_FIRST_AT = "2026-10-20T09:00:00Z"
_RECHECK_AT = "2026-10-20T12:00:00Z"


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """A refusing forge seam; no case here names a forge, proof or branch target."""

    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(tuple(argv))
        return CommandResult(exit_code=1, stdout="", stderr="no forge seam is expected")


def _seed(*, tmp_path: Path) -> tuple[Path, StoreConfig, FakeBeadsClient]:
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=repo)
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    for issue_id, issue_type in (
        (_EPIC_ID, "epic"),
        (_TARGET_ID, "feature"),
        (_OTHER_TARGET_ID, "feature"),
    ):
        _ = client.create_issue(
            draft=IssueDraft(
                issue_id=issue_id,
                issue_type=issue_type,
                title=issue_id,
                description="Definition of Done\n\n- A thing holds.",
                assignee=None,
                created_at="2026-10-20T08:00:00Z",
                metadata={"rank": "a0"},
            )
        )
        client.update_issue(issue_id=issue_id, status="active")
    return repo, config, client


def _result(*, item_id: str = _TARGET_ID) -> dict[str, object]:
    return {"repo": _PROJECT_NAME, "item_status": {"item_id": item_id, "status": "done"}}


def _supersession(*, relay_id: str, reason: str) -> Any:
    """One explicit supersession, proving the surface exists before reaching for it."""
    assert hasattr(
        _plan_relay_delivery, "RelaySupersession"
    ), "_plan_relay_delivery exports no RelaySupersession"
    return _plan_relay_delivery.RelaySupersession(relay_id=relay_id, reason=reason)


def _request(*, repo: Path, config: StoreConfig, **overrides: object) -> RelayRequest:
    declared = {field_.name for field_ in fields(RelayRequest)}
    assert declared >= set(overrides), f"RelayRequest declares no {set(overrides) - declared}"
    base = RelayRequest(
        config=config,
        project_root=repo,
        runner=_Runner(),
        epic_id=_EPIC_ID,
        relay_id=_RELAY_ID,
        operation_id="relay-record-1",
        sender=_SENDER,
        required_result=_result(),
        deadline=_ORIGINAL_DEADLINE,
        acknowledgements=RelayAcknowledgements(
            receipt_ack="2026-10-20T08:55:00Z",
            peer_recorded="2026-10-20T08:56:00Z",
        ),
        now=_FIRST_AT,
    )
    return replace(base, **overrides)


def _recorded(*, outcome: RelayRecord | RelayRefusal) -> RelayRecord:
    assert isinstance(outcome, RelayRecord), outcome
    return outcome


def test_a_recheck_of_an_unmet_relay_keeps_the_original_deadline_and_sender(
    tmp_path: Path,
) -> None:
    """The second observation names a LATER deadline and does not get it.

    "If the result is unsatisfied or unobservable, the primitive MUST record an
    undelivered relay, its unchanged deadline and the observation; the sender
    retains the obligation." A sender re-recording its own relay must not be
    able to roll its own clock forward, and every record it writes looks
    well-formed either way — so the deadline is read back off the relay's own
    history rather than off the request.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    first = _recorded(outcome=record_relay(request=_request(repo=repo, config=config)))

    recheck = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo,
                config=config,
                operation_id="relay-recheck-1",
                deadline=_LATER_DEADLINE,
                now=_RECHECK_AT,
            )
        )
    )

    assert first.original_deadline == _ORIGINAL_DEADLINE
    assert recheck.original_deadline == _ORIGINAL_DEADLINE
    assert recheck.sender == _SENDER
    assert recheck.disposition == DELIVERY_UNDELIVERED
    assert recheck.observation.status == OBSERVATION_UNSATISFIED
    assert recheck.recorded_at == _RECHECK_AT
    assert len(read_relay_records(client=client, epic_id=_EPIC_ID)) == 2


def test_a_recheck_by_an_independent_consumer_keeps_the_relay_s_own_sender(
    tmp_path: Path,
) -> None:
    """The recheck names ITS OWN identity as sender and does not become the owner.

    "Timeout MUST retain sender ownership and the original deadline while the
    independent consumer performs bounded recovery, even when the sender produces
    no new handoff", and "Owner disappearance requires explicit recoverable
    takeover, not silent discharge." The independent consumer IS the clause's own
    recheck recorder, so the sender is read back off the relay's own history
    exactly as the deadline is. A recheck that stored the identity it was handed
    would transfer ownership with none of the three legs present and with no
    record saying a transfer happened — and because the appended comment is
    authored AS the relay's sender, the timeline would then report that an expiry
    falls to the consumer rather than to the party that still owes it.

    THIS IS THE HALF THE DEADLINE CASE ABOVE CANNOT SHOW. That case reuses the
    original sender in its own request, so its sender assertion holds whether or
    not the value was carried forward: only a recheck naming a DIFFERENT sender
    can tell a carried-forward owner from a stored one, which is the same reason
    the deadline cases all name a later deadline than the first recording.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))

    recheck = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo,
                config=config,
                operation_id="relay-recheck-1",
                sender=_CONSUMER,
                deadline=_LATER_DEADLINE,
                now=_RECHECK_AT,
            )
        )
    )

    assert recheck.sender == _SENDER
    assert recheck.original_deadline == _ORIGINAL_DEADLINE
    assert recheck.disposition == DELIVERY_UNDELIVERED
    assert recheck.ownership_transferable is False
    text = client.list_comments(issue_id=_EPIC_ID)[1]["text"]
    assert isinstance(text, str)
    assert f"\nauthor: {_SENDER}\n" in text
    assert f"author: {_CONSUMER}" not in text


def test_subsequent_target_evidence_discharges_the_relay_under_that_same_deadline(
    tmp_path: Path,
) -> None:
    """ "Subsequent target evidence MAY discharge the relay."

    The positive control for the case above: the same relay, rechecked after the
    target really moved, records delivered — still under the deadline its first
    observation established, because a discharge is not a new obligation.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))
    client.update_issue(issue_id=_TARGET_ID, status="done")

    recheck = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo,
                config=config,
                operation_id="relay-recheck-1",
                deadline=_LATER_DEADLINE,
                now=_RECHECK_AT,
            )
        )
    )

    assert recheck.observation.status == OBSERVATION_SATISFIED
    assert recheck.delivered is True
    assert recheck.legs.target_evidence == recheck.observation.evidence
    assert recheck.ownership_transferable is True
    assert recheck.original_deadline == _ORIGINAL_DEADLINE


def test_a_recheck_whose_target_cannot_be_observed_keeps_the_original_deadline(
    tmp_path: Path,
) -> None:
    """The UNOBSERVABLE half of the same rule, which is the easier one to lose.

    "If the result is unsatisfied or unobservable, the primitive MUST record an
    undelivered relay, its unchanged deadline and the observation." A failure to
    MEASURE is not a measurement, so it moves neither the delivery verdict nor
    the clock — and the recorded argv is what proves the forge was genuinely
    asked rather than skipped, which an undelivered verdict alone cannot show.
    """
    repo, config, _ = _seed(tmp_path=tmp_path)
    forge = {"repo": _PROJECT_NAME, "pull_request_state": {"number": 149, "state": "merged"}}
    _ = record_relay(request=_request(repo=repo, config=config, required_result=forge))
    runner = _Runner()

    recheck = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo,
                config=config,
                runner=runner,
                operation_id="relay-recheck-1",
                required_result=forge,
                deadline=_LATER_DEADLINE,
                now=_RECHECK_AT,
            )
        )
    )

    assert runner.calls != []
    assert recheck.observation.status == OBSERVATION_UNOBSERVABLE
    assert recheck.delivered is False
    assert recheck.legs.target_evidence is None
    assert recheck.sender == _SENDER
    assert recheck.original_deadline == _ORIGINAL_DEADLINE


def test_a_recheck_carries_forward_acknowledgements_it_does_not_restate(
    tmp_path: Path,
) -> None:
    """Both transport legs are retained across observations, separately.

    "The existing supervisor obligation schema MUST retain receipt_ack and
    peer_recorded". A recheck that silently dropped them would make a relay look
    less acknowledged the more often it was observed, and a later peer recording
    must still be able to replace the value it supersedes.
    """
    repo, config, _ = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))

    recheck = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo,
                config=config,
                operation_id="relay-recheck-1",
                acknowledgements=RelayAcknowledgements(peer_recorded="2026-10-20T11:00:00Z"),
                now=_RECHECK_AT,
            )
        )
    )

    assert recheck.legs.receipt_ack == "2026-10-20T08:55:00Z"
    assert recheck.legs.peer_recorded == "2026-10-20T11:00:00Z"
    assert recheck.legs.target_evidence is None


def test_reusing_a_relay_id_against_a_conflicting_target_is_refused_unwritten(
    tmp_path: Path,
) -> None:
    """ "a conflicting target requires a new explicit supersession".

    Only the target changes across this pair, so the refusal is evidence about
    the target. Nothing is written, because a second obligation wearing the first
    one's id would make the displaced one unreadable: the later record is the
    latest for that id, and `bd comments` offers no edit.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))

    refused = record_relay(
        request=_request(
            repo=repo,
            config=config,
            operation_id="relay-record-2",
            required_result=_result(item_id=_OTHER_TARGET_ID),
            now=_RECHECK_AT,
        )
    )

    assert isinstance(refused, RelayRefusal)
    assert _OTHER_TARGET_ID in refused.detail
    assert _TARGET_ID in refused.detail
    assert len(read_relay_records(client=client, epic_id=_EPIC_ID)) == 1


def test_an_explicit_supersession_admits_the_new_target_carrying_the_old_disposition(
    tmp_path: Path,
) -> None:
    """The successor preserves what it displaced, which nothing else can.

    The predecessor's own comment cannot be amended, so the clause's "preserves
    the old obligation's disposition" is satisfiable only on the record that
    replaces it — and the predecessor's own latest observation stays readable,
    undischarged, under its own relay id.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    displaced = _recorded(outcome=record_relay(request=_request(repo=repo, config=config)))

    successor = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo,
                config=config,
                relay_id="relay-2",
                operation_id="relay-record-2",
                required_result=_result(item_id=_OTHER_TARGET_ID),
                deadline=_LATER_DEADLINE,
                supersedes=_supersession(
                    relay_id=_RELAY_ID,
                    reason="the referral moved to the attention slice's own item",
                ),
                now=_RECHECK_AT,
            )
        )
    )

    assert successor.superseded_relay_id == _RELAY_ID
    assert successor.superseded_disposition is not None
    assert displaced.disposition in successor.superseded_disposition
    assert displaced.original_deadline in successor.superseded_disposition
    assert successor.original_deadline == _LATER_DEADLINE
    records = read_relay_records(client=client, epic_id=_EPIC_ID)
    assert [record.relay_id for record in records] == [_RELAY_ID, "relay-2"]


@pytest.mark.parametrize(
    ("displaced", "reason", "needle"),
    [
        ("relay-9", "a reason", "names no recorded relay"),
        (_RELAY_ID, "   ", "causal reason"),
        ("relay-2", "a reason", "its own relay id"),
    ],
)
def test_a_supersession_that_establishes_nothing_is_refused(
    tmp_path: Path, displaced: str, reason: str, needle: str
) -> None:
    """Three ways a supersession carries no displaced obligation forward.

    A relay id nothing recorded displaces nothing; a blank reason records no
    cause; and a supersession naming the SUCCESSOR's own id would shadow the
    very disposition it claims to preserve, because the successor then becomes
    the latest record for that id.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))

    refused = record_relay(
        request=_request(
            repo=repo,
            config=config,
            relay_id="relay-2",
            operation_id="relay-record-2",
            required_result=_result(item_id=_OTHER_TARGET_ID),
            supersedes=_supersession(relay_id=displaced, reason=reason),
            now=_RECHECK_AT,
        )
    )

    assert isinstance(refused, RelayRefusal)
    assert needle in refused.detail
    assert len(read_relay_records(client=client, epic_id=_EPIC_ID)) == 1


def test_a_supersession_of_an_unchanged_target_is_refused(tmp_path: Path) -> None:
    """A supersession is for a CONFLICTING target and for nothing else.

    Admitting one where the target has not changed is the laundering route the
    deadline rule exists to close: a fresh relay id, the same obligation, and a
    deadline of the sender's own choosing, with a supersession record that reads
    as the clause's sanctioned path.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))

    refused = record_relay(
        request=_request(
            repo=repo,
            config=config,
            relay_id="relay-2",
            operation_id="relay-record-2",
            deadline=_LATER_DEADLINE,
            supersedes=_supersession(relay_id=_RELAY_ID, reason="a reason"),
            now=_RECHECK_AT,
        )
    )

    assert isinstance(refused, RelayRefusal)
    assert "conflicting target" in refused.detail
    assert len(read_relay_records(client=client, epic_id=_EPIC_ID)) == 1
