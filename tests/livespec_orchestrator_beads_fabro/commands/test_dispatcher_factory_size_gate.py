"""Dispatch-scoped audit tests for the adopted factory-size ceiling."""

from __future__ import annotations

from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_admission import (
    record_factory_size_admission_decision,
    size_justified_at_admission,
)


@dataclass(frozen=True, kw_only=True)
class _Item:
    id: str


@dataclass(frozen=True, kw_only=True)
class _Decision:
    adopted_ceiling: int | None
    assertion_count: int
    size_justified: bool


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _size_justified(*, records: tuple[dict[str, object], ...], work_item_id: str) -> bool | None:
    """Call the recovered WIP's existing two-argument reader API."""
    return size_justified_at_admission(records=records, work_item_id=work_item_id)


def test_size_justification_is_attributed_to_the_exact_dispatch() -> None:
    """Retries and interleaved items cannot inherit another admission decision."""
    journal = _Journal()
    first = _Item(id="bd-first")
    second = _Item(id="bd-second")

    record_factory_size_admission_decision(
        journal=journal,
        item=first,
        decision=_Decision(
            adopted_ceiling=2,
            assertion_count=3,
            size_justified=True,
        ),
    )
    first_admission = _size_justified(
        records=tuple(journal.records),
        work_item_id=first.id,
    )
    record_factory_size_admission_decision(
        journal=journal,
        item=second,
        decision=_Decision(
            adopted_ceiling=None,
            assertion_count=3,
            size_justified=False,
        ),
    )
    record_factory_size_admission_decision(
        journal=journal,
        item=first,
        decision=_Decision(
            adopted_ceiling=None,
            assertion_count=3,
            size_justified=False,
        ),
    )

    records = tuple(journal.records)
    assert first_admission is True
    assert (
        _size_justified(
            records=records,
            work_item_id=first.id,
        )
        is False
    )
    assert (
        _size_justified(
            records=records,
            work_item_id=second.id,
        )
        is False
    )
