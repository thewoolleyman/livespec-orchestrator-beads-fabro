"""Scenario 126 — adoption of a beads-native row assigns a status AND a real rank.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 126 — Ledger normalization adopts a beads-native `open` row and
assigns it a real rank`, and for the work-item beads-issue mapping clause it
realizes in `SPECIFICATION/contracts.md` — the one titled "Adoption of a row a
non-lifecycle writer left `open` assigns it a real rank".

ALL FIVE of the heading's gherkin scenarios are asserted over ONE seeded tenant
run through ALL FOUR cadences, because the fifth scenario's claim — that every
cadence adopts the same row identically — is only meaningful if the other four
are graded against what each cadence actually produced. Splitting them would
let a per-cadence divergence pass in whichever leg happened to be measured.

THE FOUR CADENCES ARE DRIVEN AS PRODUCTION ENTRY POINTS. Each leg is a real
`dispatcher.main(argv=[...])` invocation over the real store/client seam against
the in-memory `FakeBeadsClient`; nothing about normalization is stood in, and no
factory run is launched because no leg reaches a dispatchable target. The
single-dispatch leg names an item id the tenant does not hold: it refuses at
target selection, which is AFTER normalization, so the tenant state is what the
cadence wrote before refusing. That refusal is not incidental to the
measurement — if any leg died BEFORE normalization the adoption assertions
below would fail, so the tenant state is itself the discriminator that each
cadence reached the normalizer.

THE FIXTURE IS SEEDED AS A NON-LIFECYCLE WRITER LEAVES IT. The three adoptable
rows are written through the client's own `create_issue`, which lands beads
`open` with exactly the metadata it is handed — the shape a raw `bd create`
outside the store's 2-step path produces — so "carries no real rank" is the
absence the adapter really reports rather than a sentinel poked in by the test.

EVERY ASSERTION CARRIES A CONTROL THE ADOPTION MUST LEAVE ALONE, because a
normalization that re-keyed the whole tenant would satisfy "the adopted row has
a real rank" just as well:

- `_ANCHOR_ID` is a live, already-ranked row: it fixes the bottom of the live
  order at `_ANCHOR_RANK`, and it must still carry that key afterwards.
- `_OPEN_RANKED_ID` is adopted AND already ranked, which is the pair the third
  gherkin scenario turns on — its status moves and its key does not.
- `_CLOSED_ID` is a `done` row carrying a key that sorts after every live one.
  It is the discriminator for "bottom of the LIVE order": were `done` rows part
  of the bottom, every assigned key would sort after `_CLOSED_RANK` instead of
  before it, and the run would still look like a successful adoption.
- `_PARKED_ID` is `deferred` — parked, never auto-remapped — and it is the one
  row that must come out still carrying the bottom-sentinel.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL

_TENANT = "livespec-impl-beads"
_PREFIX = "bd-ib"

_ANCHOR_ID = "bd-ib-anchor-backlog"
_OPEN_RANKED_ID = "bd-ib-open-already-ranked"
_OPEN_RANKLESS_ID = "bd-ib-open-rankless"
_CLAIM_RANKLESS_ID = "bd-ib-raw-claim-rankless"
_PARKED_ID = "bd-ib-parked-deferred"
_CLOSED_ID = "bd-ib-closed-tail"

# The two real keys the fixture pins. `_OPEN_RANKED_RANK` is the greatest key
# any LIVE row holds, so it is the bottom a fresh insert must land after;
# `_CLOSED_RANK` sorts after it but belongs to a `done` row, so every assigned
# key must land BEFORE it.
_ANCHOR_RANK = "a1"
_OPEN_RANKED_RANK = "a5"
_CLOSED_RANK = "zz"

# An id the tenant does not hold, so the single-dispatch cadence refuses at
# target selection rather than launching anything.
_ABSENT_ID = "bd-ib-not-in-this-tenant"

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)

_Cadence = Callable[[Path], None]


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("ledger-adoption-rank")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:ledger-adoption-rank")
    for topic in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(topic, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario126_every_cadence_adopts_the_native_rows_onto_a_status_and_a_real_rank(
    tmp_path: Path,
) -> None:
    """Given a tenant holding rows a non-lifecycle writer left `open`,
    `in_progress` and `deferred`, some carrying no real rank,
    When the dispatch loop, the single-dispatch path, the standalone
    `ledger-normalize` CLI or the pre-push `ledger-normalize --gate` mode runs
    normalization over it,
    Then a rank-less `open` row is adopted into `backlog` and assigned a real,
    non-sentinel rank at the bottom of the LIVE order, an `in_progress` row is
    adopted into `active`, an already-ranked `open` row keeps its key, a
    `deferred` row is left untouched and unranked, no other row is re-keyed,
    And every cadence produces the identical outcome."""
    by_cadence = {
        name: _adopted_by(cadence=cadence, root=tmp_path / name)
        for name, cadence in _CADENCES.items()
    }

    # Gherkin 5 — every cadence adopts the same rows identically. Asserted
    # FIRST so the four assertions below grade one agreed outcome rather than
    # whichever leg the reader assumes.
    reference = by_cadence["ledger-normalize"]
    assert by_cadence == dict.fromkeys(_CADENCES, reference)

    # Gherkin 1 — the rank-less `open` row is adopted into `backlog` AND ranked.
    open_status, open_rank = reference[_OPEN_RANKLESS_ID]
    assert open_status == "backlog"
    assert open_rank != BOTTOM_SENTINEL

    # Gherkin 2 — the raw claim is adopted into `active`, and it too is ranked.
    claim_status, claim_rank = reference[_CLAIM_RANKLESS_ID]
    assert claim_status == "active"
    assert claim_rank != BOTTOM_SENTINEL

    # Each assigned key is a single BOTTOM-OF-THE-LIVE-ORDER insert: it sorts
    # after every real key a live row held, and before the `done` row's key —
    # which is what says the `done` row was not taken for the live bottom. The
    # two are distinct, so the second insert chained off the first rather than
    # colliding with it.
    assert _OPEN_RANKED_RANK < open_rank < _CLOSED_RANK
    assert _OPEN_RANKED_RANK < claim_rank < _CLOSED_RANK
    assert open_rank != claim_rank

    # Gherkin 3 — an already-ranked adopted row keeps its key, and Gherkin 4 —
    # the parked row is untouched and stays unranked. The two untouched
    # controls prove the inserts above were single inserts, not a rebalance.
    assert reference[_OPEN_RANKED_ID] == ("backlog", _OPEN_RANKED_RANK)
    assert reference[_PARKED_ID] == ("deferred", BOTTOM_SENTINEL)
    assert reference[_ANCHOR_ID] == ("backlog", _ANCHOR_RANK)
    assert reference[_CLOSED_ID] == ("done", _CLOSED_RANK)


def _adopted_by(*, cadence: _Cadence, root: Path) -> dict[str, tuple[str, str]]:
    """Seed a fresh tenant, run one cadence over it, and read every row back."""
    reset_fake_singleton()
    repo = _repo(root=root)
    _seed()
    cadence(repo)
    materialized = materialize_work_items(records=read_work_items(path=_config()))
    return {item.id: (str(item.status), item.rank) for item in materialized.values()}


def _repo(*, root: Path) -> Path:
    """A repository root declaring the fake tenant; one per cadence leg."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": _PREFIX}}}),
        encoding="utf-8",
    )
    return repo


