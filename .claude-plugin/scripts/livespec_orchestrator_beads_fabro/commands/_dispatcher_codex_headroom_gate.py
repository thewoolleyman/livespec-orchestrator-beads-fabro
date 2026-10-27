"""Resolving ONE admission evaluation's Codex usage-window policy.

`SPECIFICATION/contracts.md` section "Provider spend containment", the
paragraph "Admission filters Codex candidates by projected usage-window
headroom": "The committed `dispatcher.session_headroom_floor_percent` and
`dispatcher.session_headroom_horizon_minutes` govern this clause; it introduces
no configuration key of its own", and "For each distinct projected Codex
credential per admission evaluation, the Dispatcher MUST issue exactly one
bounded usage read ... and MUST reuse that one reading across every node and
candidate sharing the credential."

BOTH DIALS ARE THE CLAUDE CLAUSE'S OWN, RESOLVED THROUGH ITS OWN RESOLVERS.
That is the clause in as many words, and reaching for those two functions rather
than re-reading the two keys is what makes it true: a second reader of one
committed integer is how two clauses governed by one dial come to disagree about
what an out-of-range value means, after which an operator who switched the brake
off still has dispatches refused by the provider they had not configured.

THE MEMO LIVES HERE, IN THE POLICY, AND NOT IN THE FILTER, for the reason its
Claude sibling records: the filter runs once per NODE, so a memo threaded
through it would be a caller-owned dictionary every call site remembered to
share. A policy built once per admission evaluation carries the "exactly one
bounded read" guarantee as a property of the value every node is filtered
against -- and two concurrent evaluations cannot share one another's reading,
because each built its own policy.

THE CREDENTIAL IS READ AT READ TIME, NOT AT BUILD TIME. The clause reads "the
credential the dispatch would project", and that snapshot is a host file the
dispatch resolves for itself, so taking it when the first covered candidate
actually needs it is what keeps the two readings of one file from diverging. It
also means an evaluation that assesses NO covered candidate issues no request
and opens no file at all -- which is what keeps wait attention and idle-factory
reaching no provider.

THE SNAPSHOT IS READ THROUGH THE SAME HOST READER EVERY OTHER CODEX SURFACE
USES. `read_host_codex_auth` is the one resolver of that path, so the credential
this clause assesses is the credential the overlay projects. A second reader
would be the second authority on where the host credential lives, and the
fingerprint it produced would not join to the one any other surface reports.

AN UNREADABLE HOST CREDENTIAL IS AN UNOBSERVABLE READING, NOT A REFUSAL, and
the direction is the clause's: an unobservable reading is a floor skip under a
positive floor and is admitted under a floor of 0, and either way it is
journaled as unobservable. Raising here would convert a missing `codex login`
into a crash inside an admission pass whose other providers are fine.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexHeadroomPolicy,
    CodexUsageReading,
)
from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom_projection import (
    codex_projections_attempted,
    codex_window_projections,
    reading_with_codex_projections,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
    DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    read_host_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_headroom_baseline import (
    codex_window_baselines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_headroom_io import (
    read_projected_codex_usage,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_gate import (
    resolve_session_headroom_floor_percent,
    resolve_session_headroom_horizon_minutes,
)

__all__: list[str] = [
    "codex_headroom_policy",
]


def codex_headroom_policy(
    *,
    repo: Path,
    now_iso: str,
    journal_path: Path | None,
    read: Callable[..., CodexUsageReading] = read_projected_codex_usage,
    auth: Callable[[], str | None] = read_host_codex_auth,
) -> CodexHeadroomPolicy:
    """This evaluation's two dials plus its at-most-once reading of the snapshot.

    `journal_path` is the history the per-window drain rates are measured
    against, and it is a required parameter rather than a defaulted one for the
    reason its Claude sibling's is: `None` is the honest answer for a caller
    holding no journal, and a default would let a caller that simply forgot to
    thread it through report no rate for every dispatch forever -- a record that
    reads exactly like a checkout with no history.

    The baselines are read INSIDE the memo, so an evaluation that assesses no
    covered candidate touches the journal no more than it spends a request --
    and the projection is taken there too, which makes "computed only from
    journaled assessments" a property of the memo rather than a second
    guarantee to maintain.
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
    taken: list[CodexUsageReading] = []

    def read_once() -> CodexUsageReading:
        if not taken:
            reading = read(auth_json=auth(), observed_at=now_iso)
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

    return CodexHeadroomPolicy(floor_percent=floor, horizon_minutes=horizon, read=read_once)


def _assessed(
    *,
    reading: CodexUsageReading,
    floor_percent: int,
    horizon_minutes: int,
    journal_path: Path | None,
    now_iso: str,
) -> CodexUsageReading:
    """This reading, carrying exactly one projection result per window.

    THE NOT-ATTEMPTED TEST RUNS BEFORE THE JOURNAL READ, and that order is the
    behaviour rather than an optimization. The clause distinguishes a
    `not-projected` reading -- one the dial, the floor or the provider's own
    refusal settled -- from an `unavailable` projection that was attempted and
    found no baseline, and reading the history for a reading already settled is
    what makes the two indistinguishable from the outside: both end at a null
    rate, one of them having spent a file read per admission pass to establish
    an absence nothing was waiting on.

    THE BASELINES ARE KEYED ON THE WINDOW LENGTHS THIS READING ACTUALLY CARRIES,
    so a credential reporting one window costs one history walk and one
    reporting two costs two -- and a window length the reading does not carry is
    never looked for at all.

    THE RESULT IS ALWAYS ATTACHED, including on the arm that computes no rate:
    `not-projected` IS a result, and the clause requires exactly one per window
    (or once, where no window is valid) on every assessed credential.
    """
    baselines = (
        codex_window_baselines(
            journal_path=journal_path,
            credential_identity=reading.credential_identity,
            window_seconds=tuple(window.limit_window_seconds for window in reading.windows),
            now_iso=now_iso,
        )
        if codex_projections_attempted(reading=reading, floor_percent=floor_percent)
        else {}
    )
    return reading_with_codex_projections(
        reading=reading,
        projections=codex_window_projections(
            reading=reading,
            baselines=baselines,
            floor_percent=floor_percent,
            horizon_minutes=horizon_minutes,
        ),
    )
