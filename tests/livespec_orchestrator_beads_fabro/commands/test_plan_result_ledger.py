"""Tests for the two ledger adapters: item status and the exact item marker.

The hermetic in-memory tenant is the ledger here (the autouse fixture in this
tree's conftest), so every read goes through the production client seam.

ONE SEAM IS STOOD IN, FOR ONE GUARD. A beads record is `omitempty`-sparse, so a
record carrying no `status` key is a real shape the adapter has to answer for, and
the in-memory tenant always writes one. That guard is therefore exercised through
a stand-in client; every other case drives the real fake.

THE TWO MARKER-PLACEMENT CASES ARE EACH OTHER'S CONTROL, and neither is worth
anything alone. A reader that matched NOTHING would satisfy the echo case while
making every plan obligation permanently unsatisfiable, and a reader that matched
the marker anywhere in a comment satisfies the record case while reporting a
plan's own bookkeeping as the record it is still waiting for. The echo fixtures
are rendered through the PRODUCTION renderers — `progress_event_body` inside
`plan_comment_body`, and `plan_comment_body` for the scope event — so the text
under test is the text a sanctioned pointer write actually leaves on the epic,
and each case asserts that its fixtures DO contain the marker before asserting
what the reader makes of them. Without that control, a fixture whose payload had
stopped carrying the marker would report unsatisfied for the wrong reason and
read as a passing test of a reader that no longer discriminated anything.
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
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    AuthorityState,
    TransitionPayload,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    PLAN_PROGRESS_PREFIX,
    progress_event_body,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
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
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    plan_comment_body,
)

_ITEM_ID = "bd-ib-ledger"
_NOW = "2026-10-08T12:00:00Z"
_MARKER = "relay-delivery: delivered"
# The marker a plan's own proof obligation names, and the first line of the
# record that satisfies it. It is the production constant rather than a literal
# because the whole question here is whether the reader can tell that record
# apart from the plan's bookkeeping about it.
_PLAN_MARKER = PLAN_PROOF_RECORD_TITLE
_AUTHOR = "plan-session"
# The two chain records one echoed transition links, named here rather than
# inline because a `*_token_id` keyword taking a string literal reads to ruff's
# hardcoded-credential rule as a password.
_PRIOR_CHAIN_RECORD = "chain-record-a"
_NEXT_CHAIN_RECORD = "chain-record-b"


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


def _progress_event_echo(*, marker: str) -> str:
    """The comment EVERY sanctioned pointer write leaves on the epic.

    Rendered through the production renderers, so the marker reaches the body
    exactly as it does in production: serialized inside the obligation's own
    `required_result`, in a comment whose first line is the event prefix.
    """
    return plan_comment_body(
        prefix=PLAN_PROGRESS_PREFIX,
        author=_AUTHOR,
        now=_NOW,
        body=progress_event_body(
            payload=TransitionPayload(
                operation_id="op-echo",
                prior_epoch=1,
                new_epoch=2,
                prior_token_id=_PRIOR_CHAIN_RECORD,
                next_token_id=_NEXT_CHAIN_RECORD,
                event_kind="handoff",
                authority=AuthorityState(
                    required_result={
                        "repo": "repo",
                        "item_comment": {"item_id": _ITEM_ID, "marker": marker},
                    },
                    original_deadline="2099-10-10T12:00:00Z",
                    max_handoffs=4,
                    consumed_handoffs=1,
                ),
            ),
            now=_NOW,
        ),
    )


def _scope_event_quoting(*, marker: str) -> str:
    """A scope event whose PROSE names the marker, as a real one on a plan does."""
    return plan_comment_body(
        prefix=PLAN_SCOPE_PREFIX,
        author=_AUTHOR,
        now=_NOW,
        body=f"The plan still owes its {marker} record before the review is commissioned.",
    )


def _proof_record(*, marker: str) -> str:
    """A plan Proof of Done record, whose first line is the ratified header."""
    return f"{marker} — captured — session plan-session — {_NOW}\n\n## Assertion 1\n"


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


def test_a_done_target_is_satisfied_by_the_beads_native_closed_status(
    tmp_path: Path,
) -> None:
    """The lifecycle terminal name reaches the status the store actually holds.

    The work-item beads-issue mapping of `SPECIFICATION/contracts.md` maps
    lifecycle `done` onto the beads-native `closed` through the adapter, and an
    obligation is written in the LIFECYCLE vocabulary — so a reader comparing the
    target's spelling to the stored one by string equality can never satisfy a
    correctly written `done` obligation, however long the item has been closed.

    The evidence still names the status the ledger STORES, because that is the
    field the reader observed; the mapping is how the two are compared, not a
    rewriting of what was read.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="closed")
    observation = observe_item_status(
        repository=repository,
        target=ItemStatusTarget(item_id=_ITEM_ID, status="done"),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.source == SOURCE_LEDGER
    assert observation.evidence == f"ledger record {_ITEM_ID} at status closed"


def test_either_status_vocabulary_reaches_one_verdict_for_one_closed_item(
    tmp_path: Path,
) -> None:
    """A `closed` target and a `done` target are one obligation, read one way.

    The two vocabularies are both live in this tenant: `_plan_resume_advance`
    derives its own obligations with the beads-native `closed` literal, while a
    hand-authored plan obligation names the lifecycle `done`. The two readings are
    asserted EQUAL rather than each asserted satisfied, which is the control a
    per-vocabulary special case would fail: a reader that satisfied one spelling
    alone still discharges half the obligations this plan store holds.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="closed")
    readings = tuple(
        observe_item_status(
            repository=repository,
            target=ItemStatusTarget(item_id=_ITEM_ID, status=spelling),
            now=_NOW,
        )
        for spelling in ("done", "closed")
    )
    assert {one.status for one in readings} == {OBSERVATION_SATISFIED}
    assert {one.evidence for one in readings} == {f"ledger record {_ITEM_ID} at status closed"}


@pytest.mark.parametrize("stored", ["active", "acceptance"])
def test_a_done_target_is_unsatisfied_for_an_item_stored_anywhere_else(
    tmp_path: Path, stored: str
) -> None:
    """The control on the mapping: it maps ONE name and satisfies nothing else.

    A reader repaired by satisfying every `done` obligation outright would pass
    both cases above while discharging every plan obligation in the tenant the
    instant it was written. This arm is the confident negative that forbids it,
    and it names the STORED status so an operator reading the refusal is told
    where the item actually stands rather than only that it is not closed.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status=stored)
    observation = observe_item_status(
        repository=repository,
        target=ItemStatusTarget(item_id=_ITEM_ID, status="done"),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.source == SOURCE_LEDGER
    assert observation.evidence == f"ledger record {_ITEM_ID} at status {stored}"
    assert stored in observation.detail


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

    The comment OPENS with the marker, because that is what the reader counts as
    a record of the requested kind; the case below carries that placement rule.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="active")
    make_beads_client(config=store_config(repo=repository.clone)).add_comment(
        issue_id=_ITEM_ID, body=f"{_MARKER}\n\nthe delivery's own prose.\n"
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


def test_a_plan_event_echoing_the_marker_in_its_own_body_is_not_the_record(
    tmp_path: Path,
) -> None:
    """A plan's bookkeeping about an obligation cannot satisfy that obligation.

    Every sanctioned pointer write appends a `plan-progress-event` whose payload
    serializes the obligation's own `required_result`, marker included, so a
    reader scanning whole comment bodies satisfies an `item_comment` obligation
    the moment it is RECORDED — and a plan then skips the very step it is waiting
    for. A scope event quoting the marker in prose does the same.

    The first assertion is the control: both fixtures DO carry the marker, so the
    reader had something to find and the unsatisfied reading is a judgement about
    PLACEMENT rather than a fixture that stopped mentioning it.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="active")
    echo = _progress_event_echo(marker=_PLAN_MARKER)
    scope = _scope_event_quoting(marker=_PLAN_MARKER)
    assert all(_PLAN_MARKER in body for body in (echo, scope))
    client = make_beads_client(config=store_config(repo=repository.clone))
    client.add_comment(issue_id=_ITEM_ID, body=echo)
    client.add_comment(issue_id=_ITEM_ID, body=scope)

    observation = observe_item_comment(
        repository=repository,
        target=ItemCommentTarget(item_id=_ITEM_ID, marker=_PLAN_MARKER),
        now=_NOW,
    )

    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.source == SOURCE_LEDGER
    assert observation.evidence == f"2 ledger comment(s) read on {_ITEM_ID}"
    assert _PLAN_MARKER in observation.detail


def test_a_comment_opening_with_the_marker_is_the_record_the_echo_is_not(
    tmp_path: Path,
) -> None:
    """A record header satisfies the obligation, and is cited past the echo.

    The POSITIVE control for the case above, and the reason that case is not
    satisfied by a reader that matches nothing at all. The echo is seeded FIRST,
    so the cited evidence names the record's own position rather than the earlier
    comment's: a reader that stopped at the echo would report satisfied here too,
    and only the position tells the two apart.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed(repository=repository, status="active")
    client = make_beads_client(config=store_config(repo=repository.clone))
    client.add_comment(issue_id=_ITEM_ID, body=_progress_event_echo(marker=_PLAN_MARKER))
    client.add_comment(issue_id=_ITEM_ID, body=_proof_record(marker=_PLAN_MARKER))

    observation = observe_item_comment(
        repository=repository,
        target=ItemCommentTarget(item_id=_ITEM_ID, marker=_PLAN_MARKER),
        now=_NOW,
    )

    assert observation.status == OBSERVATION_SATISFIED
    assert observation.evidence == f"ledger comment position 2 on {_ITEM_ID}"
    assert MARKER_NARROWING in observation.detail


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