def _seed() -> None:
    """Seed the six rows the module docstring describes, in a fixed order.

    The order is load-bearing for the cross-cadence comparison: the two
    rank-less adoptions chain their fresh keys off each other, so a stable seed
    order is what makes "every cadence produced the identical rank" a claim
    about the cadences rather than about the iteration.
    """
    append_work_item(path=_config(), item=_item(item_id=_ANCHOR_ID, rank=_ANCHOR_RANK))
    _raw_create(item_id=_OPEN_RANKED_ID, metadata={"rank": _OPEN_RANKED_RANK})
    _raw_create(item_id=_OPEN_RANKLESS_ID, metadata={})
    _raw_create(item_id=_CLAIM_RANKLESS_ID, metadata={}, native_status="in_progress")
    _raw_create(item_id=_PARKED_ID, metadata={}, native_status="deferred")
    append_work_item(
        path=_config(),
        item=_item(item_id=_CLOSED_ID, rank=_CLOSED_RANK, status="done", resolution="completed"),
    )


def _raw_create(
    *,
    item_id: str,
    metadata: dict[str, str],
    native_status: str | None = None,
) -> None:
    """Write one row the way a writer that performs no second step leaves it.

    `create_issue` lands beads `open` carrying exactly the metadata it is
    handed, so a `{}` metadata row genuinely holds no `rank` key and reads back
    through the adapter's bottom-sentinel. `native_status` then stamps the other
    two non-lifecycle statuses the way a raw `bd --claim` or a `bd create
    --status deferred` would, leaving the metadata alone.
    """
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="task",
            title=item_id,
            description=item_id,
            assignee=None,
            created_at="2026-09-09T00:00:00Z",
            labels=["origin:freeform"],
            metadata=dict(metadata),
        )
    )
    if native_status is not None:
        client.update_issue(issue_id=item_id, status=native_status)


def _item(
    *,
    item_id: str,
    rank: str,
    status: str = "backlog",
    resolution: str | None = None,
) -> WorkItem:
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
        captured_at="2026-09-09T00:00:00Z",
        resolution=resolution,  # type: ignore[arg-type]
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _loop(repo: Path) -> None:
    _ = main(argv=["loop", "--repo", str(repo), "--budget", "1"])


def _single_dispatch(repo: Path) -> None:
    _ = main(argv=["dispatch", "--repo", str(repo), "--item", _ABSENT_ID])


def _ledger_normalize(repo: Path) -> None:
    _ = main(argv=["ledger-normalize", "--project-root", str(repo)])


def _pre_push_gate(repo: Path) -> None:
    _ = main(argv=["ledger-normalize", "--project-root", str(repo), "--gate"])


# The four cadences the ratified clause names, each a production entry point.
_CADENCES: dict[str, _Cadence] = {
    "loop": _loop,
    "dispatch": _single_dispatch,
    "ledger-normalize": _ledger_normalize,
    "ledger-normalize-gate": _pre_push_gate,
}
