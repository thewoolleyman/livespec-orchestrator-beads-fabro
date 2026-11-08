"""What one metadata write carries, and how the server applies it.

`bd update --metadata <json>` MERGES TOP-LEVEL KEYS into the stored object and
replaces a nested object wholesale (`.ai/beads-ledger-traps.md`). Both halves
of that rule live here, because both backends must agree on them: the shell
client sends the payload and the server merges it, and the in-memory client
has to do the same merge itself or a test cannot see what a real write does.

THE CLAIM-TOKEN KEY IS WITHHELD FROM EVERY PAYLOAD BUT THE PROTOCOL'S OWN. An
item names its current claim token under `CLAIM_TOKEN_METADATA_KEY`
(`SPECIFICATION/contracts.md`, "Dispatcher policy settings", the "Claim
tokens" bullet), and only a protocol write may change that name. Every other
metadata writer builds its payload as "the whole object I read a moment ago,
plus my key", so its payload carries the token id AS OF ITS OWN READ. Sent as
it stands, a merge would put that older id back after a claim writer had moved
the token on. Left out, the merge leaves the stored name alone, which is the
only thing a writer outside the protocol may do to it.

The default is the safe one: a caller that says nothing sends no token key.
"""

from __future__ import annotations

from typing import Any, cast

__all__: list[str] = [
    "CLAIM_TOKEN_METADATA_KEY",
    "merged_metadata",
    "metadata_payload",
]

CLAIM_TOKEN_METADATA_KEY = "dispatch_claim_token"  # noqa: S105 - metadata key


def metadata_payload(
    *, metadata: dict[str, Any] | None, names_claim_token: bool
) -> dict[str, Any] | None:
    """Return the metadata one update sends: a copy, less the token key.

    `names_claim_token` is true only for a claim-token protocol write, which
    is the one kind of write that sends the key. `None` stays `None`: an
    update that carries no metadata sends none. A payload that held ONLY the
    token key has nothing left to send, so it becomes `None` too, rather than
    an empty object the server would merge to no effect.
    """
    if metadata is None:
        return None
    if names_claim_token:
        return dict(metadata)
    payload = {key: value for key, value in metadata.items() if key != CLAIM_TOKEN_METADATA_KEY}
    return payload if payload or not metadata else None


def merged_metadata(*, stored: object, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the stored object after the server's merge of one payload.

    Every top-level key of the payload replaces the stored one, nested objects
    included, and every stored key the payload omits survives. `None` means
    the update carried no metadata, so nothing is stored.
    """
    if payload is None:
        return None
    existing = cast("dict[str, Any]", stored) if isinstance(stored, dict) else {}
    return {**existing, **payload}
