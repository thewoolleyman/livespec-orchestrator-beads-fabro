"""The ledger readings a claimed causal supersession's cause is graded against.

`tests/integration/test_plan_misderived_supersession.py` drives the whole write
over the real store, so the readings that a healthy ledger produces are covered
there. This module covers the ones it cannot STAGE: a progress event whose
canonical payload did not parse, a carrier whose repository no configured target
resolves, and a carrier record the ledger holds without a readable status — each
a reading whose absence must refuse.

WHY THE DERIVING MATCH IS THE IDENTITY ALONE, which `bd-ib-4hznqp` corrected. The
epoch the clause asks the identity to resolve at is the DERIVATION's own, which
its payload records, while the epoch the supersession NAMES is the chain head.
Requiring the two to agree made a misderived obligation supersedable only while
nothing had been written since it was derived, so one retaining pointer write
locked the plan for its whole budget. The case below therefore resolves the SAME
identity from a chain that has moved past it, which is the shape the measured
incident had and the one the retired reading could not answer.

AND WHY AN UNPARSEABLE PAYLOAD STILL RESOLVES NOTHING. The reason moved with the
reading rather than going away: the payload is where the obligation that
transition WROTE is recorded, and the `misderived` verification now rests on
that obligation being the retained one. A comment whose identity this reader can
see but whose payload it cannot establishes nothing about the derivation it names.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import (
    _plan_supersession_evidence as evidence_module,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    CommittedTransition,
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    PLAN_PROGRESS_PREFIX,
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_supersession import CausalSupersession
from livespec_orchestrator_beads_fabro.commands._plan_supersession_evidence import (
    supersession_evidence,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    plan_comment_body,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_NOW = "2026-10-22T07:00:00Z"
_DEADLINE = "2099-10-10T12:00:00Z"
_EPIC = "bd-ib-plan"
_OWN = "repo"
_OWN_PREFIX = "bd-ib"
_CARRIER_REPO = "carrier-repo"
_CARRIER_PREFIX = "cr"
_CARRIER = f"{_CARRIER_PREFIX}-open"
_FIRST_OPERATION = "op-first"
_SECOND_OPERATION = "op-second"
_PLAN_RESUME_ACTOR = "plan-resume"
_OBLIGATION: dict[str, object] = {
    "repo": _OWN,
    "item_comment": {"item_id": _EPIC, "marker": "Plan Proof of Done"},
}


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix=_OWN_PREFIX,
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def _fake(*, repo: Path) -> FakeBeadsClient:
    client = make_beads_client(config=_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)
    return client


def _connection(*, prefix: str) -> dict[str, object]:
    return {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": prefix}}}


def _project(*, tmp_path: Path, configure_carrier: bool) -> Path:
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = dict(_connection(prefix=_OWN_PREFIX))
    if configure_carrier:
        configured["cross_repo_targets"] = {
            _CARRIER_REPO: {"github_url": f"https://github.com/thewoolleyman/{_CARRIER_REPO}"}
        }
        carrier = tmp_path / _CARRIER_REPO
        carrier.mkdir()
        _ = (carrier / ".livespec.jsonc").write_text(
            json.dumps(_connection(prefix=_CARRIER_PREFIX)), encoding="utf-8"
        )
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    return repo


def _seed(*, repo: Path, transitions: tuple[str, ...]) -> None:
    """A chain-tracked epic carrying one committed transition per named operation.

    Several transitions is the whole point of the fixture: only a chain that has
    moved more than once can tell an identity resolved at ITS OWN epoch from one
    resolved at the epoch the chain now stands at.
    """
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC,
            issue_type="epic",
            title=_EPIC,
            description="## Definition of Done\n\n- The plan reaches its archive.\n",
            assignee=None,
            created_at=_NOW,
        )
    )
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC,
        metadata=chain_cache_metadata(existing_metadata={}, latest_closed=None, current=genesis),
    )
    config = _config(repo=repo)
    for operation_id in transitions:
        head = read_chain_head(config=config, epic_id=_EPIC)
        assert isinstance(head, ChainHead), head
        committed = commit_transition(
            config=config,
            epic_id=_EPIC,
            request=TransitionRequest(
                operation_id=operation_id,
                observed_head=head,
                authority=AuthorityState(
                    required_result=_OBLIGATION,
                    original_deadline=_DEADLINE,
                    max_handoffs=4,
                    consumed_handoffs=1,
                ),
                event_kind="pointer",
                author=_PLAN_RESUME_ACTOR,
                now=_NOW,
            ),
        )
        assert isinstance(committed, CommittedTransition), committed
    fake.add_comment(
        issue_id=_EPIC,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author="plan-session",
            now=_NOW,
            body=f"carriers:\n- 1: {_CARRIER}",
        ),
    )


def _carrier_record(*, repo: Path) -> None:
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_CARRIER,
            issue_type="task",
            title=_CARRIER,
            description="a carrier of one plan assertion",
            assignee=None,
            created_at=_NOW,
        )
    )


def _supersession(*, epoch: int, operation_id: str = _SECOND_OPERATION) -> CausalSupersession:
    return CausalSupersession(
        superseded_result_identity="repo item_comment bd-ib-plan marker 'Plan Proof of Done'",
        previous_epoch=epoch,
        cause="misderived",
        deriving_operation_id=operation_id,
        open_carrier_id=_CARRIER,
        writer="plan-session",
    )


class _StatuslessRecordClient:
    """One read-only stand-in answering a status-less record for the carrier.

    Every verb this reading uses is delegated to the real client, so the stub
    changes exactly one answer: the carrier record's own shape.
    """

    def __init__(self, *, client: FakeBeadsClient) -> None:
        self._client = client

    def show_issue(self, *, issue_id: str) -> dict[str, object]:
        record = dict(self._client.show_issue(issue_id=issue_id))
        del record["status"]
        return record


def _statusless_carrier_client(*, config: StoreConfig) -> object:
    """`make_beads_client`, with the CARRIER tenant's reads routed to the stub."""
    client = make_beads_client(config=config)
    if config.prefix != _CARRIER_PREFIX:
        return client
    assert isinstance(client, FakeBeadsClient)
    return _StatuslessRecordClient(client=client)


