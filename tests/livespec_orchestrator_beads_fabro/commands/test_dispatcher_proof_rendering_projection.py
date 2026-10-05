"""The measured proof-asset rendering's trip from the dispatch journal to the sandbox.

`SPECIFICATION/contracts.md`'s Proof-of-Done-record clause waives the inline half
of the requirement only where no API-drivable store satisfies it FOR A
REPOSITORY. The pre-dispatch gate measures that per repository and journals it;
until this slice the sandbox received only two of the three projected keys, so a
PUBLIC repository's record rendered its images as authenticated links -- outside
the ratified text, because the measured release-assets store does satisfy the
inline half there.

WHAT THESE TESTS BIND, and why each half needs its own case. The projection must
carry the measurement, AND it must stay pure: `proof_store_env_lines` is reached
from the run-config overlay, which every dispatch materializes and which the
hermetic tier exercises with no network at all. An earlier draft probed the forge
from inside it and spawned a real `gh` in 104 otherwise sealed tests. So the value
travels through the record the gate ALREADY wrote, and the purity is asserted
directly rather than inferred from the happy path -- a forge call added here would
not fail any assertion about the rendered text.

THE UNMEASURED ARM IS NOT A DEGENERATE CASE. It is the fail-safe direction
`proof_rendering_for_visibility` already takes, and the capture prompt documents
the ABSENT variable as meaning `authenticated_link`. Projecting no key is
therefore the correct unmeasured answer, and asserting it keeps a later
"helpfully default it to something" change from publishing an inline reference on
a repository nobody established was public.
"""

from __future__ import annotations

import json
import subprocess
from inspect import signature
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_proof_precondition
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import (
    RENDERING_AUTHENTICATED_LINK,
    RENDERING_INLINE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    PROOF_ASSET_RENDERING_ENV_VAR,
    PROOF_ASSETS_RELEASE_TAG_ENV_VAR,
    PROOF_STORE_JOURNAL_STAGE,
    PUBLISH_BRANCH_ENV_VAR,
    proof_store_env_lines,
)

_REPOSITORY = "livespec-orchestrator-beads-fabro"


