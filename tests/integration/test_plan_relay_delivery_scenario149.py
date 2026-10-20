"""Integration-tier acceptance for `SPECIFICATION/scenarios.md` Scenario 149.

Binds "Scenario 149 — Acknowledgment cannot discharge a target-effect relay" and
the relay-delivery clause of `SPECIFICATION/contracts.md` it governs. The
scenario's first outline fixes the whole of this assertion: given "a stable relay id,
expected result, original UTC deadline and sender obligation", and given that
"queue delivery, peer receipt and consumption are acknowledged while the target
is unchanged", recording the relay leaves it "unfulfilled", retaining "its sender
and original deadline", because "only an authoritative observation of the
requested target effect discharges it".

EVERY CASE DRIVES THE REAL PRIMITIVE against the in-memory `FakeBeadsClient`
(`LIVESPEC_BEADS_FAKE=1`), which is this repository's hermetic ledger surface. The
reference parse, the repository resolution, the shared authoritative result
reader and the ledger adapter beneath it are all production code: nothing is
stood in under the primitive, so a relay that reads as delivered here read a real
tenant row.

THE ACKNOWLEDGEMENT CASES SUPPLY BOTH TRANSPORT LEGS DELIBERATELY. A relay whose
`receipt_ack` and `peer_recorded` are both filled in is the exact shape the
clause refuses to treat as delivery, and it is the shape that reads most like a
discharged obligation at every surface an operator looks at. A case that omitted
them would pass against an implementation that discharged on either.

THE MODULE IS REACHED THROUGH `importlib` RATHER THAN A TOP-LEVEL IMPORT. At Red
the module does not exist, and a top-level import would die at COLLECTION — which
proves only unimportability, never that the behaviour is unimplemented. The
`is_file` assertion is the genuine first failure instead.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
    OBSERVATION_UNSATISFIED,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-relayepic"
_TARGET_ID = "bd-ib-relaytarget"
_RELAY_ID = "relay-overseer-schema-referral"
_SENDER = "relay-delivery-and-progress-deadline-supervisor"
_ORIGINAL_DEADLINE = "2026-10-20T18:00:00Z"
_RECORDED_AT = "2026-10-20T09:00:00Z"
_RECEIPT_ACK = "2026-10-20T08:55:00Z"
_PEER_RECORDED = "2026-10-20T08:56:00Z"

_DELIVERY_MODULE = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_plan_relay_delivery.py"
)
_RECORD_MODULE = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_plan_relay_record.py"
)


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _modules() -> tuple[Any, Any]:
    """Import the relay modules, proving they exist before reaching for them."""
    assert _RECORD_MODULE.is_file(), f"{_RECORD_MODULE} does not exist"
    assert _DELIVERY_MODULE.is_file(), f"{_DELIVERY_MODULE} does not exist"
    return (
        importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_relay_record"),
        importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_relay_delivery"),
    )


@dataclass(kw_only=True)
class _Runner:
    """A forge seam that refuses, recording every argv it was asked to run.

    Refusing is the point rather than a convenience: the clause requires an
    observation failure to be `unobservable` and never a confident negative, and
    the relay built on it to stay undelivered with its sender and deadline
    intact. An answering stand-in could not produce that reading at all.
    """

    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(tuple(argv))
        return CommandResult(exit_code=1, stdout="", stderr="the forge refused this read")


def _seed(*, tmp_path: Path, target_status: str) -> tuple[Path, StoreConfig]:
    """One plan epic plus the item whose status the relay's expected result names."""
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=repo)
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    for issue_id, issue_type, status in (
        (_EPIC_ID, "epic", "active"),
        (_TARGET_ID, "feature", target_status),
    ):
        _ = client.create_issue(
            draft=IssueDraft(
                issue_id=issue_id,
                issue_type=issue_type,
                title=issue_id,
                description="Definition of Done\n\n- A thing holds.",
                assignee=None,
                created_at="2026-10-20T08:00:00Z",
                metadata={"rank": "a0"},
            )
        )
        client.update_issue(issue_id=issue_id, status=status)
    return repo, config


