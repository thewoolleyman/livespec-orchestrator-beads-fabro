"""Scenario 123 — the ready ordering breaks equal-rank ties by ready-age.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 123 — The ready ordering breaks equal-rank ties by ready-age past
the bound`, and for the ranking-authority clause of
`SPECIFICATION/contracts.md` that heading realizes.

All four of the heading's gherkin scenarios are asserted by ONE ordering over
ONE seeded tenant, because they are four properties of a single ordering and
splitting them would let each pass against a key the others reject. The tenant
is seeded through the REAL store seam against the in-memory `FakeBeadsClient`,
so each item's `ready_since` is the durable instant the store itself writes on
a transition into `ready` — the same instant the `hygiene:ready-aging`
attention fact reads — rather than a value poked into the ordering by a stub.
No machine-local dispatch journal exists anywhere in this test.

Both ranked surfaces are driven through PRODUCTION entry points that resolve
the aging inputs themselves: `next.main` over the seeded tenant, and the
Dispatcher's own `ready_items`. Neither is handed a lookup by the test, which
is what makes "next and the Dispatcher agree" an observation rather than a
consequence of passing both the same argument.

The fixture is built so every assertion is DISCRIMINATING — each expectation
differs from what the pre-aging `(rank, id)` key would have produced:

- the aged item of the equal-rank pair carries the LEXICOGRAPHICALLY LATER id,
  so ordering it first cannot be the id tiebreak;
- the below-bound pair's older member carries the later id, so honoring age
  below the bound would swap them;
- the unknowable-instant item carries an EARLIER id than its aged sibling, so
  reading an unknown instant as "infinitely old" would put it first;
- the highest-`rank` item is the NEWEST one in the tenant, so a tiebreak that
  leaked across rank tiers would demote it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import next as next_command
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orchestrator-beads-fabro"
_PREFIX = "bd-ib"
_THRESHOLD_HOURS = 24

# The `_utc_now_iso` seam the store stamps `ready_since` through.
_STORE_CLOCK = "livespec_orchestrator_beads_fabro._store_mutations._utc_now_iso"

# The ordering the ratified clause requires over the seeded tenant. Read it
# against `_seeded_tenant` below: rank tier first, then the aged member of each
# tier, then the id tiebreak among everything the bound has not aged.
_EXPECTED_ORDER = [
    # `rank` stays primary: the newest item in the tenant, and it still leads.
    "bd-ib-tier0-newest",
    # Equal `rank`, and the aged member leads despite the later id.
    "bd-ib-tier1-b-aged",
    "bd-ib-tier1-a-newer",
    # Equal `rank`, neither past the bound: the id tiebreak holds, even though
    # `c` has been ready for less time than `d`.
    "bd-ib-tier2-c-newer",
    "bd-ib-tier2-d-older-but-unaged",
    # Equal `rank`: the aged item leads; the unknowable instant earns no age
    # advantage and keeps the id tiebreak against the newer item.
    "bd-ib-tier3-h-aged",
    "bd-ib-tier3-g-unknowable",
    "bd-ib-tier3-i-newer",
]


@dataclass(kw_only=True)
class _StoreClock:
    """The instant the store stamps onto the next `ready` transition it writes."""

    instant: str

    def now_iso(self) -> str:
        return self.instant


@pytest.fixture(autouse=True)
def _hermetic() -> Iterator[None]:
    """Drive the store onto the in-memory tenant, isolated per test."""
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario123_ready_aging_breaks_equal_rank_ties_and_both_surfaces_agree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Given ready items of equal rank whose durable ready instants differ,
    When `next` ranks the candidates and the Dispatcher composes its drain order,
    Then an item ready past dispatcher.ready_aging_threshold_hours leads its
    equal-rank siblings, an equal-rank pair below the bound keeps the id
    tiebreak, an item whose ready instant is unknowable keeps the id tiebreak
    with no age advantage, `rank` still decides across tiers,
    And the two surfaces produce the identical ordering."""
    repo = _seeded_tenant(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert next_command.main(argv=["--json", "--limit", "20", "--project-root", str(repo)]) == 0
    ranked_by_next = [
        candidate["work_item_ref"]
        for candidate in json.loads(capsys.readouterr().out)["candidates"]
    ]
    ranked_by_dispatcher = [item.id for item in ready_items(items=load_items(repo=repo), repo=repo)]

    assert ranked_by_next == _EXPECTED_ORDER
    assert ranked_by_dispatcher == _EXPECTED_ORDER


def _seeded_tenant(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Seed the eight ready items `_EXPECTED_ORDER` describes; return the repo root."""
    repo = _repo(tmp_path=tmp_path)
    clock = _StoreClock(instant=_hours_ago(hours=1))
    monkeypatch.setattr(_STORE_CLOCK, clock.now_iso)

    _seed(clock=clock, item_id="bd-ib-tier0-newest", rank="a0", hours_ready=0.25)
    _seed(clock=clock, item_id="bd-ib-tier1-a-newer", rank="a1", hours_ready=1)
    _seed(clock=clock, item_id="bd-ib-tier1-b-aged", rank="a1", hours_ready=100)
    _seed(clock=clock, item_id="bd-ib-tier2-c-newer", rank="a2", hours_ready=2)
    _seed(clock=clock, item_id="bd-ib-tier2-d-older-but-unaged", rank="a2", hours_ready=20)
    _seed(clock=clock, item_id="bd-ib-tier3-h-aged", rank="a3", hours_ready=200)
    _seed(clock=clock, item_id="bd-ib-tier3-i-newer", rank="a3", hours_ready=3)
    _seed_unknowable(item_id="bd-ib-tier3-g-unknowable", rank="a3")
    return repo


def _repo(*, tmp_path: Path) -> Path:
    """A repository root declaring the fake tenant and the aging bound."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_BLOCK: {
                    "connection": {
                        "tenant": _TENANT,
                        "prefix": _PREFIX,
                        "server_user": _TENANT,
                        "database": _TENANT,
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"ready_aging_threshold_hours": _THRESHOLD_HOURS},
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _seed(*, clock: _StoreClock, item_id: str, rank: str, hours_ready: float) -> None:
    """Write one `ready` item whose durable `ready_since` is `hours_ready` old."""
    clock.instant = _hours_ago(hours=hours_ready)
    append_work_item(path=_config(), item=_item(item_id=item_id, rank=rank))


def _seed_unknowable(*, item_id: str, rank: str) -> None:
    """Write a `ready` item carrying NO durable instant.

    Landed as a legacy row would be — written `backlog` through the store seam,
    then moved to `ready` with metadata that never gained a `ready_since` key —
    so "unknowable" is the absence the projection actually reports rather than a
    sentinel this test invented.
    """
    append_work_item(path=_config(), item=_item(item_id=item_id, rank=rank, status="backlog"))
    _fake().update_issue(issue_id=item_id, status="ready", metadata={"rank": rank})


def _item(*, item_id: str, rank: str, status: str = "ready") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=item_id,
        description=item_id,
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _hours_ago(*, hours: float) -> str:
    moment = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client
