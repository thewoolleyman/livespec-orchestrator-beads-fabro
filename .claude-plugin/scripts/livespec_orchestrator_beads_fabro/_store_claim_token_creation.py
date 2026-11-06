"""The first claim token of a work item created after the claim-token cutover.

While `dispatcher.claim_tokens` is committed `true`, every non-closed work item
MUST name exactly one token, its *current token* (contracts.md, "Dispatcher
policy settings" -> "Claim tokens"). The migration pass names one on every item
that exists at the cutover and nothing else did so afterwards, so an item
created later named none: every claim writer refused it with
`claim-token-missing` until an operator stopped the tenant's writers and ran
the pass again. This module closes that gap at the store's creation seam.

THE TOKEN IS NAMED IN THE CREATING WRITE, never in a second one. The token is
minted first and its id rides in the metadata `bd create` writes, so there is
no instant at which the item exists and names nothing. A create-then-name pair
would be a claim-changing write made outside the token protocol.

A FAILED CREATE DISCARDS ITS TOKEN. The token was minted for an item that does
not exist, so its creator closes it with the same `claim-token-discard` reason
shape `_store_claim_tokens` gives a successor no item ever named. That module
keeps its discard private, so the shape is repeated here and bound by test.
Only the two failures that say `bd` ran and refused are caught: after a
connection or credential failure nothing is reachable to close the token
through, and an open token no item names is omitted by every list surface and
read by nothing.

AN ITEM BORN CLOSED NAMES NO TOKEN. The rule covers non-closed items, and a
closed item is never the subject of a claim-changing write.

THE SETTING IS READ FROM THE ITEM'S OWN REPOSITORY, on every create, and an
UNREADABLE setting raises instead of reading as `false`. Reading it as `false`
would create an item no claim writer can write, silently, in a tenant that is
cut over. A connection descriptor carrying no `repo_root` names no repository,
so there is no committed setting to read and the answer is the unset one.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._store_claim_tokens import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import attempt_close
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsMappingError,
    LivespecConfigUnreadableError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, IssueDraft
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "claim_tokens_committed",
    "create_issue_naming_first_claim_token",
]

_DISCARD_REASON = json.dumps(
    {"kind": "claim-token-discard", "writer": "work-item-create"},
    separators=(",", ":"),
    sort_keys=True,
)


def claim_tokens_committed(*, path: StoreConfig) -> bool:
    """Whether the item's repository commits `dispatcher.claim_tokens` true.

    Raises `LivespecConfigUnreadableError` when the setting is present and
    cannot be read. The store's write seams are exception-based and none of
    their callers carries a failure track, so this follows
    `resolve_store_config` rather than inventing a second convention.
    """
    repo_root = path.repo_root
    if repo_root is None:
        return False
    setting = resolve_claim_tokens(cwd=repo_root)
    if isinstance(setting, IOFailure):
        raise LivespecConfigUnreadableError(detail=unsafe_perform_io(setting.failure()).detail)
    return unsafe_perform_io(setting.unwrap())


def create_issue_naming_first_claim_token(
    *, client: BeadsClient, draft: IssueDraft, names_token: bool
) -> None:
    """Create one issue; with `names_token`, have it name a fresh open token.

    With `names_token` false this is the bare create and nothing else is read
    or written.
    """
    if not names_token:
        _ = client.create_issue(draft=draft)
        return
    token_id = create_claim_token(client=client)
    named = replace(draft, metadata={**draft.metadata, CLAIM_TOKEN_METADATA_KEY: token_id})
    try:
        _ = client.create_issue(draft=named)
    except (BeadsCommandError, BeadsMappingError):
        attempt_close(client=client, token_id=token_id, reason=_DISCARD_REASON)
        raise
