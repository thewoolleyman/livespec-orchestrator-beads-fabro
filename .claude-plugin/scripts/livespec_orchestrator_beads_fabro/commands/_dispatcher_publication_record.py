"""Run-to-head bindings that publication stages leave on pull requests.

`SPECIFICATION/contracts.md`, in its paragraph on a publication being bound to its
run on the pull request, has `publish_draft` and `pr_refresh` post one
`livespec-publication-record` comment after each push that moved the publish
branch. The record names the run and the commit the push ACTUALLY sent, and it
lives on the forge, so every host that can read the pull request reads the same
attribution whatever its own dispatch journal holds.

A reader accepts a comment as a record only when the forge reports its author
as exactly the committed `dispatcher.publication_identity`. With the key unset
no comment is a record: the marker is plain text, so any commenter could
otherwise attribute a head to any run. When more than one record names a head,
the most recently posted one decides, so the pairs are returned newest first
and `published_head_relation` reads the first pair that names a head.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import ProofRecord
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    FACTORY_RECORD_VERDICTS,
    published_head,
)

__all__: list[str] = [
    "PUBLICATION_RECORD_FIELDS",
    "PUBLICATION_RECORD_MARKER",
    "publication_identity",
    "publication_pairs",
    "publications_of",
]

# The marker line and the field names, one per line after it. Public because the
# materialized program that POSTS a record substitutes them from here, so the
# writer and this reader cannot come to spell the format two ways.
PUBLICATION_RECORD_MARKER = "livespec-publication-record"
PUBLICATION_RECORD_FIELDS = ("run-id", "head", "pull-request", "stage", "pushed-at")
_PUBLICATION_IDENTITY_KEY = "publication_identity"
_SHA_LENGTH = 40
_SHA_CHARACTERS = frozenset("0123456789abcdef")


def publication_identity(*, repo: Path) -> str:
    """The committed `dispatcher.publication_identity`, or `""` when it names none.

    An unreadable configuration reads as no identity, the fail-closed direction:
    with no identity no comment is a publication record, so a blinded read can
    only leave a head unattributed and never attribute one to the wrong run.
    """
    value = unsafe_perform_io(
        read_dispatcher_config_value(cwd=repo, key=_PUBLICATION_IDENTITY_KEY).value_or(None)
    )
    return value if isinstance(value, str) else ""


def publications_of(
    *,
    records: tuple[ProofRecord, ...],
    comments: tuple[Mapping[str, object], ...],
    publication_identity: str,
) -> tuple[tuple[str, str], ...]:
    """Each head a record declares, paired with the run that published it.

    Publication records come first: a head with a publication record belongs to
    the run the most recently posted record names, and only a head with none
    falls back to the factory proof record that declares it.
    """
    return publication_pairs(comments=comments, publication_identity=publication_identity) + tuple(
        (head, one.run_id)
        for one in records
        if one.verdict in FACTORY_RECORD_VERDICTS
        and (head := published_head(body=one.body)) is not None
    )


def publication_pairs(
    *, comments: tuple[Mapping[str, object], ...], publication_identity: str
) -> tuple[tuple[str, str], ...]:
    """Return the head/run bindings authored by the configured identity, newest first."""
    if not publication_identity:
        return ()
    return tuple(
        reversed(
            tuple(
                (fields["head"], fields["run-id"])
                for comment in comments
                if _author_login(comment=comment) == publication_identity
                and (fields := _record_fields(body=comment.get("body"))) is not None
            )
        )
    )


def _author_login(*, comment: Mapping[str, object]) -> str | None:
    author = comment.get("author")
    if not isinstance(author, Mapping):
        return None
    login = cast("Mapping[str, object]", author).get("login")
    return login if isinstance(login, str) and login else None


def _record_fields(*, body: object) -> dict[str, str] | None:
    if not isinstance(body, str):
        return None
    lines = body.splitlines()
    if not lines or lines[0] != PUBLICATION_RECORD_MARKER:
        return None
    fields = {
        key: value.strip()
        for line in lines[1:]
        if ":" in line
        for key, value in (line.split(":", maxsplit=1),)
        if key in PUBLICATION_RECORD_FIELDS and value.strip()
    }
    if set(fields) != set(PUBLICATION_RECORD_FIELDS):
        return None
    head = fields["head"]
    if len(head) != _SHA_LENGTH or any(character not in _SHA_CHARACTERS for character in head):
        return None
    return fields