def _required_result() -> dict[str, object]:
    return {"repo": _PROJECT_NAME, "item_status": {"item_id": _TARGET_ID, "status": "done"}}


def _request(
    *,
    modules: tuple[Any, Any],
    repo: Path,
    config: StoreConfig,
    runner: _Runner | None = None,
) -> Any:
    record_module, delivery_module = modules
    return delivery_module.RelayRequest(
        config=config,
        project_root=repo,
        runner=_Runner() if runner is None else runner,
        epic_id=_EPIC_ID,
        relay_id=_RELAY_ID,
        operation_id="relay-record-1",
        sender=_SENDER,
        required_result=_required_result(),
        deadline=_ORIGINAL_DEADLINE,
        acknowledgements=record_module.RelayAcknowledgements(
            receipt_ack=_RECEIPT_ACK,
            peer_recorded=_PEER_RECORDED,
        ),
        now=_RECORDED_AT,
    )


def _relay_comments(*, config: StoreConfig) -> list[str]:
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return [
        text
        for comment in client.list_comments(issue_id=_EPIC_ID)
        if isinstance(text := comment.get("text"), str) and text.startswith("plan-relay-event")
    ]


def test_acknowledged_transport_leaves_an_unchanged_target_undelivered(
    tmp_path: Path,
) -> None:
    """Queue receipt and peer recording are acknowledged; the target has not moved.

    The clause: "A sender queue receipt, peer acknowledgment or peer_recorded
    value MUST NOT establish delivery." So the record is undelivered, carries the
    unsatisfied observation it actually took, and keeps the sender who still owes
    the obligation — while both transport legs are retained, because the schema
    requires them kept and kept SEPARATELY from the evidence leg.
    """
    modules = _modules()
    record_module, delivery_module = modules
    repo, config = _seed(tmp_path=tmp_path, target_status="active")

    recorded = delivery_module.record_relay(
        request=_request(modules=modules, repo=repo, config=config)
    )

    assert isinstance(recorded, record_module.RelayRecord)
    assert recorded.delivered is False
    assert recorded.disposition == record_module.DELIVERY_UNDELIVERED
    assert recorded.observation.status == OBSERVATION_UNSATISFIED
    assert recorded.sender == _SENDER
    assert recorded.original_deadline == _ORIGINAL_DEADLINE
    assert recorded.legs.receipt_ack == _RECEIPT_ACK
    assert recorded.legs.peer_recorded == _PEER_RECORDED
    assert recorded.legs.target_evidence is None
    assert recorded.legs.complete is False
    assert recorded.ownership_transferable is False


def test_only_an_authoritative_target_observation_records_delivery(
    tmp_path: Path,
) -> None:
    """The same relay against a target that HAS moved: delivered, with evidence.

    This is the negative control the trap catalogue asks for — an instrument that
    cannot return a hit reporting no hits is worth nothing, so the undelivered
    case above is only evidence while this one shows the same primitive, against
    the same surface, observing a real positive result.
    """
    modules = _modules()
    record_module, delivery_module = modules
    repo, config = _seed(tmp_path=tmp_path, target_status="done")

    recorded = delivery_module.record_relay(
        request=_request(modules=modules, repo=repo, config=config)
    )

    assert isinstance(recorded, record_module.RelayRecord)
    assert recorded.delivered is True
    assert recorded.disposition == record_module.DELIVERY_DELIVERED
    assert recorded.observation.status == OBSERVATION_SATISFIED
    assert recorded.legs.target_evidence == recorded.observation.evidence
    assert recorded.legs.target_evidence != ""
    assert recorded.legs.complete is True
    assert recorded.ownership_transferable is True


