"""The ending a failure block carrying NO sentence grades as.

Beside `test_acp_availability_probe_outcome.py`, which binds the clause. A run
whose failure block exists but records no cause -- an `omitempty`-sparse
payload, or an engine that named a category and no message -- has said nothing
about a provider, so it is the bare-session ending rather than a refusal. That
distinction decides whether the classifier is consulted for a hold at all, and
getting it wrong is the fail-OPEN direction: a hold minted from a block with no
sentence in it skips the candidate for fifteen minutes on nothing.

A SEPARATE module rather than cases in that one because these were authored at
that Red's Green, and a Red's test bytes are fixed across its Red-to-Green pair.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


def _outcome() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")


@pytest.mark.parametrize("cause", [None, "", "   "])
def test_a_failure_block_recording_no_sentence_is_a_bare_session_not_a_refusal(
    cause: str | None,
) -> None:
    """Nothing was said about a provider, so nothing may be graded for a hold."""
    module = _outcome()
    records = importlib.import_module(f"{_PACKAGE}._fabro_port_records")

    ending = module.probe_ending(
        observation=module.AcpProbeObservation(
            turn_completed=False,
            acp_started=True,
            cancelled=False,
            timed_out=False,
            failure=records.FabroFailureDetail(cause=cause, category=None, signature=None),
        )
    )

    assert ending == module.PROBE_SESSION_CREATED
    assert module.probe_confirms(ending=ending) is False


def test_a_recorded_sentence_with_no_session_behind_it_is_a_process_exit() -> None:
    """A pre-turn fault is not provider evidence, whatever its text says."""
    module = _outcome()
    records = importlib.import_module(f"{_PACKAGE}._fabro_port_records")

    ending = module.probe_ending(
        observation=module.AcpProbeObservation(
            turn_completed=False,
            acp_started=False,
            cancelled=False,
            timed_out=False,
            failure=records.FabroFailureDetail(
                cause="You've hit your usage limit.", category=None, signature=None
            ),
        )
    )

    assert ending == module.PROBE_PROCESS_EXIT


def test_an_ending_this_build_does_not_know_confirms_nothing() -> None:
    """A token from another build fails closed rather than reading as a success."""
    module = _outcome()

    assert module.probe_confirms(ending="some-later-builds-ending") is False
    assert set(module.PROBE_UNCONFIRMED_ENDINGS) == set(module.PROBE_ENDINGS) - {
        module.PROBE_TURN_COMPLETED
    }
