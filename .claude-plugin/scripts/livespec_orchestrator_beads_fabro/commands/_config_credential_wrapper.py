"""The repository's TOP-LEVEL `credential_wrapper` argv prefix, as read.

Split out of `_config` by cohesion, exactly as `_config_acp` is: this is the
only key `_config` read that sits at the `.livespec.jsonc` ROOT rather than
under the plugin's own `connection` or `dispatcher` block, it has one consumer,
and its fail-soft-at-the-consumer contract is a different essay from anything
`_config` resolves. Do not confuse it with `_dispatcher_credential_wrapper`,
which reads what a DISPATCH TARGET declares; this answers what THIS repository
declares for its own pre-push gate.

The root reader stays in `_config`, where every other block reader is, and is
consumed here through its PUBLIC entry point `root_mapping` — a cross-module
private import is what pyright strict and the `private_calls` check refuse, and
a second root reader would be a second account of one file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from returns.io import IOResult

from livespec_orchestrator_beads_fabro.commands._config import (
    ConfigUnreadable,
    root_mapping,
)

__all__: list[str] = [
    "resolve_credential_wrapper",
]

_CREDENTIAL_WRAPPER_KEY = "credential_wrapper"


def resolve_credential_wrapper(*, cwd: Path) -> IOResult[list[str], ConfigUnreadable]:
    """The top-level `credential_wrapper` argv-prefix; `[]` when none is configured.

    An ABSENT config file, an absent key, and a non-list value all yield `[]` on
    the SUCCESS track — each is an ANSWER: this repo configures no wrapper. A file
    that EXISTS and will not parse rides the FAILURE track instead.

    ⛔ THE DISTINCTION IS LOAD-BEARING, and it used to be lost here. The sole
    consumer is the pre-push `check-ledger-conformance-live` gate, which invokes
    the ledger check UNDER this wrapper and SKIPS when there is none. Folding an
    unreadable config into `[]` therefore let a stray comma SILENTLY TURN THE
    PRE-PUSH GATE OFF, reported in the same words as a repo that never wanted one.

    ⚠️ It stays fail-SOFT at the consumer by deliberate design — that recipe runs
    on every push and a false-fail would brick them all — so this failure track
    exists to be REPORTED, not to block. Returning it is what makes the two
    outcomes tellable apart; deciding what to do about them is the caller's.
    """
    return root_mapping(cwd=cwd).map(lambda root: _credential_wrapper_tokens(root=root))


def _credential_wrapper_tokens(*, root: dict[str, Any]) -> list[str]:
    """The `credential_wrapper` argv tokens in a root mapping, or [] when unset."""
    raw = root.get(_CREDENTIAL_WRAPPER_KEY)
    if not isinstance(raw, list):
        return []
    return [str(token) for token in cast("list[Any]", raw)]
