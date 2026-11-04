"""The hold ONE refused confirmation turn mints, dated from the probe itself.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "An eligible refusal
creates a new occurrence-time-scoped hold. Any other probe failure skips that
candidate for the current evaluation, creates no hold, and allows selection to
continue to later eligible candidates." The same section's "A hold MUST come
from an actual candidate attempt: a typed eligible failure classified from a
failed node of a terminal run, whichever terminal the run reached, or a refused
availability confirmation turn ..., which runs the candidate's own adapter and
is therefore an actual attempt. Expiry is computed from occurrence time and
never from ingestion." Scenario 127's "a refusal with an eligible
provider-limit cause records a new hold whose expiry runs from the probe's
occurrence time" is the line this grades.

THE DATING IS THE CLAIM, and it is asserted as the arithmetic rather than as a
present field. A record carrying SOME expiry is what a build dating from
ingestion also produces, so the test computes occurrence-plus-interval from the
ledger's own `HOLD_INTERVAL` and compares -- which fails for a build that
stamped the read instant and for a build that refreshed an existing record.

EVERY NEGATIVE IS PAIRED WITH THE POSITIVE ON ONE OBSERVATION SHAPE. A builder
that minted nothing satisfies all five refusals below, so the eligible row is
what refuses it; and the TIMED-OUT row is the sharpest of the negatives,
because its observation carries the identical provider sentence the eligible
row is graded from -- the only difference being the bound that fired. A builder
reading the text before the bound passes every other case in this module.

Everything is HERMETIC: the candidate and the observation are built in memory,
and nothing reaches a factory, a provider or a credential.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_availability_probe_records"

_OCCURRED = "2026-10-20T12:00:00Z"
_WORK_ITEM = "bd-ib-n3pzcl"
# The measured Anthropic usage-ceiling sentence the built-in quota signature is
# declared for; the generic transport fault below matches no signature at all.
_QUOTA = "You've hit your usage limit. Your limit will reset at 3pm."
_UNCLASSIFIED = "the sandbox could not resolve the remote host"


def _records_module() -> Any:
    """Import the probe's record builders, proving the file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _candidate() -> Any:
    """A built-in-keyed Claude candidate, so the shipped signatures apply."""
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(
            command="claude-code-acp", env={"ANTHROPIC_MODEL": "claude-opus-5"}
        ),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5 (high)",
            candidate_key="claude-opus-5-high",
            availability_key="anthropic",
        ),
    )


