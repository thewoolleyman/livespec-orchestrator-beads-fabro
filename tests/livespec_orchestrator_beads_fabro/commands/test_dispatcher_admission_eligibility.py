"""The eligibility filter's refusal ORDER, which its own docstring is about.

`_dispatcher_admission_eligibility` documents its refusal sequence as
"cheapest and least item-specific first", and that ordering is a cost and
blast-radius claim rather than a stylistic one: the two factory-wide
conditions are facts about the factory that refuse every row identically,
while the adopted assertion-count ceiling reads THIS row's ledger metadata
and, on an above-ceiling row carrying no valid `size_justification`, MUTATES
it -- `route_factory_size_decomposition` moves the row to `backlog` and
appends a ledger comment.

So a candidate wave arriving while a success-critical ACP chain is exhausted,
or while a provider ceiling is still held, must not spend one ledger
round-trip or perform one lifecycle mutation per candidate on rows the next
condition was about to refuse anyway. Each case below counts the store reads
rather than inferring them, because an item that ends up refused looks the
same from the outcome whichever condition refused it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-oversized"
_SIZE_REFUSAL_STAGE = "size-decomposition"
_EXHAUSTION_REFUSAL_STAGE = "provider-exhaustion"
_CONFIGURATION_REFUSAL_STAGE = "configuration"


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _item(*, assertion_count: int = 3) -> WorkItem:
    bullets = "\n".join(
        f"- The product satisfies assertion {index}." for index in range(assertion_count)
    )
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="ready",
        title="Oversized candidate",
        description=f"## Definition of Done\n\n{bullets}\n",
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _write_repo_config(*, repo: Path, ceiling: object) -> None:
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"adopted_assertion_count_ceiling": ceiling},
                }
            }
        ),
        encoding="utf-8",
    )


def _oversized_fixture(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ceiling: object = 1
) -> tuple[Path, StoreConfig, WorkItem, JournalFile, list[Path]]:
    """An above-ceiling, unjustified `ready` row plus a counted store seam."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo_config(repo=repo, ceiling=ceiling)
    config = _config(repo_root=repo)
    item = _item()
    append_work_item(path=config, item=item)

    reads: list[Path] = []
    eligibility = import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility"
    )

    def _counted_store_config(*, repo: Path) -> StoreConfig:
        reads.append(repo)
        return _config(repo_root=repo)

    monkeypatch.setattr(eligibility, "store_config", _counted_store_config)
    return repo, config, item, JournalFile(path=repo / "journal.jsonl"), reads


def _exhausted() -> AcpPreflightVerdict:
    return AcpPreflightVerdict(
        fallback_enabled=True, success_critical=("implement",), exhausted=("implement",)
    )


def _viable() -> AcpPreflightVerdict:
    return AcpPreflightVerdict(fallback_enabled=True, success_critical=("implement",))


def _seed_nothing(*, journal: JournalFile) -> None:
    """The exhausted-chain leg needs no journal state to refuse."""
    _ = journal


def _seed_provider_exhaustion(*, journal: JournalFile) -> None:
    journal.append(
        record={
            "stage": "provider-exhaustion-observed",
            "work_item_id": "bd-other",
            "provider": "anthropic",
            "governing_condition": "weekly allowance",
            "record_expires_at": "2099-01-01T00:00:00Z",
        }
    )


def _status_of(*, config: StoreConfig) -> str:
    return materialize_work_items(records=read_work_items(path=config))[_ITEM_ID].status


def _filter(
    *, repo: Path, preflight: AcpPreflightVerdict, item: WorkItem, journal: JournalFile
) -> list[DispatchOutcome]:
    admittable, refused = filter_eligible_candidates(
        repo=repo, preflight=preflight, candidates=[item], journal=journal
    )
    assert admittable == []
    return refused


@pytest.mark.parametrize(
    ("seed", "preflight", "expected_stage"),
    [
        pytest.param(
            _seed_nothing,
            _exhausted,
            ACP_PREFLIGHT_REFUSAL_STAGE,
            id="exhausted-acp-chain",
        ),
        pytest.param(
            _seed_provider_exhaustion,
            _viable,
            _EXHAUSTION_REFUSAL_STAGE,
            id="held-provider-ceiling",
        ),
    ],
)
def test_a_factory_wide_refusal_precedes_the_item_specific_size_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seed: Callable[..., None],
    preflight: Callable[[], AcpPreflightVerdict],
    expected_stage: str,
) -> None:
    """Neither factory-wide refusal may spend a ledger read or a mutation."""
    repo, config, item, journal, reads = _oversized_fixture(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    seed(journal=journal)

    refused = _filter(repo=repo, preflight=preflight(), item=item, journal=journal)

    assert [outcome.stage for outcome in refused] == [expected_stage]
    # The ledger was never asked about this row, so it cannot have been moved.
    assert reads == []
    assert _status_of(config=config) == "ready"


def test_the_size_gate_still_refuses_once_no_factory_wide_condition_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the reordered gate is REACHED, not merely moved out of the way."""
    repo, config, item, journal, reads = _oversized_fixture(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    refused = _filter(repo=repo, preflight=_viable(), item=item, journal=journal)

    assert [outcome.stage for outcome in refused] == [_SIZE_REFUSAL_STAGE]
    assert reads == [repo]
    assert _status_of(config=config) == "backlog"


def test_an_unreadable_adopted_ceiling_refuses_ahead_of_every_other_condition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Committed configuration is the least item-specific condition of all."""
    repo, config, item, journal, reads = _oversized_fixture(
        tmp_path=tmp_path, monkeypatch=monkeypatch, ceiling=0
    )
    _seed_provider_exhaustion(journal=journal)

    refused = _filter(repo=repo, preflight=_exhausted(), item=item, journal=journal)

    assert [outcome.stage for outcome in refused] == [_CONFIGURATION_REFUSAL_STAGE]
    assert reads == []
    assert _status_of(config=config) == "ready"
