"""Tier 0 Enemy Unit Tests for the server's run-files read.

The preservation clause of `SPECIFICATION/contracts.md`'s failed-checkpoint
subsection rests ENTIRELY on this one route. A run whose engine checkpoint
failed left its work in the server's own run directory and nowhere else: no
stage diff artifact carries a failed node's tree, and the terminal patch -- the
only other carrier -- is exactly what is absent in the case the clause exists
for. So `GET /api/v1/runs/<id>/files` is the single point of failure for
recovering about an hour of agent work per incident.

ITS OWN MODULE RATHER THAN A PAIR OF CASES IN
`test_tier0_fabro_port_surface.py`, because that module's concern is the nine
facade verbs that had no enemy coverage as of 2026-10-09 and this is not one of
them: it is the instrument for one ratified clause, and it is the HOST-CAPTURED
assertion of `bd-ib-na2xvm` -- the response SHAPE was unmeasured when the
reader was written, so the reader's parse is deliberately tolerant and this is
what measures what the deployed engine actually serves.

Like its tier 0 siblings this suite sits outside `tests/` so the hermetic
`just check` aggregate never needs a live Fabro server or credentials. Invoke
it explicitly:

    just fabro-enemy-tier0
"""

from __future__ import annotations

from _tier0_support import (
    TIMEOUT_SECONDS,
    _completed_run_id,
    _FabroTier0Config,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import (
    RunFiles,
    RunFilesUnreadable,
    read_run_files,
)

__all__: list[str] = []

_READ_TIMEOUT_SECONDS = 300.0
_CLIENT_ERROR_FLOOR = 400
# A run id the factory cannot hold. It must be a VALID ULID, for the reason
# `test_tier0_fabro_port_surface._ABSENT_RUN_ID` records: a malformed one is
# refused at the edge, before the credential and the run lookup this case
# exists to reach.
_ABSENT_RUN_ID = "01ENEMYTESTABSENTZZZZZZZZZ"


def test_the_run_files_read_returns_a_completed_run_s_changed_files_with_contents(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    """The ONLY route to a checkpoint-failed run's work, driven against this server.

    A run whose engine checkpoint failed left its work in the server's own run
    directory and nowhere else -- no stage diff artifact carries a failed
    node's tree, and the terminal patch is exactly what is absent in that case.
    So the preservation clause rests entirely on this verb, and the parse is
    deliberately tolerant because the response SHAPE was unmeasured when it was
    written. This case is what measures it.

    The assertion is on the PARSE rather than on the status, because a 200
    carrying a shape the reader cannot understand is indistinguishable at the
    preservation seam from a server that declined: both write a ledger comment
    saying the tree was not preserved. The content assertion is what separates
    "the server listed the paths" from "the server returned the bytes", which
    is the whole difference between a publishable tree and a file listing.
    """
    run_id = config.completed_run_id or _completed_run_id(port=port)

    read = read_run_files(
        port=port.server_api(),
        run_id=run_id,
        timeout_seconds=_READ_TIMEOUT_SECONDS,
    )

    assert isinstance(read, RunFiles), read
    assert read.files, f"the run-files read for {run_id} named no changed file"
    # At least one file must carry BYTES. A response listing every path with no
    # content parses, and would publish a tree of empty files.
    assert any(
        changed.content for changed in read.files
    ), f"the run-files read for {run_id} returned {len(read.files)} path(s) and no content"


def test_the_run_files_read_of_a_run_the_factory_does_not_hold_is_unreadable(
    *,
    port: FabroPort,
) -> None:
    """The other half of the same promise, and it must REACH the server.

    An unreadable read is what makes the preservation comment say the tree was
    not preserved, so the reader must not report that for a request the server
    never considered. The VERB is driven on its own first, because only the raw
    exchange carries the discriminator: a status of 0 is this port's own "no
    response arrived", which is what a wrong host, a dead proxy or an
    unresolvable name produces, and the reader folds it into the same prose a
    genuine refusal gets. The reader's verdict is then asserted beside it, so
    the case covers both the transport and the reading it feeds.
    """
    face = port.server_api()

    result = face.run_files(run_id=_ABSENT_RUN_ID, timeout_seconds=TIMEOUT_SECONDS)

    assert not result.succeeded
    assert result.status >= _CLIENT_ERROR_FLOOR, f"status {result.status}: {result.error}"

    read = read_run_files(port=face, run_id=_ABSENT_RUN_ID, timeout_seconds=TIMEOUT_SECONDS)

    assert isinstance(read, RunFilesUnreadable), read
    assert _ABSENT_RUN_ID in read.detail
    assert str(result.status) in read.detail
