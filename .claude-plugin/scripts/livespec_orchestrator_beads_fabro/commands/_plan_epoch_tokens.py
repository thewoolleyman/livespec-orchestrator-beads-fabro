"""The single-use token records a plan epic's authority chain is made of.

Every verb here goes through the public `bd` surface, because the exclusion the
chain depends on is enforced INSIDE the Beads server and writers may run on
different hosts, containers or cloud instances that share nothing but that
server (maintainer ruling 2026-10-12, `.ai/ledger-writers-are-multi-host.md`).
Nothing here may acquire a lock, open a socket, touch a host directory or
reach past `bd` into SQL.

THREE PROPERTIES AN EDITOR MUST NOT INVERT.

A token is created with a SERVER-ASSIGNED id and never re-created. A duplicate
explicit-id create is an upsert that reopens a closed record and erases its
close reason, exiting 0 and printing no warning (relay research note 007), so a
late re-create of a closed token's id would admit a second winner for an
already-committed transition.

A close reports NOTHING about who won, and `token_reading` is how the winner is
established. The exit code identifies the winner in neither direction: a loser
exits 0 when its conditional update matched no row, or exits 1 with Dolt
`Error 1213` (22 of 80 closer exits were non-zero across relay research note
005's 20 trials).

`discard_token` tolerates an absent record and `delete_token` does not. The
discard runs after a transition has already COMMITTED, where a concurrent
reconciler may have removed the same predecessor, and failing a durable
transition over a record that is already gone would convert a benign outcome
into a refusal. A leaked token record is invisible to every list surface, so
the cost of tolerating it is bounded.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.errors import BeadsCommandError, BeadsMappingError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "TOKEN_DESCRIPTION",
    "TOKEN_TITLE",
    "TokenReading",
    "attempt_close",
    "create_token",
    "delete_token",
    "discard_token",
    "token_reading",
]

# What a token record says about itself to anyone who happens to `bd show` it.
# It carries no plan identity on purpose: a token is never linked to its epic
# by a dependency or parent edge, so an id-bearing title would be the only
# thing suggesting an edge that deliberately does not exist.
TOKEN_TITLE = "livespec plan authority epoch token"  # noqa: S105 - a record TITLE
TOKEN_DESCRIPTION = (
    "Single-use plan-authority epoch token. Not a work item: it carries one "  # noqa: S105 - a record DESCRIPTION
    "authority transition in its close reason and is deleted once superseded."
)

_CLOSED_STATUS = "closed"


@dataclass(frozen=True, kw_only=True)
class TokenReading:
    """One token record as a reader found it.

    `present` is False for a record that could not be read at all, which is
    kept apart from `closed` because the two support different conclusions: a
    deleted predecessor is a chain that has moved on, while an unreadable
    server is a measurement nobody took.
    """

    present: bool
    closed: bool
    close_reason: str | None


def create_token(*, client: BeadsClient) -> str:
    """Create one token under a server-assigned id and return that id."""
    return client.create_no_history_issue(title=TOKEN_TITLE, description=TOKEN_DESCRIPTION)


def attempt_close(*, client: BeadsClient, token_id: str, reason: str) -> None:
    """Attempt the conditional close that commits a transition, learning nothing."""
    client.close_issue_without_verdict(issue_id=token_id, reason=reason)


def token_reading(*, client: BeadsClient, token_id: str) -> TokenReading:
    """Read one token's status and close reason — the ONLY way to learn the winner."""
    try:
        record = client.show_issue(issue_id=token_id)
    except (BeadsMappingError, BeadsCommandError):
        return TokenReading(present=False, closed=False, close_reason=None)
    reason = record.get("close_reason")
    return TokenReading(
        present=True,
        closed=record.get("status") == _CLOSED_STATUS,
        close_reason=reason if isinstance(reason, str) else None,
    )


def delete_token(*, client: BeadsClient, token_id: str) -> None:
    """Delete one token record outright."""
    client.delete_issue(issue_id=token_id)


def discard_token(*, client: BeadsClient, token_id: str) -> None:
    """Delete one superseded token, tolerating a record that is already gone."""
    with suppress(BeadsMappingError, BeadsCommandError):
        delete_token(client=client, token_id=token_id)