def _unresolvable_connection(*, repository: ResultRepository) -> StoreConfig | None:
    """One repository whose tenant connection no longer resolves.

    Named rather than a lambda so the signature matches the seam it replaces:
    the argument is what the production reading passes, and a stand-in that
    accepted anything would pass against a caller that had stopped passing it.
    """
    assert repository.name == _CARRIER_REPO, repository
    return None


def _head(*, repo: Path) -> ChainHead:
    head = read_chain_head(config=_config(repo=repo), epic_id=_EPIC)
    assert isinstance(head, ChainHead), head
    return head


def test_no_supersession_takes_no_reading_at_all(tmp_path: Path) -> None:
    """The ordinary write is every write, and it pays none of these round trips."""
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _seed(repo=repo, transitions=(_FIRST_OPERATION,))

    assert (
        supersession_evidence(
            config=_config(repo=repo), epic_id=_EPIC, supersession=None, head=_head(repo=repo)
        )
        is None
    )


def test_the_deriving_identity_resolves_from_a_chain_that_has_moved_past_it(
    tmp_path: Path,
) -> None:
    """The identity resolves at ITS OWN epoch, whatever epoch the chain stands at.

    The first operation moved the chain to its own epoch and the second moved it
    on, so the first derivation sits one epoch back — the measured shape, where a
    retaining write had advanced the chain past the derivation. BOTH readings are
    taken with the supersession naming the HEAD epoch, which is the only epoch
    `validate_causal_supersession` admits, so the pair separates the epoch an
    identity is RESOLVED at from the epoch a supersession NAMES: the retired
    reading answered nothing for the first and resolved only the second.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    _seed(repo=repo, transitions=(_FIRST_OPERATION, _SECOND_OPERATION))
    head = _head(repo=repo)

    retained = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch, operation_id=_FIRST_OPERATION),
        head=head,
    )
    latest = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch, operation_id=_SECOND_OPERATION),
        head=head,
    )

    assert retained is not None
    assert retained.deriving is not None
    assert retained.deriving.author == _PLAN_RESUME_ACTOR
    assert latest is not None
    assert latest.deriving is not None
    assert latest.deriving.author == _PLAN_RESUME_ACTOR


def _unparseable_event(*, repo: Path, operation_id: str) -> None:
    """One progress-event comment whose canonical payload line is not JSON.

    Written through the client's own comment surface rather than a transition,
    because the production writer renders a parseable payload on every write —
    while a live ledger holds whatever a build of any age left behind, which is
    the population both cases below are about.
    """
    _fake(repo=repo).add_comment(
        issue_id=_EPIC,
        body=(
            f"{PLAN_PROGRESS_PREFIX}\nauthor: {_PLAN_RESUME_ACTOR}\ntimestamp: {_NOW}\n\n"
            f"operation: {operation_id}\nrecorded: {_NOW}\npayload: not-json"
        ),
    )


def test_a_progress_event_whose_payload_did_not_parse_resolves_nothing(
    tmp_path: Path,
) -> None:
    """The MATCHED event's payload carries the obligation it wrote.

    That obligation is the fact the `misderived` cause's verification rests on,
    so a comment this reader can see the operation identity in but not the
    payload of resolves NOTHING rather than being matched on the identity alone.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    _seed(repo=repo, transitions=(_FIRST_OPERATION,))
    head = _head(repo=repo)
    _unparseable_event(repo=repo, operation_id=_SECOND_OPERATION)

    evidence = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch),
        head=head,
    )

    assert evidence is not None
    assert evidence.deriving is None


