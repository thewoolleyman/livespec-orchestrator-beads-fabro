"""Invoker identity resolution for the Dispatcher's published entry points.

The journal invoker attribution contract in `SPECIFICATION/contracts.md`
requires every record the journal append path writes to carry `invoker` (an
opaque identity string) and `invoker_source` (exactly one of `flag`, `env`,
`fallback`). This
module owns the RESOLUTION half of that contract; the STAMPING half belongs to
`JournalFile.append` in `_dispatcher_io`, which is the single append layer no
writer may bypass.

The resolution order is `--invoker` over `LIVESPEC_INVOKER` over the derived
`unattributed:<os-user>@<hostname>` mark. The fallback is deliberately a MARK
and not an identity: it records that NO caller asserted who acted, which is a
different claim from "this host acted" and must never be mistaken for one.

`require_invoker_refusal` implements the tightened posture. It is a STARTUP
refusal by construction — it reads nothing but the invocation's own inputs plus
the committed `dispatcher.require_invoker` dial, so an entry point can call it
before it mutates the store, writes the journal, or creates a run. That
ordering is the whole point: a refusal that fired later would itself create the
half-performed act and the attribution gap the dial exists to prevent.
"""

from __future__ import annotations

import argparse
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_REQUIRE_INVOKER,
    resolve_require_invoker,
)

__all__: list[str] = [
    "DELEGATE_ROLE",
    "ENV_SOURCE",
    "FALLBACK_SOURCE",
    "FLAG_SOURCE",
    "INVOKER_ENV_VAR",
    "INVOKER_FLAG",
    "DelegationGrant",
    "InvokerIdentity",
    "add_invoker_argument",
    "default_invoker_identity",
    "invoker_from_args",
    "require_invoker_refusal",
    "resolve_invoker",
]

# The one environment variable the contract accepts as an asserted identity.
INVOKER_ENV_VAR = "LIVESPEC_INVOKER"
# The one flag the contract accepts as an asserted identity.
INVOKER_FLAG = "--invoker"

FLAG_SOURCE = "flag"
# The reserved `<role>` a press asserts when it acts under a recorded maintainer
# delegation rather than as the human who granted it (the delegated valve
# authority paragraph of the journal invoker attribution contract).
DELEGATE_ROLE = "delegate"
ENV_SOURCE = "env"
FALLBACK_SOURCE = "fallback"

_FALLBACK_PREFIX = "unattributed:"
_USER_ENV_VAR = "USER"
_UNKNOWN_USER = "unknown-user"
_UNKNOWN_HOST = "unknown-host"
_INVOKER_HELP = (
    "identity of whoever invoked this state-changing act, stamped on every "
    "journal record it writes; overrides the LIVESPEC_INVOKER environment "
    "variable. The RECOMMENDED convention is <role>:<name>."
)


@dataclass(frozen=True, kw_only=True)
class DelegationGrant:
    """One VERIFIED maintainer delegation a press acts under.

    Only `drive`'s delegation verifier constructs one for a live press, after
    matching the press's `--delegation` ref against a committed
    `dispatcher.valve_delegations` entry; the append layer then stamps it onto
    every journal record the press writes, beside `invoker`.
    """

    ref: str
    grantor: str
    record: str

    def as_record(self) -> dict[str, str]:
        """The `delegation` object a journal record and a result payload carry."""
        return {"ref": self.ref, "grantor": self.grantor, "record": self.record}


@dataclass(frozen=True, kw_only=True)
class InvokerIdentity:
    """One resolved invocation identity plus the input it was resolved from.

    `delegation` is `None` for every identity except a verified delegated
    press, so the invoker string itself never has to carry the grant.
    """

    invoker: str
    invoker_source: str
    delegation: DelegationGrant | None = None


def resolve_invoker(
    *,
    flag: str | None,
    env: Mapping[str, str],
    hostname: str | None = None,
) -> InvokerIdentity:
    """Resolve the invocation identity: flag, else environment, else the mark.

    An empty or whitespace-only value is NOT an assertion — it is treated as
    absent at both the flag and the environment step, so a caller cannot
    launder an unattributed invocation into a `flag`-sourced record by passing
    `--invoker ''`.
    """
    asserted = _non_empty(value=flag)
    if asserted is not None:
        return InvokerIdentity(invoker=asserted, invoker_source=FLAG_SOURCE)
    from_env = _non_empty(value=env.get(INVOKER_ENV_VAR))
    if from_env is not None:
        return InvokerIdentity(invoker=from_env, invoker_source=ENV_SOURCE)
    return InvokerIdentity(
        invoker=_fallback_mark(env=env, hostname=hostname),
        invoker_source=FALLBACK_SOURCE,
    )


def default_invoker_identity() -> InvokerIdentity:
    """Resolve an identity from the process environment alone (no flag).

    The default a `JournalFile` constructed without an explicit identity
    carries, so a journal write from a surface that has not been handed the
    invocation's own identity is still stamped, and still says how the identity
    it carries was resolved.
    """
    return resolve_invoker(flag=None, env=os.environ)


def invoker_from_args(*, args: argparse.Namespace) -> InvokerIdentity:
    """Resolve the identity for a parsed invocation of a published entry point.

    `getattr` rather than attribute access: not every `Namespace` that reaches
    a journal-constructing helper came from a parser carrying `--invoker`, and
    a missing flag is exactly the "no flag was passed" case the resolution
    order already handles.
    """
    return resolve_invoker(flag=getattr(args, "invoker", None), env=os.environ)


def add_invoker_argument(*, parser: argparse.ArgumentParser) -> None:
    """Attach `--invoker` to one published state-changing entry point."""
    _ = parser.add_argument(INVOKER_FLAG, dest="invoker", default=None, help=_INVOKER_HELP)


def require_invoker_refusal(*, args: argparse.Namespace, repo: Path) -> str | None:
    """Refuse a fallback-only invocation when `dispatcher.require_invoker` is true.

    Returns the operator-facing refusal text, which each entry point emits
    before returning its precondition exit code (exit 3), or `None` to proceed.
    An unreadable `.livespec.jsonc` rides the documented default (`false`)
    exactly as every other `dispatcher.*` read does, so a config that stops
    parsing cannot silently TIGHTEN the posture into refusing every invocation.
    """
    identity = invoker_from_args(args=args)
    if identity.invoker_source != FALLBACK_SOURCE:
        return None
    required = unsafe_perform_io(
        resolve_require_invoker(cwd=repo).value_or(DEFAULT_REQUIRE_INVOKER)
    )
    if not required:
        return None
    return (
        "ERROR: dispatcher.require_invoker is true and this invocation asserted "
        f"no identity (resolved {identity.invoker} as {FALLBACK_SOURCE}).\n"
        f"Assert one of the two accepted identity inputs: pass {INVOKER_FLAG} <id> "
        f"on the invocation, or set the {INVOKER_ENV_VAR} environment variable.\n"
    )


def _non_empty(*, value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _fallback_mark(*, env: Mapping[str, str], hostname: str | None) -> str:
    user = _non_empty(value=env.get(_USER_ENV_VAR)) or _UNKNOWN_USER
    host = _non_empty(value=hostname if hostname is not None else socket.gethostname())
    return f"{_FALLBACK_PREFIX}{user}@{host or _UNKNOWN_HOST}"
