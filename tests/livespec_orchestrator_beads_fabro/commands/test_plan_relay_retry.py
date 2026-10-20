"""Retrying one relay operation returns what that operation recorded.

"Retrying the same operation identity for an existing relay MUST return its
recorded observation and MUST NOT extend the original deadline." A retry is not
a second observation: it is the SAME act, re-entered because its caller could not
tell whether the first attempt landed, and the clause's whole point is that
asking twice must be indistinguishable from asking once.

WHY EVERY CASE MEASURES SOMETHING THE RETURN VALUE CANNOT CARRY. A primitive that
simply re-observed the target and re-recorded it would return a record agreeing
with the first on the deadline, the relay id and the target — the three fields an
obvious assertion would check — while writing a second comment, re-reading the
target and, if the target had moved in between, reporting a DIFFERENT observation
under the same operation identity. So each case reads one of: the number of
`plan-relay-event` comments on the epic, the number of reads the ledger seam was
asked for, or the observation itself after the target has changed underneath.

THE TARGET IS MOVED BETWEEN THE TWO CALLS IN THE DISCRIMINATING CASE. That is the
one fixture under which a re-observing implementation cannot return the recorded
observation by coincidence, and it is also the real incident: a sender retries
because it timed out, by which time the world has moved on.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_relay_delivery import (
    RelayRefusal,
    RelayRequest,
    record_relay,
)
from livespec_orchestrator_beads_fabro.commands._plan_relay_projection import read_relay_records
from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    RelayAcknowledgements,
    RelayRecord,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNSATISFIED,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-relayepic"
_TARGET_ID = "bd-ib-relaytarget"
_RELAY_ID = "relay-1"
_OPERATION_ID = "relay-record-1"
_SENDER = "relay-supervisor"
_ORIGINAL_DEADLINE = "2026-10-20T18:00:00Z"
_LATER_DEADLINE = "2026-11-30T18:00:00Z"
_FIRST_AT = "2026-10-20T09:00:00Z"
_RETRY_AT = "2026-10-20T12:00:00Z"


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """A refusing forge seam that records what it was asked.

    The forge cases here want the read COUNT, which is the only instrument that
    separates a retry answered from the record from one answered by asking again.
    """

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
        return CommandResult(exit_code=1, stdout="", stderr="the forge refused this read")


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
    for issue_id, issue_type in ((_EPIC_ID, "epic"), (_TARGET_ID, "feature")):
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


def _result() -> dict[str, object]:
    return {"repo": _PROJECT_NAME, "item_status": {"item_id": _TARGET_ID, "status": "done"}}


def _request(*, repo: Path, config: StoreConfig, **overrides: object) -> RelayRequest:
    base = RelayRequest(
        config=config,
        project_root=repo,
        runner=_Runner(),
        epic_id=_EPIC_ID,
        relay_id=_RELAY_ID,
        operation_id=_OPERATION_ID,
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


def test_a_retried_operation_returns_its_own_recorded_observation(tmp_path: Path) -> None:
    """The target MOVES between the two calls and the retry does not notice.

    This is the fixture under which a re-observing implementation cannot pass by
    coincidence: it would return `satisfied`, and would record a discharge under
    an operation identity whose own act observed the opposite.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    first = _recorded(outcome=record_relay(request=_request(repo=repo, config=config)))
    assert first.observation.status == OBSERVATION_UNSATISFIED
    client.update_issue(issue_id=_TARGET_ID, status="done")

    retry = _recorded(
        outcome=record_relay(
            request=_request(repo=repo, config=config, deadline=_LATER_DEADLINE, now=_RETRY_AT)
        )
    )

    assert retry == first
    assert retry.observation.status == OBSERVATION_UNSATISFIED
    assert retry.delivered is False
    assert retry.original_deadline == _ORIGINAL_DEADLINE
    assert retry.recorded_at == _FIRST_AT


def test_a_retry_appends_no_second_record_to_the_epic(tmp_path: Path) -> None:
    """One operation, one durable record.

    A second comment under one operation identity would make the relay's history
    report two observations where one act took place, and `bd comments` offers no
    delete — so the duplicate would stand for the life of the epic.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))

    _ = record_relay(request=_request(repo=repo, config=config, now=_RETRY_AT))

    records = read_relay_records(client=client, epic_id=_EPIC_ID)
    assert len(records) == 1
    assert records[0].recorded_at == _FIRST_AT


def test_a_retry_spends_no_second_observation_of_the_target(tmp_path: Path) -> None:
    """The recorded observation is returned, so the target is not asked again.

    Read off the seam rather than the return value: a retry that re-observed and
    then discarded the reading would return the right record while spending the
    forge call the clause says it owes nothing for.
    """
    repo, config, _ = _seed(tmp_path=tmp_path)
    forge = {"repo": _PROJECT_NAME, "pull_request_state": {"number": 149, "state": "merged"}}
    first_runner = _Runner()
    _ = record_relay(
        request=_request(repo=repo, config=config, runner=first_runner, required_result=forge)
    )
    assert first_runner.calls != []
    retry_runner = _Runner()

    _ = record_relay(
        request=_request(
            repo=repo,
            config=config,
            runner=retry_runner,
            required_result=forge,
            now=_RETRY_AT,
        )
    )

    assert retry_runner.calls == []


def test_a_distinct_recheck_is_not_a_retry_and_does_observe_again(tmp_path: Path) -> None:
    """The control: without it, a primitive that answered EVERY call from history.

    "a distinct recheck operation MAY record a new observation for that same
    relay and original deadline" — so the same relay under a new operation
    identity reads the target, records a second observation, and discharges on
    the evidence it finds.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    _ = record_relay(request=_request(repo=repo, config=config))
    client.update_issue(issue_id=_TARGET_ID, status="done")

    recheck = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo, config=config, operation_id="relay-recheck-1", now=_RETRY_AT
            )
        )
    )

    assert recheck.observation.status == OBSERVATION_SATISFIED
    assert recheck.delivered is True
    assert recheck.original_deadline == _ORIGINAL_DEADLINE
    assert len(read_relay_records(client=client, epic_id=_EPIC_ID)) == 2


def test_an_operation_identity_reused_across_relays_answers_its_own_relay(
    tmp_path: Path,
) -> None:
    """A retry is recognised by BOTH identities, never by the operation alone.

    One sender numbering its operations per relay is the ordinary case, so an
    operation identity matched across the whole epic would answer a fresh relay's
    first recording with another relay's record — returning a target the caller
    never named, under a deadline it never set.
    """
    repo, config, client = _seed(tmp_path=tmp_path)
    first = _recorded(outcome=record_relay(request=_request(repo=repo, config=config)))

    other = _recorded(
        outcome=record_relay(
            request=_request(
                repo=repo,
                config=config,
                relay_id="relay-2",
                deadline=_LATER_DEADLINE,
                now=_RETRY_AT,
            )
        )
    )

    assert other != first
    assert other.relay_id == "relay-2"
    assert other.original_deadline == _LATER_DEADLINE
    assert len(read_relay_records(client=client, epic_id=_EPIC_ID)) == 2
