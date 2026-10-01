"""Reading a factory's advertised capability list, through a stubbed transport.

The IMPURE half of the gate bound by `test_acp_capability_gate`: that module
grades the DECISION against a capability set handed to it, and this one grades
how the set is obtained. They are separate for the reason they are separate in
the product tree -- a decision that reached for the network itself could not be
exercised without one.

`None` IS A DISTINCT ANSWER FROM THE EMPTY SET, and most of these cases exist to
hold that line. An empty set is a server that answered and advertises nothing; a
`None` is a server that was never named, could not be reached, answered
something unreadable, or answered without mentioning capabilities at all. The
gate treats both as "not advertised" and FAILS CLOSED on either, so collapsing
them here would not change today's verdict -- it would destroy the operator's
only clue about which remedy applies, which is the one thing the refusal is for.

EVERY CASE DRIVES A STUBBED TRANSPORT AND NOTHING LEAVES THE PROCESS. The
transport is the seam the product module already takes, so these exercise the
real request construction, the real success test and the real payload
narrowing, with only the socket replaced.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_CAPABILITY = "acp.candidate_config_options.v1"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _result(*, succeeded: bool = True, payload: object = None, status: int = 200) -> Any:
    """One exchange, with the payload carried as BODY TEXT.

    `fabro_http_request` re-derives `payload` by parsing `body`, so a stub that
    set `payload` directly would have its value discarded and every case would
    read as an unparseable answer -- a stub that cannot produce the state the
    test is about.
    """
    types = _module(name="_fabro_port_http")
    body = "" if payload is None else json.dumps(payload)
    return types.FabroHttpResult(
        status=status, body=body, error=None, payload=None, succeeded=succeeded
    )


@dataclass(kw_only=True)
class _Transport:
    """A recording stand-in for the ONE seam a request leaves through."""

    result: Any
    urls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> Any:
        _ = (method, headers, body, timeout_seconds)
        self.urls.append(url)
        return self.result


def _factory(*, server: str | None = _SERVER) -> Any:
    return _module(name="_config").FactoryTarget(name="hp", server=server, dev_token=None)


def _reader(*, factory: Any, transport: Any) -> Any:
    return _module(name="_acp_factory_capabilities").factory_capability_reader(
        factory=factory, transport=transport
    )


def test_an_advertised_list_reads_as_the_set_of_its_strings() -> None:
    """The happy path, and the request goes to the system-info route."""
    transport = _Transport(
        result=_result(payload={"capabilities": ["acp.fallback_chain.v1", _CAPABILITY]})
    )

    advertised = _reader(factory=_factory(), transport=transport)()

    assert advertised == frozenset({"acp.fallback_chain.v1", _CAPABILITY})
    assert transport.urls == [f"{_SERVER}/api/v1/system/info"]


def test_a_factory_with_no_server_reads_as_unobservable_without_a_request() -> None:
    """There is no host to ask, so nothing is asked."""
    transport = _Transport(result=_result())

    assert _reader(factory=_factory(server=None), transport=transport)() is None
    assert transport.urls == []


def test_no_factory_at_all_reads_as_unobservable_without_a_request() -> None:
    """The non-dispatching entry points reach the gate with no factory pinned."""
    transport = _Transport(result=_result())

    assert _reader(factory=None, transport=transport)() is None
    assert transport.urls == []


def test_a_failed_exchange_reads_as_unobservable_rather_than_as_empty() -> None:
    """An unreachable factory has told us nothing, not that it has nothing."""
    transport = _Transport(result=_result(succeeded=False, status=0))

    assert _reader(factory=_factory(), transport=transport)() is None


def test_an_answer_carrying_no_capabilities_key_reads_as_unobservable() -> None:
    """An older server that never mentions capabilities is not an empty one."""
    transport = _Transport(result=_result(payload={"version": "0.254.0"}))

    assert _reader(factory=_factory(), transport=transport)() is None


def test_a_non_object_answer_reads_as_unobservable() -> None:
    """A body that parsed but is not an object carries no capability list."""
    transport = _Transport(result=_result(payload=["acp.fallback_chain.v1"]))

    assert _reader(factory=_factory(), transport=transport)() is None


def test_an_explicitly_empty_list_reads_as_the_empty_set() -> None:
    """The discriminator: a server that DID answer "none" is not unobservable.

    Without this case every other one here is equally consistent with a reader
    that returns `None` for everything, and the gate's two refusal messages
    would be one message with a coin flip in front of it.
    """
    transport = _Transport(result=_result(payload={"capabilities": []}))

    assert _reader(factory=_factory(), transport=transport)() == frozenset()


def test_non_string_entries_are_dropped_rather_than_failing_the_read() -> None:
    """A malformed entry costs that entry, not the whole answer."""
    transport = _Transport(result=_result(payload={"capabilities": [_CAPABILITY, 7, None]}))

    assert _reader(factory=_factory(), transport=transport)() == frozenset({_CAPABILITY})


def test_the_read_is_memoized_across_calls() -> None:
    """One dispatch asks once, however many nodes carry options."""
    transport = _Transport(result=_result(payload={"capabilities": [_CAPABILITY]}))
    read = _reader(factory=_factory(), transport=transport)

    first = read()
    second = read()

    assert first == second == frozenset({_CAPABILITY})
    assert len(transport.urls) == 1
