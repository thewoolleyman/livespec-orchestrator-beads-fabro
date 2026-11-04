"""Resolving, refusing and journaling `dispatcher.credential_queue_allowance_seconds`."""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_queue_allowance import (
    CREDENTIAL_QUEUE_ALLOWANCE_KEY,
    DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS,
    CredentialQueueAllowance,
    credential_queue_allowance_from_block,
    credential_queue_allowance_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
)


def test_an_absent_key_resolves_the_documented_default_at_the_default_layer() -> None:
    resolved = credential_queue_allowance_from_block(block={})

    assert resolved == CredentialQueueAllowance(
        seconds=DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS, layer=WORKFLOW_DEFAULT_LAYER
    )


def test_a_committed_value_resolves_at_the_repository_layer() -> None:
    resolved = credential_queue_allowance_from_block(
        block={"credential_queue_allowance_seconds": 3_600}
    )

    assert resolved == CredentialQueueAllowance(seconds=3_600, layer=REPOSITORY_LAYER)


@pytest.mark.parametrize(
    "value",
    [0, -1, 1.5, "bad", True],
    ids=["zero", "negative", "fractional", "string", "boolean"],
)
def test_a_non_positive_or_non_integer_value_refuses_by_name(value: object) -> None:
    """Every rejected shape names the key, because the key is what must be edited.

    `True` rides the same list as the four the scenario names, and it is the one
    a hand-rolled coercion admits: `bool` is an `int` in Python, so `true` in a
    config file resolves to a ONE-SECOND queue allowance that passes a naive
    validation and then refuses every dispatch that queued at all.
    """
    refusal = credential_queue_allowance_from_block(
        block={"credential_queue_allowance_seconds": value}
    )

    assert isinstance(refusal, str)
    assert CREDENTIAL_QUEUE_ALLOWANCE_KEY in refusal
    assert repr(value) in refusal


def test_the_journal_record_nests_the_figure_with_its_layer() -> None:
    """One nested object, so a reader cannot join a figure to another row's layer."""
    record: dict[str, Any] = credential_queue_allowance_journal_record(
        allowance=CredentialQueueAllowance(seconds=3_600, layer=REPOSITORY_LAYER)
    )

    assert record == {"credential_queue_allowance": {"seconds": 3_600, "layer": REPOSITORY_LAYER}}
