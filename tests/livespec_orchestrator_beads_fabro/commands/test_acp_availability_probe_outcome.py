"""WHAT one confirmation turn's ending means: only a completed turn confirms.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "Availability is
confirmed only by a successfully completed ACP prompt turn ... Session
creation, process exit alone, timeout, cancellation, and an ACP refusal do not
confirm availability." Scenario 127's "only a successfully completed prompt
turn makes the candidate eligible for the dispatch" is the line this grades.

THE FIVE UNCONFIRMED ENDINGS ARE GRADED SEPARATELY RATHER THAN COLLAPSED, and
that is the whole claim here. Downstream they take THREE different routes -- a
refusal may mint a hold, a timeout must not, and a process exit is neither --
so an implementation answering one boolean would satisfy a test that only ever
asked "did it confirm" while losing the distinction every later decision rests
on. Each case therefore asserts the ENDING as well as the verdict.

EVERY CASE IS PAIRED WITH THE ONE THAT MUST ANSWER DIFFERENTLY. A grader
returning "unconfirmed" unconditionally satisfies five of the six rows; the
completed-turn row is what refuses it, and it is asserted on the same
observation shape as its neighbours with one field moved.

Everything is HERMETIC: the observations are built in memory and nothing reaches
a factory, a provider or a credential.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_availability_probe_outcome"


def _outcome_module() -> Any:
    """Import the probe's outcome grading, proving its file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _failure(*, cause: str) -> Any:
    """One recorded failure carrying a provider's own sentence."""
    records = importlib.import_module(f"{_PACKAGE}._fabro_port_records")
    return records.FabroFailureDetail(
        cause=cause, category="transient_infra", signature="confirm|deterministic|acp turn failed"
    )


def _observation(*, module: Any, **overrides: Any) -> Any:
    """One probe ending as the launcher read it, defaulting to a clean success."""
    fields: dict[str, Any] = {
        "turn_completed": True,
        "acp_started": True,
        "cancelled": False,
        "timed_out": False,
        "failure": None,
    }
    fields.update(overrides)
    return module.AcpProbeObservation(**fields)


def test_a_successfully_completed_prompt_turn_is_the_one_ending_that_confirms() -> None:
    """The positive control: without it every refusal below is satisfied vacuously."""
    module = _outcome_module()

    ending = module.probe_ending(observation=_observation(module=module))

    assert ending == module.PROBE_TURN_COMPLETED
    assert module.probe_confirms(ending=ending) is True


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        # Session creation: the adapter opened a session and no turn completed.
        ({"turn_completed": False}, "PROBE_SESSION_CREATED"),
        # Process exit alone: the adapter never reached the protocol at all.
        ({"turn_completed": False, "acp_started": False}, "PROBE_PROCESS_EXIT"),
        # Timeout: the probe's own bound fired and the work was terminated.
        ({"turn_completed": False, "timed_out": True}, "PROBE_TIMED_OUT"),
        # Cancellation.
        ({"turn_completed": False, "cancelled": True}, "PROBE_CANCELLED"),
    ],
)
def test_the_four_endings_with_no_provider_sentence_each_record_unconfirmed(
    overrides: dict[str, Any], expected: str
) -> None:
    """Each is its own ending, because each takes its own route downstream."""
    module = _outcome_module()

    ending = module.probe_ending(observation=_observation(module=module, **overrides))

    assert ending == getattr(module, expected)
    assert module.probe_confirms(ending=ending) is False


def test_an_acp_refusal_is_its_own_ending_and_confirms_nothing() -> None:
    """A refusal is the one unconfirmed ending that may later mint a hold."""
    module = _outcome_module()

    ending = module.probe_ending(
        observation=_observation(
            module=module,
            turn_completed=False,
            failure=_failure(cause="You've hit your usage limit."),
        )
    )

    assert ending == module.PROBE_REFUSED
    assert module.probe_confirms(ending=ending) is False


def test_a_completed_turn_is_not_overridden_by_a_recorded_failure_elsewhere() -> None:
    """The turn is what confirms; a run-level sentence beside it changes nothing."""
    module = _outcome_module()

    ending = module.probe_ending(
        observation=_observation(module=module, failure=_failure(cause="a later node failed"))
    )

    assert ending == module.PROBE_TURN_COMPLETED


def test_a_timed_out_probe_outranks_its_own_recorded_refusal_text() -> None:
    """A terminated turn mints no hold, so the bound is graded before the text."""
    module = _outcome_module()

    ending = module.probe_ending(
        observation=_observation(
            module=module,
            turn_completed=False,
            timed_out=True,
            failure=_failure(cause="You've hit your usage limit."),
        )
    )

    assert ending == module.PROBE_TIMED_OUT


def test_every_ending_is_enumerated_and_exactly_one_of_them_confirms() -> None:
    """The vocabulary is closed, so no consumer can be handed a token it cannot grade."""
    module = _outcome_module()

    assert set(module.PROBE_ENDINGS) == {
        module.PROBE_TURN_COMPLETED,
        module.PROBE_SESSION_CREATED,
        module.PROBE_PROCESS_EXIT,
        module.PROBE_TIMED_OUT,
        module.PROBE_CANCELLED,
        module.PROBE_REFUSED,
    }
    assert len(module.PROBE_ENDINGS) == len(set(module.PROBE_ENDINGS))
    confirming = [one for one in module.PROBE_ENDINGS if module.probe_confirms(ending=one)]
    assert confirming == [module.PROBE_TURN_COMPLETED]
