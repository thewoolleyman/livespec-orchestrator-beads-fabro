"""The bounded five-hour session-usage read, and the gate it resolves into.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance" -> "Admission filters candidates by projected Claude
session headroom": the Dispatcher "MUST read the provider's five-hour session
utilization using the exact credential snapshot that the dispatch would
project", and "the usage request MUST have a finite implementation-defined
timeout".

THE CREDENTIAL COMES FROM THE SAME SELECTION THE DISPATCH PROJECTS, through
`select_factory_credential` and the env var it names, which is what makes "the
exact credential snapshot that the dispatch would project" a fact about the code
rather than a convention two readers keep. Reading some other variable would
produce a perfectly healthy reading of an allowance no run was going to spend --
a clean, plausible, wrong answer with no error anywhere.

EVERY TRANSPORT FAULT IS UNOBSERVABLE, NEVER A NUMBER. A refused connection, a
timeout, a non-JSON body and an unparseable figure all resolve to an explicit
unobservable reading, because the alternative -- substituting a utilization --
would report full headroom for a provider nothing was heard from and admit the
run the filter exists to hold. The ONE discrimination the transport makes is
authentication: a 401 is reported as its own unobservable result, since the
remedy is the credential rather than the network.

NOTHING HERE DECIDES ANYTHING. The reading and the floor travel together as a
`SessionHeadroomGate` value, and the grading lives on that value in
`_acp_session_headroom`; an unreadable floor rides the setting's documented
default through `.value_or`, exactly as every other `dispatcher.*` consumer
resolves one.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    UNOBSERVABLE_AUTHENTICATION,
    UNOBSERVABLE_TRANSPORT,
    SessionHeadroomGate,
    SessionHeadroomReading,
    classify_session_utilization,
    credential_identity,
    unobservable_session_reading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
    resolve_session_headroom_floor_percent,
)

__all__: list[str] = [
    "CLAUDE_SESSION_USAGE_TIMEOUT_SECONDS",
    "CLAUDE_SESSION_USAGE_URL",
    "live_session_headroom_gate",
    "read_claude_session_headroom",
]

# The subscription usage endpoint, and the finite timeout the clause requires.
# The timeout matches the admission credential probe's own bound: both are
# pre-claim host reads whose whole purpose is to answer before a sandbox is
# launched, so a slower one would delay every dispatch to no end.
CLAUDE_SESSION_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_SESSION_USAGE_TIMEOUT_SECONDS = 20.0

_CLAUDE_OAUTH_BETA = "oauth-2025-04-20"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_RESPONSE_BYTES = 65_536
_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401
_FIVE_HOUR_KEY = "five_hour"
_UTILIZATION_KEY = "utilization"


@dataclass(frozen=True, kw_only=True)
class _AuthenticationFault:
    """The ONE transport answer that names the credential, not the network.

    It is a distinct VALUE rather than another `None`, because the two owe
    different remedies: a refused connection is the network and a rejected
    token is the credential. Folding both into "no body" would report a revoked
    subscription token as a transport blip, and the operator would retry rather
    than rotate.
    """


def read_claude_session_headroom(*, token: str, observed_at: str) -> SessionHeadroomReading:
    """Read the five-hour utilization of ONE exact credential snapshot.

    The identity is computed from the token that was actually read, BEFORE any
    request is made, so even a reading that never reaches the provider still
    names the snapshot it was about.
    """
    identity = credential_identity(token=token)
    payload = _usage_payload(token=token)
    fault = _transport_fault(payload=payload)
    if fault is not None:
        return unobservable_session_reading(
            credential_identity=identity, observed_at=observed_at, reason=fault
        )
    return classify_session_utilization(
        value=_five_hour_utilization(payload=payload),
        credential_identity=identity,
        observed_at=observed_at,
    )


def _transport_fault(*, payload: object) -> str | None:
    """The unobservable result this transport answer reports under, if any."""
    if isinstance(payload, _AuthenticationFault):
        return UNOBSERVABLE_AUTHENTICATION
    if payload is None:
        return UNOBSERVABLE_TRANSPORT
    return None


def live_session_headroom_gate(*, repo: Path) -> SessionHeadroomGate | None:
    """The reading and floor this host's projected credential resolves to.

    `None` says NO covered credential is projected at all, which is the absence
    of a SUBJECT rather than an unobservable reading: with no token there is no
    snapshot to assess, and minting an unobservable reading for one would skip
    every covered candidate on a condition the dispatch path's own
    absent-credential refusal already reports with a remedy.
    """
    choice = select_factory_credential(
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: sys.stderr.write(f"livespec-dispatch: {message}\n"),
    )
    token = os.environ.get(choice.env_name, "")
    if token == "":
        return None
    floor = unsafe_perform_io(
        resolve_session_headroom_floor_percent(cwd=repo).value_or(
            DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT
        )
    )
    reading = read_claude_session_headroom(token=token, observed_at=utc_now_iso())
    return SessionHeadroomGate(reading=reading, floor=floor)


def _usage_payload(*, token: str) -> object:
    """One bounded GET against the usage endpoint, as data rather than a raise.

    Three answers, and the caller discriminates them by TYPE: the decoded body,
    an `_AuthenticationFault` for a rejected token, and `None` for every other
    fault. Nothing raises past this function, so a provider outage is a journaled
    unobservable reading rather than a crashed admission pass.
    """
    request = _usage_request(token=token)
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
            request,
            timeout=CLAUDE_SESSION_USAGE_TIMEOUT_SECONDS,
        ) as response:
            if response.status != _HTTP_OK:
                return None
            return _json_object(body=response.read(_MAX_RESPONSE_BYTES))
    except HTTPError as error:
        return _AuthenticationFault() if error.code == _HTTP_UNAUTHORIZED else None
    except (OSError, TimeoutError, URLError):
        return None


def _usage_request(*, token: str) -> Request:
    return Request(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
        CLAUDE_SESSION_USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": _CLAUDE_OAUTH_BETA,
            "anthropic-version": _ANTHROPIC_VERSION,
        },
        method="GET",
    )


def _five_hour_utilization(*, payload: object) -> object:
    """The `five_hour.utilization` figure, or `None` when the body has none.

    A body whose five-hour node is ABSENT or is not an object yields `None`,
    which the classifier reports as the `missing` unobservable result. A
    present-but-null figure is deliberately NOT distinguished from it: both say
    the provider told us nothing about this window, and two tokens for one
    observation would imply a discrimination nothing downstream can act on.
    """
    if not isinstance(payload, dict):
        return None
    window = cast("dict[str, object]", payload).get(_FIVE_HOUR_KEY)
    if not isinstance(window, dict):
        return None
    return cast("dict[str, object]", window).get(_UTILIZATION_KEY)


def _json_object(*, body: bytes) -> object:
    """The decoded body, or the empty object when it does not decode.

    The empty object carries no five-hour window, so an undecodable body reaches
    the classifier as `missing` rather than as a fault of its own: nothing was
    heard about the window either way, and the transport did answer.
    """
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
