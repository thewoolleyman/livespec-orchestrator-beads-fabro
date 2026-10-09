"""READING a factory's advertised capability list, for the gate that needs it.

The IMPURE half of `_acp_capability_gate`, kept apart from it for the reason
every seam in this tree is: the gate's decision is a pure function of a
capability set, and a decision that reached for the network itself could not be
exercised without one. What crosses the boundary is a CALLABLE returning
`frozenset[str] | None`, so the gate consults it only when it has something to
gate, and a test supplies a set directly.

`None` MEANS "COULD NOT ESTABLISH", NOT "EMPTY". The distinction is the whole
value of the type: an empty set is a server that answered and advertises
nothing, while `None` is a server that did not answer, answered with something
unreadable, or was never named. The gate treats both as "not advertised" --
fail closed -- but it says WHICH in its refusal, because the remedies differ.

THE READ IS MEMOIZED PER DISPATCH. One dispatch asks once however many nodes
carry options; the closure caches the first answer. That is safe here because
the question is about a server BUILD, which does not change inside one
dispatch, and it keeps a multi-node chain from issuing one round trip per node.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpTransport,
    UrllibFabroHttpTransport,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget

__all__: list[str] = [
    "factory_capability_reader",
]

_CAPABILITIES_KEY = "capabilities"
_TIMEOUT_SECONDS = 10.0


def factory_capability_reader(
    *,
    factory: FactoryTarget | None,
    transport: FabroHttpTransport | None = None,
) -> Callable[[], frozenset[str] | None]:
    """A memoized reader of one factory's advertised capabilities.

    A factory that is `None`, or that carries no server url, reads as `None`
    without any request: there is no host to ask, which is a different thing
    from a host that declined to answer only in the message the gate prints.
    """
    sender = UrllibFabroHttpTransport() if transport is None else transport
    cached: list[frozenset[str] | None] = []

    def read() -> frozenset[str] | None:
        if not cached:
            cached.append(_capabilities(factory=factory, transport=sender))
        return cached[0]

    return read


def _capabilities(
    *, factory: FactoryTarget | None, transport: FabroHttpTransport
) -> frozenset[str] | None:
    """One `GET /system/info` read, or `None` when it cannot be established.

    The read goes through the Fabro facade's own server-API face rather than
    the transport function beneath it, so this module names no Fabro route and
    sends no request of its own — the single-seam rule the Enemy Unit Test
    suite's evidence depends on.
    """
    if factory is None or factory.server is None:
        return None
    result = FabroHttpPort(
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        transport=transport,
    ).system_info(timeout_seconds=_TIMEOUT_SECONDS)
    if not result.succeeded:
        return None
    return _declared(payload=result.payload)


def _declared(*, payload: object) -> frozenset[str] | None:
    """The advertised strings, or `None` when the answer carries no list.

    Takes `object` and narrows HERE so the shape check lives in one place. A
    payload with NO `capabilities` key is `None` rather than the empty set: a
    server that never mentions capabilities has not told us it lacks one, it
    has told us nothing, and reporting an empty set would make an older server
    indistinguishable from one that answered "none".
    """
    if not isinstance(payload, dict):
        return None
    raw = cast("dict[str, object]", payload).get(_CAPABILITIES_KEY)
    if not isinstance(raw, list):
        return None
    advertised = cast("list[object]", raw)
    return frozenset(item for item in advertised if isinstance(item, str))
