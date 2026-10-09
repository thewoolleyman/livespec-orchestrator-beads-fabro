"""Tests for the two ledger adapters: item status and the exact item marker.

The hermetic in-memory tenant is the ledger here (the autouse fixture in this
tree's conftest), so every read goes through the production client seam.

ONE SEAM IS STOOD IN, FOR ONE GUARD. A beads record is `omitempty`-sparse, so a
record carrying no `status` key is a real shape the adapter has to answer for, and
the in-memory tenant always writes one. That guard is therefore exercised through
a stand-in client; every other case drives the real fake.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsRecord,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_result_ledger import (
    MARKER_NARROWING,
    UNRESOLVED_CONNECTION,
    observe_item_comment,
    observe_item_status,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
    OBSERVATION_UNSATISFIED,
    SOURCE_LEDGER,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ItemCommentTarget,
    ItemStatusTarget,
)

_ITEM_ID = "bd-ib-ledger"
_NOW = "2026-10-08T12:00:00Z"
_MARKER = "relay-delivery: delivered"


def _repo(*, tmp_path: Path, prefix: str | None = "bd-ib") -> ResultRepository:
    clone = tmp_path / "repo"
    clone.mkdir()
    connection: dict[str, object] = {} if prefix is None else {"prefix": prefix}
    _ = (clone / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": connection}}),
        encoding="utf-8",
    )
    return ResultRepository(name="repo", clone=clone)


def _seed(*, repository: ResultRepository, status: str) -> None:
    client = make_beads_client(config=store_config(repo=repository.clone))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="feature",
            title=_ITEM_ID,
            description="",
            assignee=None,
            created_at="2026-10-08T00:00:00Z",
        )
    )
    client.update_issue(issue_id=_ITEM_ID, status=status)


class _StatuslessClient:
    """A tenant whose record omits `status`, the way a sparse `bd` record can."""

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        return {"id": issue_id}


def test_a_matching_status_is_satisfied_with_the_record_as_its_evidence(
    tmp_path: Path,
) -> None:
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="ready")
    observation = observe_item_status(
        repository=repository,
        target=ItemStatusTarget(item_id=_ITEM_ID, status="ready"),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.source == SOURCE_LEDGER
    assert observation.evidence == f"ledger record {_ITEM_ID} at status ready"
    assert observation.observed_at == _NOW


def test_a_different_status_is_unsatisfied_and_reports_the_status_it_read(
    tmp_path: Path,
) -> None:
    """A confident negative, citing the status actually standing on the record."""
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="ready")
    observation = observe_item_status(
        repository=repository,
        target=ItemStatusTarget(item_id=_ITEM_ID, status="done"),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.evidence == f"ledger record {_ITEM_ID} at status ready"
    assert "not the expected done" in observation.detail


def test_an_unreadable_connection_makes_the_status_read_unobservable(
    tmp_path: Path,
) -> None:
    """A repository whose configuration resolves no connection was never queried."""
    repository = _repo(tmp_path=tmp_path, prefix=None)
    observation = observe_item_status(
        repository=repository,
        target=ItemStatusTarget(item_id=_ITEM_ID, status="ready"),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_LEDGER
    assert observation.detail == UNRESOLVED_CONNECTION
    assert observation.evidence == ""


def test_an_item_absent_from_the_tenant_makes_the_status_read_unobservable(
    tmp_path: Path,
) -> None:
    """An item the tenant does not hold says nothing about where that item stands.

    Deliberately NOT a confident negative: "this item is not at `ready`" would be
    a claim about an item the read never found, and its remedy — file it, or fix
    the id — is not the remedy an unsatisfied reading points at.
    """
    repository = _repo(tmp_path=tmp_path)
    observation = observe_item_status(
        repository=repository,
        target=ItemStatusTarget(item_id="bd-ib-never-filed", status="ready"),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_LEDGER
    assert "BeadsMappingError" in observation.detail


def test_a_record_carrying_no_status_is_malformed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sparse record is not evidence that the item stands anywhere.

    The clause puts malformed evidence in the unobservable set, and this is why:
    reading an absent key as a mismatch reaches a plausible answer by accident,
    and reading it as a match would satisfy every status result against a record
    that says nothing.
    """
    repository = _repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._plan_result_ledger.make_beads_client",
        lambda **_kwargs: _StatuslessClient(),
    )
    observation = observe_item_status(
        repository=repository,
        target=ItemStatusTarget(item_id=_ITEM_ID, status="ready"),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert "carries no readable status" in observation.detail


def test_an_exact_marker_is_satisfied_and_says_what_it_does_not_prove(
    tmp_path: Path,
) -> None:
    """The clause's narrowing rides on the SATISFIED observation itself.

    A satisfied observation is what a caller quotes onward, and this is the one
    kind whose satisfaction proves the least — so the limit travels with it rather
    than living only in the clause.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="active")
    make_beads_client(config=store_config(repo=repository.clone)).add_comment(
        issue_id=_ITEM_ID, body=f"handoff\n\n{_MARKER}\n"
    )
    observation = observe_item_comment(
        repository=repository,
        target=ItemCommentTarget(item_id=_ITEM_ID, marker=_MARKER),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.evidence == f"ledger comment position 1 on {_ITEM_ID}"
    assert MARKER_NARROWING in observation.detail


def test_the_comment_evidence_prefers_a_recorded_instant_over_a_position(
    tmp_path: Path,
) -> None:
    """A positional identity is the LAST resort, not the first.

    The clause asks for a ledger comment identity, so a comment that records when
    it was written is cited by that instant; a position only distinguishes two
    comments of the same item and says nothing about which write it was.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="active")
    client = make_beads_client(config=store_config(repo=repository.clone))
    client.seed_comment(issue_id=_ITEM_ID, text=f"{_MARKER}\n", created_at="2026-10-07T10:00:00Z")
    observation = observe_item_comment(
        repository=repository,
        target=ItemCommentTarget(item_id=_ITEM_ID, marker=_MARKER),
        now=_NOW,
    )
    assert observation is not None
    assert observation.evidence == f"ledger comment 2026-10-07T10:00:00Z on {_ITEM_ID}"


