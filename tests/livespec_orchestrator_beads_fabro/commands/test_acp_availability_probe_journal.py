"""EVERY confirmation turn is journaled, whatever it ended as.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "Every probe turn is
journaled with the candidate identity, outcome, occurrence time and, where
observable, its cost."

"EVERY" IS THE CLAIM, and it is the half an implementation is most likely to
narrow. A row written only on refusal loses the measurement that found a
provider HEALTHY -- which is exactly the question an operator asks while a
chain is waiting -- and an absent row reads downstream as a probe nobody ran.
So the row is asserted for all six endings, parametrized, and the confirming
ending is in that set rather than tested alone.

"WHERE OBSERVABLE" IS ABOUT THE MEASUREMENT AND NOT ABOUT THE KEY. The engine
reports no cost figure on many runs, and a row that OMITS the key when it has
none is indistinguishable from a row written by a build that never recorded
cost at all. So the null is asserted to be PRESENT and accompanied by a stated
observability flag -- the same fail-closed reading the repository's cost gate
already takes.

THE IDENTITY IS ASSERTED FIELD BY FIELD rather than as one joined key, because
a domain hold is scoped by the availability key ALONE: a query for "every probe
that spent this account" must not have to take a pair apart to ask it.

Everything is HERMETIC: the candidate is built in memory and nothing reaches a
factory, a provider or a credential.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_availability_probe_records"

_OCCURRED = "2026-10-20T12:00:00Z"


def _records() -> Any:
    """Import the record builders, proving the journal row is implemented."""
    module = importlib.import_module(f"{_PACKAGE}.{_MODULE}")
    assert hasattr(module, "probe_journal_record"), "probe_journal_record is not implemented yet"
    assert hasattr(module, "PROBE_JOURNAL_STAGE"), "PROBE_JOURNAL_STAGE is not declared yet"
    return module


def _candidate(*, identified: bool = True) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    adapter = adapters.AcpAdapter(command="codex-acp", args=("acp",))
    if not identified:
        return schema.AcpCandidate(adapter=adapter)
    return schema.AcpCandidate(
        adapter=adapter,
        identity=schema.AcpCandidateIdentity(
            display_name="GPT 5.5 (high)",
            candidate_key="gpt-5.5-high",
            availability_key="chatgpt-team-account",
        ),
    )


def _endings() -> list[str]:
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    return list(outcome.PROBE_ENDINGS)


@pytest.mark.parametrize("ending", _endings())
def test_a_row_is_journaled_for_every_ending_including_the_one_that_confirms(
    ending: str,
) -> None:
    """A row written only on refusal makes a healthy provider's probe invisible."""
    module = _records()
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")

    row = module.probe_journal_record(
        candidate=_candidate(),
        ending=ending,
        occurred_at=_OCCURRED,
        factory="hp",
        run_id="01MPROBE",
        cost_usd_micros=4120,
    )

    assert row["stage"] == module.PROBE_JOURNAL_STAGE
    assert row["outcome"] == ending
    assert row["confirmed"] is outcome.probe_confirms(ending=ending)
    assert row["occurred_at"] == _OCCURRED
    assert row["node"] == probe.AVAILABILITY_PROBE_NODE
    assert row["factory"] == "hp"
    assert row["run_id"] == "01MPROBE"
    # The identity, field by field: a domain hold is keyed on the first alone.
    assert row["availability_key"] == "chatgpt-team-account"
    assert row["candidate_key"] == "gpt-5.5-high"
    assert row["display_name"] == "GPT 5.5 (high)"
    assert row["cost_usd_micros"] == 4120
    assert row["cost_observable"] is True


def test_an_unobservable_cost_is_a_present_null_and_a_stated_flag() -> None:
    """An omitted key is what a row from a build predating cost looks like."""
    module = _records()

    row = module.probe_journal_record(
        candidate=_candidate(),
        ending=module.PROBE_JOURNAL_STAGE and "turn-completed",
        occurred_at=_OCCURRED,
        factory="hp",
        run_id="01MPROBE",
        cost_usd_micros=None,
    )

    assert "cost_usd_micros" in row
    assert row["cost_usd_micros"] is None
    assert row["cost_observable"] is False


def test_the_row_names_the_expired_observations_the_probe_was_run_to_satisfy() -> None:
    """Provenance: what the probe was FOR, never a claim about what it cleared."""
    module = _records()

    row = module.probe_journal_record(
        candidate=_candidate(),
        ending="turn-completed",
        occurred_at=_OCCURRED,
        factory="hp",
        run_id="01MPROBE",
        cost_usd_micros=None,
        observation_ids=("acp-aaaa1111", "acp-bbbb2222"),
    )

    assert row["satisfies_observation_ids"] == ["acp-aaaa1111", "acp-bbbb2222"]

    without = module.probe_journal_record(
        candidate=_candidate(),
        ending="turn-completed",
        occurred_at=_OCCURRED,
        factory="hp",
        run_id=None,
        cost_usd_micros=None,
    )
    assert without["satisfies_observation_ids"] == []
    assert without["run_id"] is None


def test_an_identity_less_candidate_is_journaled_with_nulls_not_an_invented_key() -> None:
    """A row naming an undeclared entitlement would read as evidence about it."""
    module = _records()

    row = module.probe_journal_record(
        candidate=_candidate(identified=False),
        ending="process-exit",
        occurred_at=_OCCURRED,
        factory="hp",
        run_id="01MPROBE",
        cost_usd_micros=None,
    )

    assert row["availability_key"] is None
    assert row["candidate_key"] is None
    assert row["display_name"] is None


def test_the_row_round_trips_through_the_append_only_journals_own_encoding() -> None:
    """A row the journal cannot encode is a turn nothing records."""
    module = _records()

    row = module.probe_journal_record(
        candidate=_candidate(),
        ending="acp-refusal",
        occurred_at=_OCCURRED,
        factory="hp",
        run_id="01MPROBE",
        cost_usd_micros=0,
    )

    decoded = json.loads(json.dumps(row, sort_keys=True))
    assert decoded == row
    # Zero is a MEASURED figure, not an absence.
    assert decoded["cost_observable"] is True