def test_a_later_event_whose_payload_did_not_parse_retains_nothing(tmp_path: Path) -> None:
    """A later transition nobody can read is carried as having retained NOTHING.

    It is NOT skipped, which is the whole of the arm: the decision compares
    canonical identities, and `None` has none, so an unreadable later transition
    compares unequal to every obligation and refuses. Skipping it would let the
    one transition this reader cannot place be the cheapest route past the
    retention condition.

    Its control is the case above, which puts the unreadable payload on the
    MATCHED event instead and resolves no transition at all — so the two arms
    report different absences and neither stands in for the other.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    _seed(repo=repo, transitions=(_FIRST_OPERATION,))
    head = _head(repo=repo)
    _unparseable_event(repo=repo, operation_id=_SECOND_OPERATION)

    evidence = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch, operation_id=_FIRST_OPERATION),
        head=head,
    )

    assert evidence is not None
    assert evidence.deriving is not None
    assert evidence.deriving.required_result == _OBLIGATION
    assert evidence.deriving.later_results == (None,)


def test_a_carrier_whose_repository_resolves_to_no_configured_target_is_absent(
    tmp_path: Path,
) -> None:
    """The reading fails BEFORE any tenant is reached, and reports as absent.

    Its sibling below fails AFTER the record came back, and both are kept
    because a reader that had stopped resolving repositories at all would
    satisfy that one alone.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=False)
    _seed(repo=repo, transitions=(_FIRST_OPERATION,))
    head = _head(repo=repo)

    evidence = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch, operation_id=_FIRST_OPERATION),
        head=head,
    )

    assert evidence is not None
    assert evidence.carrier is None


def test_a_carrier_record_carrying_no_readable_status_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record with no status is evidence of nothing about where the carrier stands.

    The shape is produced through a small READ-ONLY stub keyed on the carrier
    tenant's own prefix, because the in-memory fake's public write surface cannot
    mint a record without one — while a live `omitempty`-sparse ledger can, which
    is exactly why the arm exists. The stub DELEGATES every other connection, so
    the deriving-transition read beside it is the real one.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    _seed(repo=repo, transitions=(_FIRST_OPERATION,))
    head = _head(repo=repo)
    monkeypatch.setattr(evidence_module, "make_beads_client", _statusless_carrier_client)

    evidence = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch, operation_id=_FIRST_OPERATION),
        head=head,
    )

    assert evidence is not None
    assert evidence.carrier is None


def test_a_carrier_repository_whose_connection_stops_resolving_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tenancy and the record read resolve the connection SEPARATELY.

    A credential that expires, or a configuration file rewritten, between the
    two leaves a repository that was indexed and can no longer answer — so the
    second resolution has its own failure, and it must refuse rather than fall
    through to a read it cannot take. The state is reached through the one seam
    that can produce it, because a single-threaded fixture reads one file twice
    and gets one answer.

    Its control is the case above, which reaches the SAME line of the same read
    with the resolution left alone and answers a readable carrier.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    _seed(repo=repo, transitions=(_FIRST_OPERATION,))
    head = _head(repo=repo)
    monkeypatch.setattr(evidence_module, "result_store_config", _unresolvable_connection)

    evidence = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch, operation_id=_FIRST_OPERATION),
        head=head,
    )

    assert evidence is not None
    assert evidence.carrier is None


def test_an_epic_whose_chain_tracks_no_obligation_is_not_plan_level(tmp_path: Path) -> None:
    """`plan_level` is read off the obligation, so no obligation answers False.

    The arm matters because the supersession's own identity check is graded
    separately: an authority tracking nothing would otherwise reach the
    plan-level condition with no target to read and have to guess.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC,
            issue_type="epic",
            title=_EPIC,
            description="## Definition of Done\n\n- The plan reaches its archive.\n",
            assignee=None,
            created_at=_NOW,
        )
    )
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC,
        metadata=chain_cache_metadata(existing_metadata={}, latest_closed=None, current=genesis),
    )

    evidence = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=0),
        head=_head(repo=repo),
    )

    assert evidence is not None
    assert evidence.plan_level is False
