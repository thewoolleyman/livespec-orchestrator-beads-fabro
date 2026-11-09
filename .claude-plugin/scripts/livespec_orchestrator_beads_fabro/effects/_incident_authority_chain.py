"""Locating and walking the retained incident token chain.

`read_genesis` verifies the published root token of an item and returns it with the
item's head hint. `read_chain` walks the tokens' own conditional-close links from
the hint's latest closed token (a current read) or from the genesis root (every
other read) to the open successor. The hint is a start point and never authority:
a stale one only lengthens the forward walk, and an absent, open, foreign or
unreadable one reads the whole chain from the root.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    HEAD_HINT_KEY,
    TOKEN_TITLE,
    TRANSITION_MARKER,
    decode_attempt,
    decode_record,
    unsupported_carrier,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
)
from livespec_orchestrator_beads_fabro._incident_carrier import CARRIER_UNSUPPORTED
from livespec_orchestrator_beads_fabro.effects._incident_genesis_fence import (
    FENCED_GENESIS_KEYS,
    fenced_root_holds,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = ["read_chain", "read_genesis"]
_GENESIS_KEYS = frozenset(("schema", "repository", "item_id", "root_token_id"))
_TRANSITION_KEYS = frozenset(
    ("schema", "repository", "item_id", "prior_token_id", "next_token_id", "attempt")
)
_MAX_TOKENS = 256


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _head_hint(*, item: dict[str, Any]) -> str | None:
    metadata = item.get("metadata")
    hint = (
        cast("dict[str, Any]", metadata).get(HEAD_HINT_KEY) if isinstance(metadata, dict) else None
    )
    return hint if isinstance(hint, str) and hint else None


def read_genesis(
    *, client: BeadsClient, repository: str, item_id: str
) -> tuple[str, str | None] | AuthorityRefusal:
    """The published root token, and the item's head hint when it names one."""
    item = client.show_issue(issue_id=item_id)
    if item.get("id") != item_id:
        return _refuse(code="incident-authority-item-mismatch", detail=item_id)
    roots: set[str] = set()
    for comment in client.list_comments(issue_id=item_id):
        text = comment.get("text")
        if not isinstance(text, str) or not text.startswith(GENESIS_MARKER):
            continue
        record = decode_record(
            text=text, marker=GENESIS_MARKER, keys=_GENESIS_KEYS
        ) or decode_record(text=text, marker=GENESIS_MARKER, keys=FENCED_GENESIS_KEYS)
        if (
            record is None
            or record["repository"] != repository
            or record["item_id"] != item_id
            or not isinstance(record["root_token_id"], str)
            or not record["root_token_id"]
            or not fenced_root_holds(client=client, record=record, repository=repository)
        ):
            return _refuse(code="incident-authority-invalid-genesis", detail=item_id)
        roots.add(record["root_token_id"])
    if len(roots) != 1:
        return _refuse(
            code="incident-authority-ambiguous" if roots else "incident-authority-missing",
            detail=item_id,
        )
    return next(iter(roots)), _head_hint(item=item)


def _transition(
    *,
    record: dict[str, Any],
    token: str,
    repository: str,
    item_id: str,
    generation: int | None,
    used_operations: set[str],
) -> tuple[IncidentAttempt, str] | AuthorityRefusal:
    payload = decode_record(
        text=record.get("close_reason"), marker=TRANSITION_MARKER, keys=_TRANSITION_KEYS
    )
    if (
        payload is None
        or payload["repository"] != repository
        or payload["item_id"] != item_id
        or payload["prior_token_id"] != token
        or not isinstance(payload["next_token_id"], str)
        or not payload["next_token_id"]
    ):
        return _refuse(code="incident-authority-invalid-transition", detail=token)
    if unsupported_carrier(value=payload["attempt"]):
        return _refuse(code=CARRIER_UNSUPPORTED, detail=token)
    attempt = decode_attempt(value=payload["attempt"])
    if (
        attempt is None
        or attempt.repository != repository
        or attempt.item_id != item_id
        or (generation is not None and attempt.generation != generation)
    ):
        return _refuse(code="incident-authority-invalid-attempt", detail=token)
    if attempt.operation_id in used_operations:
        return _refuse(code="incident-authority-reused-operation", detail=attempt.operation_id)
    return attempt, payload["next_token_id"]


def _walk(
    *, client: BeadsClient, repository: str, item_id: str, start: str, generation: int | None
) -> tuple[list[tuple[str, IncidentAttempt]], str] | AuthorityRefusal:
    """Follow the links from `start`; a None generation takes the first attempt's own."""
    seen: set[str] = set()
    history: list[tuple[str, IncidentAttempt]] = []
    token = start
    for _ in range(_MAX_TOKENS):
        if token in seen:
            return _refuse(code="incident-authority-cycle", detail=token)
        seen.add(token)
        record = client.show_issue(issue_id=token)
        if record.get("id") != token or record.get("title") != TOKEN_TITLE:
            return _refuse(code="incident-authority-invalid-token", detail=token)
        if record.get("status") == "backlog":
            return history, token
        if record.get("status") != "closed":
            return _refuse(code="incident-authority-invalid-token-state", detail=token)
        transition = _transition(
            record=record,
            token=token,
            repository=repository,
            item_id=item_id,
            generation=generation,
            used_operations={prior.operation_id for _, prior in history},
        )
        if isinstance(transition, AuthorityRefusal):
            return transition
        attempt, successor = transition
        history.append((token, attempt))
        generation = attempt.generation + 1
        token = successor
    return _refuse(code="incident-authority-history-limit", detail=start)


def read_chain(
    *,
    client: BeadsClient,
    repository: str,
    item_id: str,
    genesis: tuple[str, str | None],
    hinted: bool,
) -> tuple[list[tuple[str, IncidentAttempt]], str] | AuthorityRefusal:
    root, hint = genesis
    if hinted and hint is not None:
        short = _walk(
            client=client, repository=repository, item_id=item_id, start=hint, generation=None
        )
        if not isinstance(short, AuthorityRefusal) and short[0]:
            return short
    return _walk(client=client, repository=repository, item_id=item_id, start=root, generation=1)
