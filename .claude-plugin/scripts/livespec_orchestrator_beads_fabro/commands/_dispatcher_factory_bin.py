"""The engine client binary ONE factory declares, resolved against the global.

`LIVESPEC_FABRO_BIN`, `dispatcher.fabro_bin` and the home-path probe answer
one question for the whole Dispatcher — which `fabro` client drives a run —
and a single global answer was correct while every declared factory ran the
same engine. Running an upgrade candidate beside the production server breaks
that in both directions: the candidate client cannot talk to the legacy
server and the legacy client cannot talk to the candidate, so the client is a
property OF THE FACTORY rather than of the host.

A factory entry's optional `bin` key carries it, and this module is the one
place the two layers meet. An ABSENT key is a complete answer — this factory
runs whatever the host resolves — so it returns the fallback untouched rather
than probing anything of its own, which is what keeps every repository that
declares no `bin` on exactly the resolution it had before the key existed.

A DECLARED key wins outright, including over an explicit `--fabro-bin`. That
precedence is the one a reader is most likely to want the other way round, so
the reason is recorded rather than left to be inferred: the key states a
COMPATIBILITY constraint, not a preference. An operator naming a different
client for a factory that declares one is naming a client that cannot speak to
that factory's server, and the resulting run fails inside the engine rather
than at the flag. An operator who wants a different client points the KEY at
it.

THE GLOBAL LEG IS RESOLVED ONCE AND STAMPED ON `args`. Without that stamp a
per-item factory pin — the ledger's `dispatch_factory`, which binds a target
AFTER the preamble — would have nothing to fall back to but `args.fabro_bin`,
which by then carries the PREVIOUS factory's client; one factory's binary
would reach another factory's server, and the record would look healthy. The
stamp is also what makes a second preamble pass idempotent: the drain runs one
per tick, and a pass that re-read its own write would mistake the
factory-effective client for an operator's flag.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_bin,
)

__all__: list[str] = [
    "factory_effective_fabro_bin",
    "factory_fabro_bin",
    "resolve_dispatch_fabro_bin",
]

# The `args` attribute carrying the GLOBAL resolution, written by
# `resolve_dispatch_fabro_bin` and read by `factory_effective_fabro_bin`. Named
# here, in the module that owns both ends, so the two cannot drift apart.
_GLOBAL_BIN_ATTR = "fabro_bin_global"


def factory_fabro_bin(*, factory: FactoryTarget | None, fallback: str) -> str:
    """The engine client binary driving Fabro calls against `factory`.

    `fallback` is the GLOBAL resolution the caller already has in hand, passed
    in rather than resolved here: this module answers what the factory says,
    and a second global resolution taken at this depth could not be proven to
    agree with the one the dispatch record and the plan already carry.

    `factory` is optional because a caller that never ran the dispatch
    preamble — the needs-attention and standalone reconcile surfaces construct
    their own arguments — has no target to consult, and that is the
    pre-factory behaviour rather than a fault.
    """
    if factory is None or factory.fabro_bin is None:
        return fallback
    return factory.fabro_bin


def resolve_dispatch_fabro_bin(
    *,
    args: argparse.Namespace,
    repo: Path,
    factory: FactoryTarget,
) -> str:
    """The binary this dispatch drives `factory` with, stamping the global leg.

    The global leg is an explicit `--fabro-bin`, else `resolve_fabro_bin`'s
    env / config / home-path precedence; it is stamped on `args` so the
    per-item re-resolution and a second preamble pass both read the one value
    this pass resolved rather than re-deriving one.
    """
    global_bin = _stamped_global_bin(args=args)
    if global_bin is None:
        global_bin = resolve_fabro_bin(cwd=repo)
    setattr(args, _GLOBAL_BIN_ATTR, global_bin)
    return factory_fabro_bin(factory=factory, fallback=global_bin)


def factory_effective_fabro_bin(
    *,
    args: argparse.Namespace,
    factory: FactoryTarget,
) -> str | None:
    """Re-resolve the binary for a factory bound AFTER the dispatch preamble.

    None means there is nothing to re-resolve: this factory declares no `bin`
    and no global leg was ever stamped, which is the shape a caller that never
    ran the preamble has. Leaving `args.fabro_bin` untouched there is the
    pre-factory behaviour rather than a fault.
    """
    global_bin = _stamped_global_bin(args=args)
    if global_bin is None:
        return factory.fabro_bin
    return factory_fabro_bin(factory=factory, fallback=global_bin)


def _stamped_global_bin(*, args: argparse.Namespace) -> str | None:
    """The stamped global leg, else an explicit `--fabro-bin`, else None.

    The stamp is read FIRST: once a preamble pass has run, `args.fabro_bin`
    holds that pass's factory-effective client rather than an operator's flag,
    so reading the flag first would promote one factory's binary to the global
    answer for every factory after it.
    """
    stamped = getattr(args, _GLOBAL_BIN_ATTR, None)
    if isinstance(stamped, str):
        return stamped
    flag = getattr(args, "fabro_bin", None)
    return flag if isinstance(flag, str) else None
