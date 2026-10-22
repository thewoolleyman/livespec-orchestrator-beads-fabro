"""The ledger readings a claimed causal supersession's cause is graded against.

`tests/integration/test_plan_misderived_supersession.py` drives the whole write
over the real store, so the readings that a healthy ledger produces are covered
there. This module covers the ones it cannot STAGE, and every one of them is a
reading whose absence must refuse: the deriving transition resolved from a
DIFFERENT epoch of the same plan, a progress event whose canonical payload did
not parse, a carrier whose repository no configured target resolves, and a
carrier record the ledger holds without a readable status.

WHY THE EPOCH HALF OF THE DERIVING MATCH IS THE ONE WORTH STAGING. An operation
identity alone resolves A transition of this plan — a real one, recorded by a
real derivation actor — and the obligation it wrote is not the one being
superseded. That makes the resulting supersession look fully evidenced while
naming the wrong derivation, which is the one failure here that produces no
refusal at all.
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

    Several transitions is the whole point of the fixture: the deriving match is
    an identity AND an epoch, and only a chain that has moved more than once can
    tell a match on both from a match on the identity alone.
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


def test_the_deriving_match_needs_the_epoch_as_well_as_the_identity(tmp_path: Path) -> None:
    """An identity resolved at the WRONG epoch names a different derivation.

    Both transitions here are recorded by a real derivation actor, so an
    identity-only match returns a well-formed `DerivingTransition` and the
    supersession reads as fully evidenced while naming the derivation that wrote
    some earlier obligation. The pair is the discriminator: the same identity is
    asked for at the epoch it moved the chain to, and at the next one.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    _seed(repo=repo, transitions=(_FIRST_OPERATION, _SECOND_OPERATION))
    head = _head(repo=repo)

    matched = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch, operation_id=_FIRST_OPERATION),
        head=head,
    )
    mismatched = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch - 1, operation_id=_FIRST_OPERATION),
        head=head,
    )

    assert matched is not None
    assert matched.deriving is None
    assert mismatched is not None
    assert mismatched.deriving is not None
    assert mismatched.deriving.author == _PLAN_RESUME_ACTOR


def test_a_progress_event_whose_payload_did_not_parse_resolves_nothing(
    tmp_path: Path,
) -> None:
    """An event whose epoch could not be read cannot be matched on its epoch.

    The payload line is what carries the epoch, so a comment this reader can see
    the operation identity in but not the payload of resolves NOTHING rather than
    being matched on the identity alone.
    """
    repo = _project(tmp_path=tmp_path, configure_carrier=True)
    _carrier_record(repo=repo)
    _seed(repo=repo, transitions=(_FIRST_OPERATION,))
    head = _head(repo=repo)
    _fake(repo=repo).add_comment(
        issue_id=_EPIC,
        body=(
            f"{PLAN_PROGRESS_PREFIX}\nauthor: {_PLAN_RESUME_ACTOR}\ntimestamp: {_NOW}\n\n"
            f"operation: {_SECOND_OPERATION}\nrecorded: {_NOW}\npayload: not-json"
        ),
    )

    evidence = supersession_evidence(
        config=_config(repo=repo),
        epic_id=_EPIC,
        supersession=_supersession(epoch=head.epoch),
        head=head,
    )

    assert evidence is not None
    assert evidence.deriving is None


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
