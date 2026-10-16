"""Resolving ONE admission evaluation's session-headroom policy.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "The floor is a committed-only
`dispatcher.session_headroom_floor_percent` (integer from 0 through 100
inclusive, default 20) ... It is NOT declared API-configurable, and is
therefore committed-only"; "The admission horizon is a committed-only
`dispatcher.session_headroom_horizon_minutes` (integer from 0 through 1440
inclusive, default 180)"; and "One assessment per distinct projected credential
per admission evaluation MUST be reused across nodes and candidates sharing
that credential."

BOTH DIALS ARE RESOLVED HERE, ONCE, AND RIDE THE POLICY TOGETHER. The floor
decides on the LEVEL this reading carries and the horizon decides on the
PROJECTION taken from it, so a filter holding one without the other can grade
only half the clause -- and the two are read from one repository at one instant,
which is what keeps a dispatch from being graded against a floor and a horizon
that were never committed together.

THE MEMO LIVES HERE, IN THE POLICY, AND NOT IN THE FILTER. The filter runs once
per NODE against one `PreflightInputs`, so a memo threaded through it would
have to be a caller-owned dictionary every call site remembered to share. A
policy built once per admission evaluation carries the "at most once" guarantee
as a property of the value instead -- and two concurrent evaluations cannot
share one another's reading, because each built its own policy. That is the
same isolation the probe's explicit memo buys, obtained from the value's
lifetime rather than from a convention.

THE CREDENTIAL IS READ AT READ TIME, NOT AT BUILD TIME. The clause asks for the
"exact credential snapshot that the dispatch would project", and the projection
reads the environment, so taking the snapshot when the first candidate actually
needs it is what keeps the two readings of one variable from diverging. It also
means an evaluation that assesses NO covered candidate issues no request at all.

AN UNREADABLE FLOOR RESOLVES TO THE RATIFIED DEFAULT, exactly as the re-probe
cadence does, and that direction is chosen rather than incidental: the default
IS the specification's value, so a malformed dial falls back onto the behaviour
the clause ratifies rather than onto a disabled filter. The refusal is still
available to a caller that wants to report the malformed dial --
`resolve_session_headroom_floor_percent` returns it -- which is why the two are
separate functions.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from returns.io import IOResult
from returns.result import Failure, Result, Success
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
    DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
    SessionHeadroomPolicy,
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    drain_rate_attempted,
    reading_with_drain_rate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    reading_with_projection,
    session_headroom_projection,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    session_headroom_assessment_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_baseline import (
    session_headroom_baseline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_io import (
    read_projected_session_headroom,
)

__all__: list[str] = [
    "SESSION_HEADROOM_FLOOR_PERCENT_KEY",
    "SESSION_HEADROOM_HORIZON_MINUTES_KEY",
    "journal_session_headroom",
    "resolve_session_headroom_floor_percent",
    "resolve_session_headroom_horizon_minutes",
    "session_headroom_policy",
]


class JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


SESSION_HEADROOM_FLOOR_PERCENT_KEY = "session_headroom_floor_percent"
SESSION_HEADROOM_HORIZON_MINUTES_KEY = "session_headroom_horizon_minutes"

_FLOOR_MINIMUM = 0
_FLOOR_MAXIMUM = 100
_HORIZON_MINIMUM_MINUTES = 0
_HORIZON_MAXIMUM_MINUTES = 1440


def resolve_session_headroom_floor_percent(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read the committed floor, bounded to the clause's inclusive 0..100 range.

    The generic integer resolver in `_dispatcher_policy_settings` carries a
    minimum and no maximum, and this dial needs both: a floor above 100 is not
    a strict dial, it is one no reading can ever satisfy, so it would refuse
    every covered candidate in the repository forever.
    """
    return read_dispatcher_config_value(
        cwd=cwd, key=SESSION_HEADROOM_FLOOR_PERCENT_KEY
    ).bind_result(
        lambda value: _bounded_dial(
            value=value,
            setting=SESSION_HEADROOM_FLOOR_PERCENT_KEY,
            default=DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
            minimum=_FLOOR_MINIMUM,
            maximum=_FLOOR_MAXIMUM,
        )
    )


