"""Shared pieces of the wait telemetry event builders.

The lifecycle publisher and the inventory builder describe the same wait in the
same vocabulary, so the identity an event carries, the opaque target digest and
the observation signature live here once. A second copy would let a target be
digested one way when it is armed and another when it is inventoried, and the
two views of one wait would stop joining.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import (
    SessionEvent,
    session_event,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitTarget,
)

__all__: list[str] = [
    "Subject",
    "build_event",
    "digest",
    "observation_signature",
    "target_attributes",
]

_DIGEST_DIGITS = 16


@dataclass(frozen=True, kw_only=True)
class Subject:
    """Whose event this is: the wait's identity and the associations known for it."""

    repository: str | None
    session_id: str | None
    wait_id: str | None
    associations: dict[str, str]


def digest(*, text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_DIGEST_DIGITS]


def _repository_name(*, repository: str) -> str:
    return Path(repository).name or repository


def target_attributes(*, target: WaitTarget) -> dict[str, object | None]:
    return {
        "session.wait.target.kind": target.kind,
        "session.wait.target.id": digest(text=target.identity),
    }


def observation_signature(*, observation: GateObservation) -> str:
    return f"{observation.state}|{observation.exit_code}|{observation.fresh}"


def build_event(
    *, name: str, at: float, subject: Subject, attributes: dict[str, object | None]
) -> SessionEvent:
    """One catalog event for a wait, under that wait's stable trace."""
    repository_name = (
        None if subject.repository is None else _repository_name(repository=subject.repository)
    )
    identity: dict[str, object | None] = {
        "session.repository": repository_name,
        "session.id": subject.session_id,
        "session.wait.id": subject.wait_id,
        **subject.associations,
    }
    return session_event(
        name=name,
        at=at,
        trace_key=f"{repository_name}:{subject.session_id}:{subject.wait_id}",
        attributes={**identity, **attributes},
    )
