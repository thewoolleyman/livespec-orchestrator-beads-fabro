"""The sanctioned claim-token migration pass, and the census of unnamed items.

`dispatcher.claim_tokens` may be committed `true` only once every non-closed
item of the tenant names an open *current token* (contracts.md, "Stranded claim
release" -> "Claim tokens"). Nothing else gives an item its first token: a
claim writer that finds none MUST write nothing and report
`claim-token-missing`. This module is the one place a first token comes from.

WHAT "NAMES NO OPEN TOKEN" MEANS is decided in `_verdict`, once, for the pass
and for its re-read: the item names no token at all, or the token it names is
closed. A discarded token is a closed token, so it needs no case of its own. A
named token that cannot be READ is neither: it is `claim-token-unobservable`,
and the item is held rather than renamed, because an unreadable record is a
measurement nobody took and renaming over an open token would break the rule
that an item already naming one is left unchanged.

THE PASS IS RE-RUNNABLE BECAUSE IT KEEPS NO STATE OF ITS OWN. Each run reads
the tenant and writes only the items that name no open token now, so a run that
stopped half way is finished by running it again. One item's write is ordered
read, mint, name, read back: a failure before the name leaves at most an open
token no item names, which every list surface omits and which nothing reads.
An item is reported as named only when the read-back names the fresh token.

THE PASS CANNOT MEASURE ITS OWN PRECONDITION. It MUST run while every claim
writer of the tenant is stopped, and writers share nothing but the Beads server
(`.ai/ledger-writers-are-multi-host.md`), so no lock or process table on this
host can establish that. The caller attests it; `apply=False` is the survey
that writes nothing and needs no attestation.

`claim_token_named_by` repeats the three-line read `_store_claim_tokens` keeps
private. The duplication is bound by test rather than by import: the census
must report an item exactly when the writer protocol refuses it, and
`test_store_claim_token_migration` asserts that agreement record by record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_claim_tokens import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import token_reading
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError, BeadsMappingError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ClaimTokenMigrationReport",
    "claim_token_named_by",
    "migrate_claim_tokens",
    "read_work_item_ids_naming_no_claim_token",
]

_CLOSED_STATUS = "closed"

_ITEM_CLOSED = "item-closed"
_NAMES_OPEN = "names-open-token"
_NAMES_NONE = "names-no-open-token"
_UNOBSERVABLE = "claim-token-unobservable"

_CHANGED = "changed-since-listing"
_WRITE_FAILED = "write-failed"
_WRITE_UNCONFIRMED = "write-unconfirmed"


@dataclass(frozen=True, kw_only=True)
class ClaimTokenMigrationReport:
    """What one run of the pass found and did, item by item.

    `unnamed` is populated only by a survey: the items that name no open token
    and were not written because the run was not applied. `held` carries each
    item the run could not settle beside the reason, and is what a second run
    is for.
    """

    applied: bool
    named: tuple[tuple[str, str], ...]
    unchanged: tuple[str, ...]
    unnamed: tuple[str, ...]
    held: tuple[tuple[str, str], ...]

    @property
    def complete(self) -> bool:
        """Whether every non-closed item this run read names an open token."""
        return not self.unnamed and not self.held


def claim_token_named_by(*, record: BeadsRecord) -> str | None:
    """The claim token one item record names, or None when it names none."""
    raw = record.get("metadata")
    metadata = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    value = metadata.get(CLAIM_TOKEN_METADATA_KEY)
    return value.strip() if isinstance(value, str) and value.strip() != "" else None


def migrate_claim_tokens(*, client: BeadsClient, apply: bool) -> ClaimTokenMigrationReport:
    """Name a fresh open token on every non-closed item that names no open one.

    With `apply` false nothing is written and the same items are reported as
    `unnamed`. The caller passes `apply=True` only after attesting that every
    claim writer of the tenant is stopped.
    """
    named: list[tuple[str, str]] = []
    unchanged: list[str] = []
    unnamed: list[str] = []
    held: list[tuple[str, str]] = []
    records = {
        item_id: record
        for record in client.list_issues()
        if isinstance(item_id := record.get("id"), str)
    }
    for item_id in sorted(records):
        verdict = _verdict(client=client, record=records[item_id])
        if verdict == _NAMES_OPEN:
            unchanged.append(item_id)
        elif verdict == _UNOBSERVABLE:
            held.append((item_id, _UNOBSERVABLE))
        elif verdict == _NAMES_NONE and not apply:
            unnamed.append(item_id)
        elif verdict == _NAMES_NONE:
            token_id, reason = _name_fresh_token(client=client, item_id=item_id)
            if token_id is None:
                held.append((item_id, reason))
            else:
                named.append((item_id, token_id))
    return ClaimTokenMigrationReport(
        applied=apply,
        named=tuple(named),
        unchanged=tuple(unchanged),
        unnamed=tuple(unnamed),
        held=tuple(held),
    )


def read_work_item_ids_naming_no_claim_token(*, path: StoreConfig) -> tuple[str, ...]:
    """Every non-closed tenant item that names no current token, sorted.

    ONE list read and no per-item read, because `needs-attention` calls it on
    every pass once the key is `true`. It asks the question the writer protocol
    asks, whether the item names a token at all, and not the migration's wider
    one: an item naming a CLOSED token is a transition the protocol itself
    waits out or takes over, and reporting it here would send an operator to
    stop every writer over a state the writers resolve.

    Token records need no filter. They are no-history records, which no list
    surface returns.
    """
    client = make_beads_client(config=path)
    return tuple(
        sorted(
            item_id
            for record in client.list_issues()
            if isinstance(item_id := record.get("id"), str)
            and record.get("status") != _CLOSED_STATUS
            and claim_token_named_by(record=record) is None
        )
    )


def _verdict(*, client: BeadsClient, record: BeadsRecord) -> str:
    """Classify one item record: closed, naming an open token, none, or unreadable."""
    if record.get("status") == _CLOSED_STATUS:
        return _ITEM_CLOSED
    token_id = claim_token_named_by(record=record)
    if token_id is None:
        return _NAMES_NONE
    reading = token_reading(client=client, token_id=token_id)
    if not reading.present:
        return _UNOBSERVABLE
    return _NAMES_NONE if reading.closed else _NAMES_OPEN


def _name_fresh_token(*, client: BeadsClient, item_id: str) -> tuple[str | None, str]:
    """Name one fresh token on one item: `(token id, "")`, or `(None, reason)`.

    The item is read again first, through `bd show`, and written only when that
    read still says it names no open token. The listing and the show are two
    read surfaces, and a writer that was not stopped can move the item between
    them; either way the newer read wins and the item is held, never renamed.

    The whole metadata object is sent, as every other metadata write here does:
    `bd update --metadata` is a client-side read-modify-write.
    """
    try:
        record = client.show_issue(issue_id=item_id)
        verdict = _verdict(client=client, record=record)
        if verdict != _NAMES_NONE:
            return None, f"{_CHANGED}: {verdict}"
        token_id = create_claim_token(client=client)
        raw = record.get("metadata")
        metadata = dict(cast("dict[str, Any]", raw)) if isinstance(raw, dict) else {}
        metadata[CLAIM_TOKEN_METADATA_KEY] = token_id
        client.update_issue(issue_id=item_id, metadata=metadata, names_claim_token=True)
        landed = claim_token_named_by(record=client.show_issue(issue_id=item_id))
    except (BeadsCommandError, BeadsMappingError) as error:
        return None, f"{_WRITE_FAILED}: {error}"
    if landed != token_id:
        return None, _WRITE_UNCONFIRMED
    return token_id, ""
