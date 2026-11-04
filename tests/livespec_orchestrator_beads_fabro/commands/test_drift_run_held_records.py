"""The held-finding record's own edges: what cannot hold, and what cannot be read.

Three absences, each with a different consequence the pass depends on.

A repository that commits NO ANCHOR, or whose connection block resolves to no
tenant, CANNOT hold — and `record_held_finding` answers False rather than
raising or quietly succeeding. The pass reads that False as "this finding is
not disposed of", which stops the frontier at its merge. Both halves are
asserted because they are independent: a build checking only the anchor raises
from inside one finding's disposition and kills the whole pass over a question
that has a good answer.

A record whose PAYLOAD will not read as a held finding is SKIPPED rather than
blinding the read of every other hold on the same anchor. The anchor is a
shared ledger row carrying three record types and anything an older build left
there, so a reader that gave up on the first unparseable payload would report
zero holds on an anchor holding five.

And a DUPLICATE identity is reported ONCE. The record is append-only, so a
build that held one finding twice — or an operator replaying a pass against an
anchor an older build wrote — must not make the operator surface list it twice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._drift_run_findings import DriftFinding
from livespec_orchestrator_beads_fabro.commands._drift_run_held import (
    HELD_MARKER_PREFIX,
    held_findings,
    record_held_finding,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator

_ANCHOR = "bd-ib-anchor"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _finding(*, identity: str = "drift-aaaa", target: str | None = "## H") -> DriftFinding:
    return DriftFinding(
        merge="aaaaaaa1",
        kind="unstated",
        generalization_target=target,
        statement="a behaviour",
        rationale="because",
        identity=identity,
    )


def _seed_anchor() -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ANCHOR,
            type="task",
            status="backlog",
            title="anchor",
            description="d",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-01T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            blocked_reason=None,
            factory_safety=None,
            admission_policy=None,
            acceptance_policy=None,
            spec_commitment_hint=None,
        ),
    )


@pytest.mark.parametrize(
    ("case", "path", "anchor"),
    [
        ("no anchor is committed", _config(), None),
        ("the committed anchor is blank", _config(), "   "),
        ("no tenant connection resolves", None, _ANCHOR),
    ],
)
def test_a_repository_that_cannot_hold_says_so(
    case: str, path: StoreConfig | None, anchor: str | None
) -> None:
    assert record_held_finding(path=path, anchor=anchor, finding=_finding()) is False, case


def test_no_tenant_connection_reads_no_holds() -> None:
    assert held_findings(path=None, anchor=_ANCHOR) == ()


def test_an_absent_anchor_row_reads_no_holds() -> None:
    # The committed id names no live row: the read is fail-soft because it runs
    # inside the needs-attention composition, where raising would take the
    # whole snapshot down for one wrong config value.
    assert held_findings(path=_config(), anchor="bd-ib-nobody") == ()


def test_a_held_finding_round_trips_with_its_merge_and_target() -> None:
    _seed_anchor()

    assert record_held_finding(path=_config(), anchor=_ANCHOR, finding=_finding()) is True
    read_back = held_findings(path=_config(), anchor=_ANCHOR)

    assert [one.identity for one in read_back] == ["drift-aaaa"]
    assert read_back[0].merge == "aaaaaaa1"
    assert read_back[0].generalization_target == "## H"


def test_a_finding_held_with_no_target_round_trips_as_none() -> None:
    _seed_anchor()
    _ = record_held_finding(path=_config(), anchor=_ANCHOR, finding=_finding(target=None))

    assert held_findings(path=_config(), anchor=_ANCHOR)[0].generalization_target is None


@pytest.mark.parametrize(
    ("case", "payload"),
    [
        ("not JSON at all", "not json"),
        ("a JSON scalar", '"a string"'),
        ("no identity", '{"merge": "m", "kind": "unstated"}'),
        ("an identity of the wrong type", '{"identity": 1, "merge": "m", "kind": "unstated"}'),
        ("no merge", '{"identity": "drift-x", "kind": "unstated"}'),
        ("no kind", '{"identity": "drift-x", "merge": "m"}'),
    ],
)
def test_an_unreadable_record_is_skipped_and_the_rest_are_read(case: str, payload: str) -> None:
    _seed_anchor()
    client = make_beads_client(config=_config())
    client.add_comment(issue_id=_ANCHOR, body=HELD_MARKER_PREFIX + payload)
    client.add_comment(issue_id=_ANCHOR, body="an unrelated comment nobody wrote for this")
    _ = record_held_finding(path=_config(), anchor=_ANCHOR, finding=_finding())

    # The sound record is still read: a reader that gave up on the first
    # unparseable payload would report zero holds on an anchor holding one.
    assert [one.identity for one in held_findings(path=_config(), anchor=_ANCHOR)] == [
        "drift-aaaa"
    ], case


def test_one_identity_held_twice_is_reported_once() -> None:
    _seed_anchor()
    _ = record_held_finding(path=_config(), anchor=_ANCHOR, finding=_finding())
    _ = record_held_finding(path=_config(), anchor=_ANCHOR, finding=_finding())

    assert len(held_findings(path=_config(), anchor=_ANCHOR)) == 1
