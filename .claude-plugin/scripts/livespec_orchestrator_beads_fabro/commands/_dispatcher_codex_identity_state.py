"""The private host file one Codex identity observation is remembered in.

The persistence half of the opt-in credential observation. A refresh happens
between two runs of a status command, so the only way a status reading can say
anything about it is to have remembered the preceding reading.

What is stored is deliberately narrow: the one-way fingerprints
`_dispatcher_codex_identity_claims` produced, plus the access token's expiry
instant and the moment of the reading. No token, no claim value, and nothing
copied out of `auth.json` -- the provider's authentication file is only ever
read, and never by this module at all.

Two properties of the write are load-bearing rather than incidental. It goes
through a mode-600 temporary and an atomic replace, so an UPDATE installs the
restrictive mode afresh instead of inheriting whatever the previous file had
drifted to, and a concurrent reader sees either the old record or the new one and
never a half-written file. And a file that EXISTS but cannot be parsed is its own
outcome: calling it absent would invite a fresh first observation over a record
still on disk, and calling it a prior observation would let the comparison report
continuity it never measured.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "IDENTITY_STATE_SCHEMA",
    "CodexIdentityStateRecord",
    "PriorIdentityState",
    "identity_state_collision",
    "read_prior_identity_state",
    "write_identity_state",
]

# Versioned, so a later field addition is a schema a reader can recognise
# rather than a shape it has to guess at.
IDENTITY_STATE_SCHEMA = "livespec-codex-identity-observation/v1"

_SCHEMA_FIELD = "schema"
_OBSERVED_AT_FIELD = "observed_at_epoch"
_EXPIRES_AT_FIELD = "expires_at_epoch"
_SESSION_FIELD = "session_fingerprint"
_TOKEN_FIELD = "token_fingerprint"  # noqa: S105 - a JSON field NAME; its value is a digest

_STATE_FILE_MODE = 0o600
_STATE_DIR_MODE = 0o700

PriorStateStatus = Literal["absent", "readable", "unreadable"]

_ABSENT_DETAIL = "No preceding observation has been recorded at this path."


@dataclass(frozen=True, kw_only=True)
class CodexIdentityStateRecord:
    """One remembered observation, exactly as the state file carries it."""

    session_fingerprint: str | None
    token_fingerprint: str | None
    expires_at_epoch: int | None
    observed_at_epoch: int


@dataclass(frozen=True, kw_only=True)
class PriorIdentityState:
    """The preceding observation, and what reading it actually established."""

    status: PriorStateStatus
    detail: str
    record: CodexIdentityStateRecord | None


def read_prior_identity_state(*, path: Path) -> PriorIdentityState:
    """Read the preceding observation, distinguishing absent from unreadable.

    The two are reported apart because they license different conclusions: an
    absent file means this reading is genuinely the first, while a file that
    cannot be parsed means a preceding reading exists and this one cannot see
    it. Collapsing the second into the first would quietly restart the series
    over a record still sitting on disk.
    """
    if not path.exists():
        return PriorIdentityState(status="absent", detail=_ABSENT_DETAIL, record=None)
    stored = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(stored, AttemptFailure):
        return _unreadable(detail=f"could not be opened ({stored.error})")
    raw = parse_json(text=stored)
    if isinstance(raw, JsonParseFailure):
        return _unreadable(detail="is not valid JSON")
    if not isinstance(raw, dict):
        return _unreadable(detail="is not a JSON object")
    return _parsed(block=cast("dict[str, object]", raw))


def write_identity_state(*, path: Path, record: CodexIdentityStateRecord) -> str | None:
    """Record this observation, returning a detail string if it was not written."""
    text = json.dumps(_encode(record=record), indent=2, sort_keys=True) + "\n"
    written = attempt(action=lambda: _write(path=path, text=text), exceptions=(OSError,))
    if isinstance(written, AttemptFailure):
        return f"This observation could not be written: {written.error}"
    return None


def identity_state_collision(*, state_path: Path, protected_path: Path) -> str | None:
    """Return why writing `state_path` would touch `protected_path`, else None.

    BOTH paths a write touches are checked, because they are destructive in
    different ways and at different moments: the destination is replaced at the
    end, while the temporary is UNLINKED before anything is opened. A guard
    covering only the destination would let the unlink delete the protected file
    and then report a perfectly successful write.

    Equality is by RESOLVED path, so `.`/`..` segments and a symlinked parent
    cannot alias past it, plus a same-file check for the case resolution cannot
    see -- a hard link, where two genuinely different paths name one inode.
    `resolve()` is non-strict because the destination normally does not exist
    yet; it still normalizes the ancestors that do.
    """
    protected = protected_path.resolve()
    for candidate, role in (
        (state_path, "destination"),
        (_temporary_for(path=state_path), "temporary"),
    ):
        if candidate.resolve() == protected or _same_file(left=candidate, right=protected_path):
            return (
                f"the observation {role} resolves to the host Codex credential " f"at {protected}"
            )
    return None


def _same_file(*, left: Path, right: Path) -> bool:
    """Whether two existing paths name one file; False when either is absent."""
    same = attempt(action=lambda: left.samefile(right), exceptions=(OSError,))
    if isinstance(same, AttemptFailure):
        return False
    return same


def _temporary_for(*, path: Path) -> Path:
    """The staging path a write passes through, derived in ONE place."""
    return path.with_name(f"{path.name}.tmp")


def _write(*, path: Path, text: str) -> None:
    """Install the record through a private temporary and an atomic replace.

    The mode is set at CREATION rather than afterwards, so the bytes are never
    on disk under a wider mode, not even momentarily.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=_STATE_DIR_MODE)
    temporary = _temporary_for(path=path)
    temporary.unlink(missing_ok=True)
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, _STATE_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        _ = handle.write(text)
    _ = temporary.replace(path)


