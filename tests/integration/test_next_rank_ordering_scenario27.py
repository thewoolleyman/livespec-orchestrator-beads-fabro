"""Scenario 27 — `next` ranks ready items by the rank ordering authority.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 27 — next ranks ready items by rank`, whose two gherkin `Then`
clauses are the two cases below: ready candidates come back in `rank` order,
and equal-`rank` candidates break their tie by `id` lexicographic order.

The tenant is seeded through the REAL store seam against the in-memory
`FakeBeadsClient` — the same hermetic backend the rest of this directory
drives — and the ordering is read off `next.main`'s own `--json` envelope, so
what is asserted is the candidate list an operator receives rather than the
return value of the sort key the wrapper happens to compose. Nothing is
stubbed: no lookup, clock or ordering input is handed in by this test.

Each case is built so its expectation is DISCRIMINATING — it differs from what
every other ordering available over the same fixture would produce:

- the rank-order case gives the `a0` item the lexicographically LAST id and
  the `a2` item the lexicographically FIRST, so the expected order is the
  exact REVERSE of the `id` ordering, and seeds them `a2`, `a0`, `a1` so it is
  not insertion order either;
- the tie case seeds the lexicographically LATER id FIRST, so the expected
  order is neither insertion order nor — because the earlier-seeded row also
  carries the OLDER durable `ready_since` — the oldest-ready-first order the
  aging tiebreak would impose had either row aged past the bound. Neither has:
  both are seeded within the same pass, far inside the 24-hour bound the
  repository fixture declares, which is what keeps `rank` and `id` the only
  live components of the key. The aging tier itself is bound by
  `tests/integration/test_ready_aging_tiebreak_scenario123.py`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import next as next_command
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orchestrator-beads-fabro"
_PREFIX = "bd-ib"
# Far enough above the seeding pass that no row in either fixture is aged, so
# the aging tier is constant and `(rank, id)` is the whole live ordering.
_THRESHOLD_HOURS = 24
# The heading every seeded item's Definition of Done reference names; written
# into the fixture repository's own spec tree by `_repo` below.
_SPEC_HEADING = "## Effective acceptance criteria"


@pytest.fixture(autouse=True)
def _hermetic() -> Iterator[None]:
    """Drive the store onto the in-memory tenant, isolated per case."""
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario27_next_returns_ready_candidates_in_rank_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Given ready items with ranks "a2", "a0", "a1",
    When `next` is run,
    Then the candidates are returned in the order ranked "a0", "a1", "a2"."""
    repo = _repo(tmp_path=tmp_path)
    # Seeded in the gherkin's own order, and id-ordered against the expectation:
    # `aaa` holds `a2` and `ccc` holds `a0`, so rank order is the reverse of id
    # order and neither insertion order nor `id` can produce the assertion below.
    _seed(item_id="bd-ib-aaa", rank="a2")
    _seed(item_id="bd-ib-ccc", rank="a0")
    _seed(item_id="bd-ib-bbb", rank="a1")

    ranked = _ranked_candidates(repo=repo, capsys=capsys)

    assert [candidate["work_item_ref"] for candidate in ranked] == [
        "bd-ib-ccc",
        "bd-ib-bbb",
        "bd-ib-aaa",
    ]
    assert [candidate["rank"] for candidate in ranked] == ["a0", "a1", "a2"]


def test_scenario27_equal_rank_candidates_break_ties_by_id_lexicographic_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Given two ready items of equal rank,
    When `next` is run,
    Then ties are broken by id lexicographic order."""
    repo = _repo(tmp_path=tmp_path)
    # The lexicographically LATER id is seeded FIRST, so it is both the earlier
    # insertion and the older durable `ready_since`; the expectation below
    # therefore fails under either of those orderings.
    _seed(item_id="bd-ib-tie-b", rank="a0")
    _seed(item_id="bd-ib-tie-a", rank="a0")

    ranked = _ranked_candidates(repo=repo, capsys=capsys)

    assert [candidate["work_item_ref"] for candidate in ranked] == [
        "bd-ib-tie-a",
        "bd-ib-tie-b",
    ]
    assert [candidate["rank"] for candidate in ranked] == ["a0", "a0"]


def _ranked_candidates(
    *,
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> list[dict[str, object]]:
    """Run `next` over the seeded tenant and return its full candidate list.

    `--limit` is set well above the fixture size so the slice is the whole
    ranked list: a default-limited read would assert an ordering over a prefix
    and pass against a key that only agrees on the first few rows.
    """
    assert next_command.main(argv=["--json", "--limit", "20", "--project-root", str(repo)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    candidates: list[dict[str, object]] = envelope["candidates"]
    return candidates


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
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _seed(*, item_id: str, rank: str) -> None:
    """File one `ready` item through the real store seam."""
    append_work_item(path=_config(), item=_item(item_id=item_id, rank=rank))


def _item(*, item_id: str, rank: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title=item_id,
        description=_definition_of_done(item_id=item_id),
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


def _definition_of_done(*, item_id: str) -> str:
    """A conforming Definition of Done, so the row is a DISPATCH candidate.

    `next` applies the shared acceptance-eligibility decision as step 1 of the
    ranking algorithm, so an item with no section is absent from the ranked
    list entirely — and an ordering assertion over an empty list asserts
    nothing. The section is fixture here; the decision itself is bound by
    `tests/livespec_orchestrator_beads_fabro/commands/test_acceptance_eligibility_candidate_wiring.py`.
    """
    return (
        "## Definition of Done\n"
        "\n"
        f"- The ranked order places {item_id} where the rank authority requires.\n"
        "\n"
        f"References: {_SPEC_HEADING}\n"
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