def resolve_session_headroom_horizon_minutes(
    *, cwd: Path
) -> IOResult[int, PolicySettingUnreadable]:
    """Read the committed horizon, bounded to the clause's inclusive 0..1440 range.

    The SECOND dial that needs a maximum as well as a minimum, and it needs one
    for the mirror-image reason the floor does: an unbounded horizon is not a
    stricter dial, it is one no projected exhaustion can ever fall outside, so a
    committed 4000 would refuse every covered candidate whose drain is
    measurable at all -- while reading, in the record, exactly like a horizon
    somebody chose.

    COMMITTED-ONLY, as the clause ratifies it, so -- like the floor -- it is
    deliberately NOT a member of `_drive_config_schema.CONFIG_KEYS`. That
    manifest is what makes a setting reachable over the `drive --action
    set-config` write surface, so the absent declaration IS the mechanism
    rather than a documentation choice.
    """
    return read_dispatcher_config_value(
        cwd=cwd, key=SESSION_HEADROOM_HORIZON_MINUTES_KEY
    ).bind_result(
        lambda value: _bounded_dial(
            value=value,
            setting=SESSION_HEADROOM_HORIZON_MINUTES_KEY,
            default=DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
            minimum=_HORIZON_MINIMUM_MINUTES,
            maximum=_HORIZON_MAXIMUM_MINUTES,
        )
    )


def session_headroom_policy(
    *,
    repo: Path,
    now_iso: str,
    journal_path: Path | None,
    read: Callable[..., SessionHeadroomReading] = read_projected_session_headroom,
) -> SessionHeadroomPolicy:
    """This evaluation's two dials plus its at-most-once reading of the projection.

    `journal_path` is the history the DRAIN RATE is measured against, and it is
    a required parameter rather than a defaulted one: `None` is the honest
    answer for a caller holding no journal, and a default would let a caller
    that simply forgot to thread it through report no rate for every dispatch
    forever -- a record that reads exactly like a checkout with no history. It
    is PASSED rather than derived from `repo` because `dispatcher.py` accepts a
    `--journal` override, so a re-derived path can name a different file from
    the one this pass appends to.

    The baseline is read INSIDE the memo, so an evaluation that assesses no
    covered candidate touches the journal no more than it spends a request --
    and the PROJECTION is taken there too, which is what makes "The projection
    MUST be computed only from journaled assessments and MUST NOT issue any
    usage request beyond the one bounded reading this clause already requires"
    a property of the memo rather than a second guarantee to maintain.
    """
    floor = unsafe_perform_io(
        resolve_session_headroom_floor_percent(cwd=repo).value_or(
            DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT
        )
    )
    horizon = unsafe_perform_io(
        resolve_session_headroom_horizon_minutes(cwd=repo).value_or(
            DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES
        )
    )
    taken: list[SessionHeadroomReading] = []

    def read_once() -> SessionHeadroomReading:
        if not taken:
            reading = read(token=_projected_token(), observed_at=now_iso)
            taken.append(
                _assessed(
                    reading=reading,
                    floor_percent=floor,
                    horizon_minutes=horizon,
                    journal_path=journal_path,
                    now_iso=now_iso,
                )
            )
        return taken[0]

    return SessionHeadroomPolicy(floor_percent=floor, horizon_minutes=horizon, read=read_once)