def _encode(*, record: CodexIdentityStateRecord) -> dict[str, object]:
    return {
        _SCHEMA_FIELD: IDENTITY_STATE_SCHEMA,
        _OBSERVED_AT_FIELD: record.observed_at_epoch,
        _EXPIRES_AT_FIELD: record.expires_at_epoch,
        _SESSION_FIELD: record.session_fingerprint,
        _TOKEN_FIELD: record.token_fingerprint,
    }


def _parsed(*, block: dict[str, object]) -> PriorIdentityState:
    """Grade a parsed state file against the schema this build writes.

    An unrecognised schema and a record carrying no reading instant are both
    unreadable rather than partially trusted: a record whose shape this build
    does not know cannot be compared field by field, and an invented instant
    would read exactly like a real one.
    """
    if block.get(_SCHEMA_FIELD) != IDENTITY_STATE_SCHEMA:
        return _unreadable(detail=f"does not carry the {IDENTITY_STATE_SCHEMA} schema")
    observed_at = _int_field(block=block, name=_OBSERVED_AT_FIELD)
    if observed_at is None:
        return _unreadable(detail=f"carries no integer {_OBSERVED_AT_FIELD}")
    return PriorIdentityState(
        status="readable",
        detail="The preceding observation was read.",
        record=CodexIdentityStateRecord(
            session_fingerprint=_str_field(block=block, name=_SESSION_FIELD),
            token_fingerprint=_str_field(block=block, name=_TOKEN_FIELD),
            expires_at_epoch=_int_field(block=block, name=_EXPIRES_AT_FIELD),
            observed_at_epoch=observed_at,
        ),
    )


def _unreadable(*, detail: str) -> PriorIdentityState:
    return PriorIdentityState(
        status="unreadable",
        detail=(
            f"A preceding observation exists at this path but {detail}, so this "
            "reading establishes nothing about whether either identifier changed."
        ),
        record=None,
    )


def _str_field(*, block: dict[str, object], name: str) -> str | None:
    value = block.get(name)
    if isinstance(value, str) and value != "":
        return value
    return None


def _int_field(*, block: dict[str, object], name: str) -> int | None:
    value = block.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