def test_a_marker_no_comment_carries_is_unsatisfied_and_counts_what_it_read(
    tmp_path: Path,
) -> None:
    """The scan walks every comment, so the control seeds two that do not match.

    The count is the evidence identity for this arm: there is no comment to cite,
    and "two comments were read and neither carried it" is a different claim from
    "the comments could not be read" — which is the next cycle's status.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="active")
    client = make_beads_client(config=store_config(repo=repository.clone))
    client.add_comment(issue_id=_ITEM_ID, body="one unrelated rider\n")
    client.add_comment(issue_id=_ITEM_ID, body="another unrelated rider\n")
    observation = observe_item_comment(
        repository=repository,
        target=ItemCommentTarget(item_id=_ITEM_ID, marker=_MARKER),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.evidence == f"2 ledger comment(s) read on {_ITEM_ID}"


def test_an_unreadable_connection_makes_the_comment_read_unobservable(
    tmp_path: Path,
) -> None:
    repository = _repo(tmp_path=tmp_path, prefix=None)
    observation = observe_item_comment(
        repository=repository,
        target=ItemCommentTarget(item_id=_ITEM_ID, marker=_MARKER),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.detail == UNRESOLVED_CONNECTION


def test_an_item_absent_from_the_tenant_makes_the_comment_read_unobservable(
    tmp_path: Path,
) -> None:
    """Zero comments READ and zero comments READABLE are different facts.

    The unsatisfied arm cites how many comments it read; this arm could read
    none, so reporting "no comment carries the marker" would be a negative about
    a population nobody enumerated.
    """
    repository = _repo(tmp_path=tmp_path)
    observation = observe_item_comment(
        repository=repository,
        target=ItemCommentTarget(item_id="bd-ib-never-filed", marker=_MARKER),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert "BeadsMappingError" in observation.detail
