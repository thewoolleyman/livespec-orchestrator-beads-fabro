"""Binding-aware selection of Proof of Done records.

The record, rather than a later attempt to reconstruct which factory run merged,
is the authority for a proof's work item, pull request and head.  This module
keeps that interpretation in one place so the evidence leg, pointer and parking
record cannot disagree about whether a comment counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_NOT_REPRODUCED,
    VERDICT_HOST_RECORDED,
    VERDICT_HOST_VERIFIED,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
    ProofRecord,
)

__all__: list[str] = [
    "BIND_VERDICT_BOUND",
    "BIND_VERDICT_BOUND_ELSEWHERE",
    "BIND_VERDICT_HUMAN_ATTESTED",
    "BIND_VERDICT_LEGACY_HOST",
    "BIND_VERDICT_LEGACY_MATCHED",
    "BIND_VERDICT_SUPERSEDED",
    "BIND_VERDICT_UNBINDABLE",
    "BoundRecord",
    "ProofRecordInventory",
    "proof_record_inventory",
]

BIND_VERDICT_HUMAN_ATTESTED = "human-attested"
BIND_VERDICT_SUPERSEDED = "superseded"
BIND_VERDICT_BOUND = "bound"
BIND_VERDICT_BOUND_ELSEWHERE = "bound-elsewhere"
BIND_VERDICT_LEGACY_HOST = "legacy-host"
BIND_VERDICT_LEGACY_MATCHED = "legacy-matched"
BIND_VERDICT_UNBINDABLE = "unbindable"

_BIND_PREFIX = "Binds:"
_SUPERSEDES_PREFIX = "Supersedes:"
_BINDING = re.compile(
    "".join(
        (
            r"^Binds: (?P<item>[^\s]+) — pull request #(?P<pr>[1-9][0-9]*) — ",
            r"head (?P<head>[0-9a-fA-F]{40,64})$",
        )
    )
)
_HOST_VERDICTS = frozenset(
    (VERDICT_HOST_RECORDED, VERDICT_HOST_VERIFIED, VERDICT_HOST_NOT_REPRODUCED)
)
_VERIFY_VERDICTS = frozenset((VERDICT_VERIFIED, VERDICT_NOT_REPRODUCED))


@dataclass(frozen=True, kw_only=True)
class _Binding:
    work_item_id: str
    pull_request: int
    head: str


@dataclass(frozen=True, kw_only=True)
class BoundRecord:
    """One record and its single v230 bind verdict."""

    record: ProofRecord
    verdict: str
    fault: str | None = None
    stale_head: bool = False

    @property
    def counts(self) -> bool:
        if self.verdict == BIND_VERDICT_HUMAN_ATTESTED:
            return True
        if self.record.verdict in _HOST_VERDICTS:
            return self.verdict in (BIND_VERDICT_BOUND, BIND_VERDICT_LEGACY_HOST)
        return self.verdict in (BIND_VERDICT_BOUND, BIND_VERDICT_LEGACY_MATCHED)


@dataclass(frozen=True, kw_only=True)
class ProofRecordInventory:
    """Every record and the subsets the acceptance pass may grade."""

    entries: tuple[BoundRecord, ...]

    @property
    def unbindable(self) -> tuple[BoundRecord, ...]:
        return tuple(one for one in self.entries if one.verdict == BIND_VERDICT_UNBINDABLE)

    @property
    def factory_records(self) -> tuple[BoundRecord, ...]:
        return tuple(
            one
            for one in self.entries
            if one.counts and one.record.verdict in _VERIFY_VERDICTS and not one.stale_head
        )

    @property
    def host_records(self) -> tuple[BoundRecord, ...]:
        return tuple(
            one for one in self.entries if one.counts and one.record.verdict in _HOST_VERDICTS
        )


def proof_record_inventory(
    *,
    records: tuple[ProofRecord, ...],
    work_item_id: str,
    pull_request: int,
    merged_head: str | None,
    dispatch_ids: tuple[str, ...],
) -> ProofRecordInventory:
    """Classify every record once, in pull-request order.

    Legacy matching intentionally receives every identifier attributed to every
    dispatch of this item.  It is a compatibility arm only; bound records never
    consult it, which is what removes the merging-run-resolution failure mode.
    """
    initial = tuple(
        _classify(
            record=record,
            work_item_id=work_item_id,
            pull_request=pull_request,
            dispatch_ids=dispatch_ids,
        )
        for record in records
    )
    superseded = _superseded_urls(entries=initial, pull_request=pull_request)
    return ProofRecordInventory(
        entries=tuple(
            _with_state(
                entry=entry,
                superseded=_is_superseded(url=entry.record.url, targets=superseded),
                merged_head=merged_head,
            )
            for entry in initial
        )
    )


def _classify(
    *,
    record: ProofRecord,
    work_item_id: str,
    pull_request: int,
    dispatch_ids: tuple[str, ...],
) -> BoundRecord:
    if record.verdict == VERDICT_HUMAN_ATTESTED:
        return BoundRecord(record=record, verdict=BIND_VERDICT_HUMAN_ATTESTED)
    binding, fault = _binding_in(body=record.body)
    if fault is not None:
        return BoundRecord(record=record, verdict=BIND_VERDICT_UNBINDABLE, fault=fault)
    if binding is not None:
        verdict = (
            BIND_VERDICT_BOUND
            if binding.work_item_id == work_item_id and binding.pull_request == pull_request
            else BIND_VERDICT_BOUND_ELSEWHERE
        )
        return BoundRecord(record=record, verdict=verdict)
    if record.verdict in _HOST_VERDICTS:
        return BoundRecord(record=record, verdict=BIND_VERDICT_LEGACY_HOST)
    if record.run_id in dispatch_ids:
        return BoundRecord(record=record, verdict=BIND_VERDICT_LEGACY_MATCHED)
    return BoundRecord(
        record=record,
        verdict=BIND_VERDICT_UNBINDABLE,
        fault="factory record has no binding and its run matches no dispatch of this item",
    )


def _binding_in(*, body: str) -> tuple[_Binding | None, str | None]:
    lines = body.splitlines()
    indexes = tuple(index for index, line in enumerate(lines) if line.startswith(_BIND_PREFIX))
    if not indexes:
        return None, None
    if len(indexes) != 1:
        return None, "record carries more than one Binds line"
    if indexes[0] != 1:
        return None, "Binds line is not immediately after the record header"
    match = _BINDING.fullmatch(lines[1])
    if match is None:
        return None, "Binds line is malformed or incomplete"
    return (
        _Binding(
            work_item_id=match.group("item"),
            pull_request=int(match.group("pr")),
            head=match.group("head").lower(),
        ),
        None,
    )


def _superseded_urls(*, entries: tuple[BoundRecord, ...], pull_request: int) -> frozenset[str]:
    targets: set[str] = set()
    for entry in entries:
        binding, fault = _binding_in(body=entry.record.body)
        if fault is not None or binding is None or binding.pull_request != pull_request:
            continue
        for line in entry.record.body.splitlines():
            if line.startswith(_SUPERSEDES_PREFIX):
                targets.add(line[len(_SUPERSEDES_PREFIX) :].strip())
    return frozenset(targets)


def _is_superseded(*, url: str, targets: frozenset[str]) -> bool:
    """Whether a correction names this record's full link or fixture identifier."""
    return url in targets or any(target.rsplit("/", maxsplit=1)[-1] == url for target in targets)


def _with_state(*, entry: BoundRecord, superseded: bool, merged_head: str | None) -> BoundRecord:
    if superseded:
        return BoundRecord(record=entry.record, verdict=BIND_VERDICT_SUPERSEDED)
    binding, _ = _binding_in(body=entry.record.body)
    stale = (
        entry.counts
        and entry.record.verdict in _VERIFY_VERDICTS
        and binding is not None
        and merged_head is not None
        and binding.head != merged_head.lower()
    )
    return BoundRecord(
        record=entry.record,
        verdict=entry.verdict,
        fault=entry.fault,
        stale_head=stale,
    )