def _repo(*, tmp_path: Path) -> Path:
    """A governed repository declaring no tag override, so the default resolves."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}),
        encoding="utf-8",
    )
    return tmp_path


def _journal_with(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    """A dispatch journal carrying exactly `records`, one JSON object per line."""
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _store_record(*, repository: str, rendering: str) -> dict[str, Any]:
    """One `proof-asset-store` record in the shape the gate writes it."""
    return {
        "at": "2026-10-05T00:00:00Z",
        "stage": PROOF_STORE_JOURNAL_STAGE,
        "work_item_id": "bd-ib-pa73qh",
        "repository": repository,
        "store": "release_assets",
        "rendering": rendering,
        "inline_waived": rendering != RENDERING_INLINE,
    }


def test_the_rendering_is_read_back_from_the_record_the_gate_journaled(tmp_path: Path) -> None:
    """The measurement reaches the projection through the journal, not a second probe.

    The gate performs the visibility probe ONCE per dispatch, before admission,
    and already journals the result per repository because the clause requires
    the waiver to be auditable. Reading that record back is what lets the overlay
    carry the measurement while performing no forge call of its own.
    """
    journal_path = _journal_with(
        tmp_path=tmp_path,
        records=(_store_record(repository=_REPOSITORY, rendering=RENDERING_INLINE),),
    )

    assert hasattr(_dispatcher_proof_precondition, "journaled_proof_rendering")
    assert (
        _dispatcher_proof_precondition.journaled_proof_rendering(
            journal_path=journal_path, repository=_REPOSITORY
        )
        == RENDERING_INLINE
    )


def test_the_newest_record_for_this_repository_wins(tmp_path: Path) -> None:
    """A repository's visibility can change between dispatches; the last read stands.

    The control is the SIBLING record written after it: a reader that simply took
    the last `proof-asset-store` row in the file would return another
    repository's answer, and both are plausible strings.
    """
    journal_path = _journal_with(
        tmp_path=tmp_path,
        records=(
            _store_record(repository=_REPOSITORY, rendering=RENDERING_AUTHENTICATED_LINK),
            _store_record(repository=_REPOSITORY, rendering=RENDERING_INLINE),
            _store_record(repository="some-other-tenant", rendering=RENDERING_AUTHENTICATED_LINK),
        ),
    )

    assert (
        _dispatcher_proof_precondition.journaled_proof_rendering(
            journal_path=journal_path, repository=_REPOSITORY
        )
        == RENDERING_INLINE
    )


def test_every_unmeasured_shape_reads_as_the_empty_rendering(tmp_path: Path) -> None:
    """Absent journal, foreign repository, and the UNOBSERVABLE arm all read unmeasured.

    They are one answer to the consumer -- nobody established this repository's
    visibility on this dispatch -- and the empty string is what the projection
    keys the withheld-key arm on. The unobservable record is included because it
    IS a `proof-asset-store` row: a reader keyed on the stage alone, without
    checking that the row carries a rendering, would return `None` where the
    caller expects a string.
    """
    unobservable = {
        "at": "2026-10-05T00:00:00Z",
        "stage": PROOF_STORE_JOURNAL_STAGE,
        "work_item_id": "bd-ib-pa73qh",
        "repository": _REPOSITORY,
        "unobservable": "the forge did not answer",
    }
    journal_path = _journal_with(
        tmp_path=tmp_path,
        records=(
            unobservable,
            _store_record(repository="some-other-tenant", rendering=RENDERING_INLINE),
        ),
    )

    assert (
        _dispatcher_proof_precondition.journaled_proof_rendering(
            journal_path=journal_path, repository=_REPOSITORY
        )
        == ""
    )
    assert (
        _dispatcher_proof_precondition.journaled_proof_rendering(
            journal_path=tmp_path / "never-written.jsonl", repository=_REPOSITORY
        )
        == ""
    )


def test_the_env_projection_carries_the_measured_rendering_beside_the_two_other_keys(
    tmp_path: Path,
) -> None:
    """All three keys, in the one table the capture stage reads.

    `beside` is the assertion, not merely `present`: the branch and the tag were
    already projected and the capture prompt reads all three out of the same
    `[environments.<id>.env]` table the overlay appends.
    """
    assert "rendering" in signature(proof_store_env_lines).parameters

    lines = proof_store_env_lines(
        repo=_repo(tmp_path=tmp_path),
        work_item_id="bd-ib-pa73qh",
        rendering=RENDERING_INLINE,
    )

    assert f'{PUBLISH_BRANCH_ENV_VAR} = "feat/bd-ib-pa73qh"' in lines
    assert f'{PROOF_ASSETS_RELEASE_TAG_ENV_VAR} = "proof-assets"' in lines
    assert f'{PROOF_ASSET_RENDERING_ENV_VAR} = "{RENDERING_INLINE}"' in lines


def test_the_env_projection_withholds_the_key_for_an_unmeasured_repository(
    tmp_path: Path,
) -> None:
    """No measurement, no key — the capture prompt's documented fallback covers it.

    Projecting `authenticated_link` here instead would look equivalent and is
    not: it would report a measurement that never happened, and the prompt
    already distinguishes an absent variable from a measured waiver when it says
    so on the record.
    """
    lines = proof_store_env_lines(repo=_repo(tmp_path=tmp_path), work_item_id="bd-ib-pa73qh")

    assert PUBLISH_BRANCH_ENV_VAR in lines
    assert PROOF_ASSET_RENDERING_ENV_VAR not in lines


def _refuse_subprocess(*args: object, **kwargs: object) -> object:
    """A `subprocess.run` stand-in that fails rather than letting a shell-out through."""
    _ = (args, kwargs)
    message = "the overlay projection must not shell out"
    raise AssertionError(message)


def test_the_env_projection_spawns_no_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The purity half, asserted directly rather than inferred from the rendered text.

    A forge call added inside this projection would change nothing any assertion
    about the rendered keys could see, which is exactly how the earlier draft
    reached 104 sealed tests before anyone noticed. So the guard is on the
    MECHANISM: every forge verb in this package runs through `subprocess.run`,
    and a projection that reaches for one fails here instead of out in CI.
    """
    monkeypatch.setattr(subprocess, "run", _refuse_subprocess)

    lines = proof_store_env_lines(
        repo=_repo(tmp_path=tmp_path),
        work_item_id="bd-ib-pa73qh",
        rendering=RENDERING_AUTHENTICATED_LINK,
    )

    assert f'{PROOF_ASSET_RENDERING_ENV_VAR} = "{RENDERING_AUTHENTICATED_LINK}"' in lines


def test_the_subprocess_guard_fires_when_something_does_shell_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control on the case above: the stand-in CAN return the other answer.

    Without it, the purity assertion is an instrument nobody established could
    fail — a guard that silently stopped being installed, or a `subprocess.run`
    the projection reached through some other binding, would read exactly like a
    pure projection. This drives the patched seam directly and requires it to
    raise.
    """
    monkeypatch.setattr(subprocess, "run", _refuse_subprocess)

    with pytest.raises(AssertionError, match="must not shell out"):
        _ = subprocess.run(["true"], check=False)
