"""The dispatch CLAIM stamp: which dispatch, on which host, holds an item.

`_store_dispatch_factory` already records WHICH factory an item is pinned to
and WHICH run id it last learned. Neither answers the question the claim half
of run reconciliation asks: *whose* dispatch holds this `active` row, and on
which machine is that dispatcher's liveness observable at all. Ledger writers
may run on any number of hosts that share nothing but the Beads server
(`.ai/ledger-writers-are-multi-host.md`), so a reconciler can observe only its
OWN host's processes — and a claim it cannot attribute to itself is one it must
leave alone.

So the stamp is its own metadata key carrying all four facts together: the
dispatch, the dispatching host, the run (or `None` while the dispatch has not
learned one yet), and the factory the run was submitted to. One key rather
than four, because the four are only meaningful as a set: a run id beside
another dispatch's host, or a host beside a previous dispatch's run, is worse
than no stamp at all — it is a stamp that reads as authoritative.

THE PENDING STAMP IS WHAT MAKES A FRESH ADMISSION DISTINGUISHABLE FROM THE OLD
CLAIM, and it is why `run_id` is OPTIONAL rather than absent. An item that was
released by a human valve and admitted again carries, for as long as it takes
the new dispatch to learn its run, a stamp whose run id would otherwise still
name the PREVIOUS run — which the factory now reports absent. A reconciler
reading that would release a live dispatch's claim. The pending stamp replaces
the whole key with one naming the new dispatch and no run, so the reading is
`attribution-pending` and the claim is held.

THE WHOLE KEY IS WRITTEN EVERY TIME, which is a correctness requirement rather
than convenience. `bd update --metadata` merges top-level keys but REPLACES a
nested object wholesale, so a partial write of this object destroys whatever
sub-key the payload did not resend. Writing it whole makes that merge rule
work FOR the stamp: the object that survives is exactly the object one writer
intended, never a blend of two.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CLAIM_STAMP_METADATA_KEY",
    "ClaimRow",
    "ClaimStamp",
    "claim_row_for",
    "claim_stamp_from_record",
    "record_claim_stamp",
]

CLAIM_STAMP_METADATA_KEY = "dispatch_claim"

_DISPATCH_ID_KEY = "dispatch_id"
_HOST_KEY = "dispatching_host"
_RUN_ID_KEY = "run_id"
_FACTORY_KEY = "factory"
_FACTORY_NAME_KEY = "name"
_FACTORY_SERVER_KEY = "server"


@dataclass(frozen=True, kw_only=True)
class ClaimStamp:
    """One item's dispatch claim, as its ledger metadata records it.

    Every field is optional because the stamp is read from a record an EARLIER
    build may have written: a reader that required a field would raise on a
    legacy row rather than reporting the claim as unattributable, and a
    reconciler that raises mid-survey stops surveying the rest of the ledger.
    """

    dispatch_id: str | None
    dispatching_host: str | None
    run_id: str | None
    factory_name: str | None
    factory_server: str | None

    @property
    def pending(self) -> bool:
        """Whether this stamp's dispatch has not yet learned its run.

        Keyed on the ABSENT run id rather than on a separate flag: a flag can
        disagree with the field it describes, and the disagreement would be
        invisible because both shapes parse.
        """
        return self.run_id is None


def claim_stamp_from_record(*, record: BeadsRecord) -> ClaimStamp | None:
    """The claim stamp an issue record carries, or None when it carries none.

    `None` means UNATTRIBUTABLE and never "no claim": the caller grades a
    missing stamp as its own hold reason, because an item resting `active`
    with assignee `fabro` and no readable stamp is a claim nobody can place.
    """
    raw = _metadata_of(record=record).get(CLAIM_STAMP_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    stamp = cast("dict[str, Any]", raw)
    factory_raw = stamp.get(_FACTORY_KEY)
    factory = cast("dict[str, Any]", factory_raw) if isinstance(factory_raw, dict) else {}
    return ClaimStamp(
        dispatch_id=_text(value=stamp.get(_DISPATCH_ID_KEY)),
        dispatching_host=_text(value=stamp.get(_HOST_KEY)),
        run_id=_text(value=stamp.get(_RUN_ID_KEY)),
        factory_name=_text(value=factory.get(_FACTORY_NAME_KEY)),
        factory_server=_text(value=factory.get(_FACTORY_SERVER_KEY)),
    )


@dataclass(frozen=True, kw_only=True)
class ClaimRow:
    """The three facts a claim recovery re-reads, from ONE ledger read.

    They are projected together rather than fetched one at a time because the
    contract's re-read is a question about one INSTANT: "still `active`, still
    assigned `fabro`, still stamped with the same run". Three separate reads
    answer about three instants, and a claim that changed between two of them
    would pass a check that no single state ever satisfied.
    """

    status: str | None
    assignee: str | None
    stamp: ClaimStamp | None


def claim_row_for(*, path: StoreConfig, work_item_id: str) -> ClaimRow:
    """Read one item's status, assignee and claim stamp as of one instant."""
    record = make_beads_client(config=path).show_issue(issue_id=work_item_id)
    return ClaimRow(
        status=_text(value=record.get("status")),
        assignee=_text(value=record.get("assignee")),
        stamp=claim_stamp_from_record(record=record),
    )


def record_claim_stamp(*, path: StoreConfig, work_item_id: str, stamp: ClaimStamp) -> None:
    """Replace this item's claim stamp WHOLESALE with the one handed in.

    ONE writer for both the pending stamp and the run stamp, taking the value
    rather than its five fields: the two differ only in whether `run_id` is
    populated, so two writers would be two renderings of one object and the
    PENDING one — the stamp that exists to be distinguishable from the previous
    claim — is exactly the one whose drift nothing would notice.

    The caller builds the `ClaimStamp`. At admission that is a stamp naming the
    new dispatch and its host with NO run id, written in a write that PRECEDES
    the `ready -> active` transition, so no instant exists in which the row is
    `active` under this dispatch while still stamped with the previous
    dispatch's run.
    """
    client = make_beads_client(config=path)
    metadata = _metadata_of(record=client.show_issue(issue_id=work_item_id))
    metadata[CLAIM_STAMP_METADATA_KEY] = {
        _DISPATCH_ID_KEY: stamp.dispatch_id,
        _HOST_KEY: stamp.dispatching_host,
        _RUN_ID_KEY: stamp.run_id,
        _FACTORY_KEY: {
            _FACTORY_NAME_KEY: stamp.factory_name,
            _FACTORY_SERVER_KEY: stamp.factory_server,
        },
    }
    client.update_issue(issue_id=work_item_id, metadata=metadata)


def _text(*, value: object) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    if isinstance(raw, dict):
        return dict(cast("dict[str, Any]", raw))
    return {}