def _observation(*, cause: str | None = _QUOTA, **overrides: Any) -> Any:
    """One probe ending, defaulting to a refusal carrying the quota sentence."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    port = importlib.import_module(f"{_PACKAGE}._fabro_port_records")
    fields: dict[str, Any] = {
        "turn_completed": False,
        "acp_started": True,
        "cancelled": False,
        "timed_out": False,
        "failure": None
        if cause is None
        else port.FabroFailureDetail(
            cause=cause, category="transient_infra", signature="confirm|deterministic|acp"
        ),
    }
    fields.update(overrides)
    return outcome.AcpProbeObservation(**fields)


def _built(*, module: Any, observation: Any) -> Any:
    """The hold record this probe ending mints, or `None`."""
    return module.probe_hold_record(
        candidate=_candidate(),
        builtin=True,
        observation=observation,
        occurred_at=_OCCURRED,
        run_reference="hp:01MPROBE",
        work_item_id=_WORK_ITEM,
    )


def test_an_eligible_refusal_mints_a_hold_expiring_from_the_probes_own_instant() -> None:
    """The positive control, and the dating asserted as arithmetic over the clause."""
    module = _records_module()
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")

    record = _built(module=module, observation=_observation())

    assert record is not None
    assert record["occurred_at"] == _OCCURRED
    expected = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc) + hold_records.HOLD_INTERVAL
    assert record["expires_at"] == expected.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert record["stage"] == hold_records.HOLD_STAGE
    assert record["schema_version"] == hold_records.HOLD_SCHEMA_VERSION
    assert record["cause"] == "quota"
    assert record["scope"] == "availability-domain"
    assert record["hold_key"] == "anthropic"
    assert record["node"] == probe.AVAILABILITY_PROBE_NODE
    assert record["work_item_id"] == _WORK_ITEM
    # A refused confirmation turn ran the candidate's own adapter, so it is an
    # actual candidate attempt rather than a probe the clause forbids minting
    # from.
    assert record["evidence_kind"] == "candidate-attempt"
    assert "01MPROBE" in str(record["evidence_id"])


def test_the_minted_record_parses_back_as_a_live_schema_v1_observation() -> None:
    """A record the ledger cannot read holds nothing, whatever fields it carries."""
    module = _records_module()
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")

    record = _built(module=module, observation=_observation())

    assert record is not None
    parsed = hold_records.parse_hold_record(record=record)
    assert not isinstance(parsed, str), parsed
    assert hold_records.hold_expired(hold=parsed, now_iso="2026-10-20T12:10:00Z") is False
    assert hold_records.hold_expired(hold=parsed, now_iso="2026-10-20T12:20:00Z") is True


def test_re_ingesting_one_probe_reproduces_the_identical_observation_id() -> None:
    """A replayed release must not duplicate the hold its own probe already minted."""
    module = _records_module()

    first = _built(module=module, observation=_observation())
    again = _built(module=module, observation=_observation())

    assert first is not None
    assert again is not None
    assert first["observation_id"] == again["observation_id"]


@pytest.mark.parametrize(
    "overrides",
    [
        # Terminated past the bound, carrying the IDENTICAL quota sentence: the
        # sharpest negative, because only the bound distinguishes it.
        {"timed_out": True},
        {"cancelled": True},
        # A session that opened and completed no turn.
        {"cause": None},
        # The adapter exited before the protocol, whatever its text says.
        {"acp_started": False},
        # A completed turn confirms; it never mints a hold.
        {"turn_completed": True},
    ],
)
def test_no_other_probe_ending_mints_a_hold_even_carrying_a_quota_sentence(
    overrides: dict[str, Any],
) -> None:
    """ "Any other probe failure ... creates no hold" — including a timed-out one."""
    module = _records_module()

    assert _built(module=module, observation=_observation(**overrides)) is None


def test_a_refusal_whose_cause_classifies_non_eligible_mints_nothing() -> None:
    """An unmatched sentence keeps its existing route and holds no allowance."""
    module = _records_module()

    assert _built(module=module, observation=_observation(cause=_UNCLASSIFIED)) is None


def test_an_unreadable_occurrence_instant_mints_nothing_rather_than_an_undated_hold() -> None:
    """Expiry is computed from occurrence, so an unreadable instant has no expiry."""
    module = _records_module()

    record = module.probe_hold_record(
        candidate=_candidate(),
        builtin=True,
        observation=_observation(),
        occurred_at="not-an-instant",
        run_reference="hp:01MPROBE",
        work_item_id=_WORK_ITEM,
    )

    assert record is None


def test_the_hold_is_dated_from_the_probe_and_never_from_the_read_that_ingests_it() -> None:
    """Two probes an hour apart expire an hour apart, from their own instants."""
    module = _records_module()
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")

    later = module.probe_hold_record(
        candidate=_candidate(),
        builtin=True,
        observation=_observation(),
        occurred_at="2026-10-20T13:00:00Z",
        run_reference="hp:01MLATER",
        work_item_id=_WORK_ITEM,
    )
    earlier = _built(module=module, observation=_observation())

    assert later is not None
    assert earlier is not None
    gap = hold_records.parse_hold_instant(
        text=str(later["expires_at"])
    ) - hold_records.parse_hold_instant(text=str(earlier["expires_at"]))
    assert gap == timedelta(hours=1)