def _assessed(
    *,
    reading: SessionHeadroomReading,
    floor_percent: int,
    horizon_minutes: int,
    journal_path: Path | None,
    now_iso: str,
) -> SessionHeadroomReading:
    """This reading, carrying its drain rate and its ONE projection result.

    THE NOT-ATTEMPTED TEST RUNS BEFORE THE JOURNAL READ, and that order is the
    behaviour rather than an optimization. The clause distinguishes a
    `not-projected` reading -- one the floor settled -- from an `unavailable`
    projection that was attempted and found no baseline, and reading the
    history on a reading the floor already settled is what makes the two
    indistinguishable from the outside: both would end at a null rate, one of
    them having spent a file read per admission pass to establish an absence
    nothing was waiting on.

    THE BASELINE IS READ ONCE AND SPENT TWICE, which is why it is bound to a
    local rather than asked for again by the projection. The rate and the
    projection are two readings OF ONE HISTORY, so a second `session_headroom_
    baseline` call would re-read a journal that concurrent passes append to --
    and a rate measured against one baseline while the projection named another
    is a record whose own two halves disagree.

    THE RESULT IS ALWAYS ATTACHED, including on the arm that computes no rate:
    `not-projected` IS a result, and the clause requires exactly one on every
    assessed credential. A reading that left the field null there would make an
    operator's disabled dial indistinguishable from a build that does not
    project at all.
    """
    baseline = (
        session_headroom_baseline(
            journal_path=journal_path,
            credential_identity=reading.credential_identity,
            now_iso=now_iso,
        )
        if drain_rate_attempted(reading=reading, floor_percent=floor_percent)
        else None
    )
    rated = reading_with_drain_rate(reading=reading, baseline=baseline)
    return reading_with_projection(
        reading=rated,
        projection=session_headroom_projection(
            reading=rated,
            baseline=baseline,
            floor_percent=floor_percent,
            horizon_minutes=horizon_minutes,
        ),
    )


def _projected_token() -> str | None:
    """The token the dispatch would project: the caam-selected slot, else unnumbered.

    The same selector the projection and the usability probe call, so all three
    name ONE account (`bd-ib-nzp5ln`: reading the unnumbered variable here
    assessed anthropic-1 while the projection billed anthropic-3).
    """
    choice = select_factory_credential(
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: sys.stderr.write(f"livespec-dispatch: {message}\n"),
    )
    return os.environ.get(choice.env_name)


def _bounded_dial(
    *, value: object, setting: str, default: int, minimum: int, maximum: int
) -> Result[int, PolicySettingUnreadable]:
    """One declared dial, or the refusal naming the range it fell outside.

    ONE grader for both dials rather than one apiece. They differ only in their
    bounds, and a second hand-rolled copy is how two dials written from the same
    clause come to disagree about whether "inclusive" includes its endpoints --
    which is exactly the boundary the clause states twice and an almost-correct
    implementation moves.
    """
    if value is None:
        return Success(default)
    if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum:
        return Success(value)
    return Failure(
        PolicySettingUnreadable(
            setting=setting,
            detail=(
                f"dispatcher.{setting} must be an integer from "
                f"{minimum} through {maximum} inclusive; got {value!r}"
            ),
        )
    )


def journal_session_headroom(
    *, work_item_id: str, verdict: AcpPreflightVerdict, journal: JournalWriter
) -> None:
    """Record this evaluation's readings against ONE affected work-item.

    TWO things make this a no-op rather than an empty row, and they are
    different conditions. A verdict carrying NO floor was resolved without a
    policy -- wait attention, idle-factory, the legacy no-fallback path -- so no
    reading was ever attempted and there is nothing to report. A verdict
    carrying a floor but NO assessments assessed no covered candidate, which is
    every dispatch in a repository routed wholly away from Claude; a row per
    item per pass there would be journal noise naming nothing.

    A floor of ZERO is neither of those: the reading is still attempted and
    still journaled, which is why the guard tests the floor for `None` rather
    than for falsity.
    """
    floor = verdict.session_headroom_floor_percent
    if floor is None or not verdict.headroom_assessments:
        return
    journal.append(
        record=session_headroom_assessment_record(
            work_item_id=work_item_id,
            floor_percent=floor,
            assessments=verdict.headroom_assessments,
            nodes=verdict.nodes,
        )
    )