def test_a_target_that_could_not_be_observed_leaves_the_relay_undelivered(
    tmp_path: Path,
) -> None:
    """ "unobservable sources and wrong-repository observations never establish
    fulfillment".

    A forge read that fails is a failure to MEASURE, not a measurement, so the
    relay stays undelivered with no evidence leg and its sender still owing it —
    the same disposition an unmet target produces, reached from the opposite
    kind of ignorance. The runner's recorded argv is what proves the forge was
    genuinely asked rather than skipped, which is the one thing an undelivered
    verdict alone cannot distinguish.
    """
    modules = _modules()
    record_module, delivery_module = modules
    repo, config = _seed(tmp_path=tmp_path, target_status="done")
    runner = _Runner()
    request = replace(
        _request(modules=modules, repo=repo, config=config, runner=runner),
        required_result={
            "repo": _PROJECT_NAME,
            "pull_request_state": {"number": 149, "state": "merged"},
        },
    )

    recorded = delivery_module.record_relay(request=request)

    assert isinstance(recorded, record_module.RelayRecord)
    assert runner.calls != []
    assert recorded.observation.status == OBSERVATION_UNOBSERVABLE
    assert recorded.delivered is False
    assert recorded.legs.target_evidence is None
    assert recorded.sender == _SENDER
    assert recorded.original_deadline == _ORIGINAL_DEADLINE


def test_the_recorded_relay_is_durable_on_the_epic_with_its_payload(
    tmp_path: Path,
) -> None:
    """One `plan-relay-event` comment per recorded observation, payload included.

    The ledger is the sole durable store, so a relay the primitive returned but
    never wrote would be an obligation nobody else can see. The payload is
    asserted through the module's own parse rather than by matching prose,
    because the parse is what a retry and a recheck read it back with.
    """
    modules = _modules()
    record_module, delivery_module = modules
    repo, config = _seed(tmp_path=tmp_path, target_status="active")

    recorded = delivery_module.record_relay(
        request=_request(modules=modules, repo=repo, config=config)
    )
    assert isinstance(recorded, record_module.RelayRecord)

    comments = _relay_comments(config=config)
    assert len(comments) == 1
    payload = record_module.payload_line(text=comments[0])
    assert payload is not None
    assert record_module.parse_relay_payload(text=payload) == recorded


def test_a_relay_naming_an_untyped_expected_result_is_refused_unwritten(
    tmp_path: Path,
) -> None:
    """ "Arbitrary shell predicates MUST NOT be accepted as result references."

    A relay whose expected result is not one of the five typed kinds has no
    canonical target identity, so there is nothing a later recheck could compare
    against. The refusal is returned BEFORE anything is written, because a
    recorded relay nobody can re-observe is worse than none.
    """
    modules = _modules()
    _, delivery_module = modules
    repo, config = _seed(tmp_path=tmp_path, target_status="active")
    request = replace(
        _request(modules=modules, repo=repo, config=config),
        required_result={"repo": _PROJECT_NAME, "shell": "test -f done"},
    )

    refused = delivery_module.record_relay(request=request)

    assert isinstance(refused, delivery_module.RelayRefusal)
    assert _relay_comments(config=config) == []


@pytest.mark.parametrize(
    "field",
    ["relay_id", "operation_id", "sender", "deadline"],
)
def test_a_relay_missing_one_identity_field_is_refused_before_any_read(
    tmp_path: Path, field: str
) -> None:
    """ "a stable relay id, expected result, original UTC deadline and sender".

    Each of the four is what a LATER call addresses the relay by — the recheck,
    the retry, and the party an expiry falls to — so a relay missing any one of
    them is an obligation nothing can re-observe or attribute. The refusal is
    graded before the target is read, because a read spent on an unaddressable
    relay is a read spent on a question nobody can ask again.
    """
    modules = _modules()
    _, delivery_module = modules
    repo, config = _seed(tmp_path=tmp_path, target_status="done")
    request = replace(_request(modules=modules, repo=repo, config=config), **{field: "   "})

    refused = delivery_module.record_relay(request=request)

    assert isinstance(refused, delivery_module.RelayRefusal)
    assert field.replace("_", " ").replace("operation id", "operation identity") in refused.detail
    assert _relay_comments(config=config) == []
