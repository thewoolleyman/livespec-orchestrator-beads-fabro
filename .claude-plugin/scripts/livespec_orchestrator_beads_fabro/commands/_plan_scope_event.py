"""Author ordinary plan scope events and recorded continuation rulings.

A continuation ruling shares the plan timeline with ordinary requirement and
deferral events, but it never carries a carrier map.  Its attended marker is
rendered here after every caller-provided field, so a caller cannot manufacture
the evidence that the ruling was recorded by an attended session.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import (
    carrier_map_block,
    guard_carrier_map,
)
from livespec_orchestrator_beads_fabro.commands._plan_continuation import (
    AUTHORIZED_PREFIX,
    REVOKED_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    is_unattended_session,
    plan_comment_body,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "PlanContinuationAuthorization",
    "PlanContinuationRefusal",
    "PlanContinuationRevocation",
    "PlanContinuationWrite",
    "ScopeEventWrite",
    "write_scope_event",
]


@dataclass(frozen=True, kw_only=True)
class PlanContinuationAuthorization:
    """The maintainer fields of an attended continuation authorization."""

    until: str
    by: str
    directive: str


@dataclass(frozen=True, kw_only=True)
class PlanContinuationRevocation:
    """A maintainer revocation of the latest continuation authorization."""

    by: str


PlanContinuationWrite = PlanContinuationAuthorization | PlanContinuationRevocation


@dataclass(frozen=True, kw_only=True)
class PlanContinuationRefusal:
    """Why the primitive refused to write a continuation ruling."""

    detail: str


@dataclass(frozen=True, kw_only=True)
class ScopeEventWrite:
    """All inputs to one scope-event write across the public module boundary."""

    config: StoreConfig
    epic_id: str
    requirements: tuple[str, ...]
    deferrals: tuple[str, ...]
    author: str
    now: str
    carriers: tuple[str, ...]
    continuation: PlanContinuationWrite | None


def write_scope_event(*, request: ScopeEventWrite) -> PlanContinuationRefusal | None:
    """Write one scope event, or return an expected continuation refusal."""
    continuation = request.continuation
    if continuation is not None:
        refusal = _continuation_refusal(
            request=request,
            continuation=continuation,
        )
        if refusal is not None:
            return refusal
        body = _continuation_body(continuation=continuation)
    else:
        body = _scope_body(
            requirements=request.requirements,
            deferrals=request.deferrals,
            carriers=request.carriers,
        )
    client = make_beads_client(config=request.config)
    if continuation is None:
        guard_carrier_map(
            epic_id=request.epic_id,
            description=_epic_description(client=client, epic_id=request.epic_id),
            carriers=request.carriers,
        )
    client.add_comment(
        issue_id=request.epic_id,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author=request.author,
            now=request.now,
            body=body,
        ),
    )
    return None


def _continuation_refusal(
    *,
    request: ScopeEventWrite,
    continuation: PlanContinuationWrite,
) -> PlanContinuationRefusal | None:
    if is_unattended_session(env=os.environ):
        return PlanContinuationRefusal(
            detail="an unattended plan session cannot record a continuation ruling"
        )
    if request.carriers:
        return PlanContinuationRefusal(detail="a continuation ruling is never a carrier-map event")
    values = (
        (continuation.until, continuation.by, continuation.directive)
        if isinstance(continuation, PlanContinuationAuthorization)
        else (continuation.by,)
    )
    if not all(value.splitlines() == [value] for value in values):
        return PlanContinuationRefusal(
            detail="continuation ruling fields must each occupy exactly one line"
        )
    return None


def _continuation_body(*, continuation: PlanContinuationWrite) -> str:
    if isinstance(continuation, PlanContinuationAuthorization):
        return (
            f"{AUTHORIZED_PREFIX}\n"
            f"until: {continuation.until}\n"
            f"by: {continuation.by}\n"
            f"directive: {continuation.directive}\n"
            "recorded-attended: true"
        )
    return f"{REVOKED_PREFIX}\nby: {continuation.by}"


def _epic_description(*, client: BeadsClient, epic_id: str) -> str:
    """One epic's description, tolerating the key's absence."""
    record = client.show_issue(issue_id=epic_id)
    description = record.get("description")
    return description if isinstance(description, str) else ""


def _scope_body(
    *, requirements: tuple[str, ...], deferrals: tuple[str, ...], carriers: tuple[str, ...]
) -> str:
    requirement_lines = "\n".join(f"- {requirement}" for requirement in requirements)
    deferral_lines = "\n".join(f"- {deferral}" for deferral in deferrals)
    body = f"Requirement carriers:\n{requirement_lines}\n\nExplicit deferrals:\n{deferral_lines}"
    block = carrier_map_block(carriers=carriers)
    return f"{body}\n\n{block}" if block else body
