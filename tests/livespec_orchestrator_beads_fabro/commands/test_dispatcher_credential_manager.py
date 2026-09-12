"""The llm-provider-manager consumer boundary: its records, port and wire protocol.

Every request object asserted here is graded against livespec-overseer
`SPECIFICATION/contracts.md` section "The LLM credential-provider operation", which closes
each member set in BOTH directions — so the assertions compare whole key sets rather than
checking that a field is present. A test that only checked presence would pass against a
request carrying an extra member the manager refuses.

The parser cases are deliberately weighted toward MALFORMED input, because the success
path is the one a wrong implementation also gets right. A manager answering in a shape
this build does not model must become a refusal, never a half-trusted record.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    ANTHROPIC_PROVIDER,
    FACTORY_PURPOSE,
    INFERENCE_KIND,
    ISOLATED_RUN_ADAPTER,
    RECEIPT_MEMBERS,
    REPORT_CLASSIFICATIONS,
    CredentialReceipt,
    ManagerRefusal,
    ProvisionedCredential,
    RunFailureReport,
    manager_refusal_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_wire import (
    MALFORMED_RESPONSE_TYPE,
    parse_provision_response,
    parse_report_response,
    parse_target_response,
    provision_request_object,
    refusal,
    report_request_object,
    run_registration_object,
    target_request_object,
)

_RUN_ID = "dispatch-2026-09-12-a"
_RECORD_ID = "5f1b7a0c-0000-4000-8000-00000000cafe"

_MODULE_ROOT = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)


def _receipt_payload() -> dict[str, str]:
    return {
        "record_id": _RECORD_ID,
        "account_id": "anthropic-2",
        "validated_at": "2026-09-12T08:00:00Z",
        "purpose": FACTORY_PURPOSE,
        "lease_expires_at": "2026-09-12T14:00:00Z",
    }


def _ok(*, operation: str, **members: object) -> str:
    import json

    return json.dumps({"version": 1, "status": "ok", "operation": operation, **members})


# ---------------------------------------------------------------------------
# The boundary exists as its own module, separate from the process that runs it
# ---------------------------------------------------------------------------


def test_the_manager_boundary_and_its_wire_protocol_are_separate_modules() -> None:
    """The port is declarable without importing the subprocess that implements it.

    This is what acceptance criterion 1's word "injectable" buys: a consumer — and every
    hermetic test — depends on the port module, and only production wiring reaches the
    module that spawns `llm-provider-manager`.
    """
    assert (_MODULE_ROOT / "_dispatcher_credential_manager.py").is_file()
    assert (_MODULE_ROOT / "_dispatcher_credential_manager_wire.py").is_file()

    port = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager"
    )

    assert "subprocess" not in port.__dict__
    assert port.CredentialManagerClient is not None


def test_the_receipt_carries_no_field_that_could_hold_a_credential() -> None:
    """`CredentialReceipt` is secret-free BY CONSTRUCTION, not by convention."""
    receipt = CredentialReceipt(**_receipt_payload())

    assert set(receipt.__dataclass_fields__) == set(RECEIPT_MEMBERS)
    assert "value" not in receipt.__dataclass_fields__


def test_a_provisioned_credential_pairs_the_value_with_its_receipt() -> None:
    provisioned = ProvisionedCredential(
        receipt=CredentialReceipt(**_receipt_payload()), value="sk-live-value"
    )

    assert provisioned.value == "sk-live-value"
    assert provisioned.receipt.record_id == _RECORD_ID


# ---------------------------------------------------------------------------
# Request objects — closed member sets, graded whole
# ---------------------------------------------------------------------------


def test_the_target_request_names_only_the_three_members_the_manager_accepts() -> None:
    assert target_request_object(consumer_run_id=_RUN_ID) == {
        "version": 1,
        "consumer_run_id": _RUN_ID,
        "adapter": ISOLATED_RUN_ADAPTER,
    }


def test_the_provision_request_asks_for_an_anthropic_inference_credential_at_factory_purpose() -> (
    None
):
    """Acceptance criterion 1's four coordinates, spelled as the manager's registry does.

    `strategy` and `lease_seconds` are absent on purpose: both default manager-side, and
    sending the default would move the strategy decision into this consumer.
    """
    request = provision_request_object(consumer_run_id=_RUN_ID, target_ref="ref-abc")

    assert request == {
        "version": 1,
        "provider": ANTHROPIC_PROVIDER,
        "kind": INFERENCE_KIND,
        "purpose": FACTORY_PURPOSE,
        "consumer_run_id": _RUN_ID,
        "target_ref": "ref-abc",
    }
    assert "strategy" not in request
    assert "lease_seconds" not in request


def test_the_report_request_carries_the_four_identity_members_and_no_diagnostic() -> None:
    """Idempotency is keyed on exactly these four, so nothing else may ride along."""
    report = RunFailureReport(
        consumer_run_id=_RUN_ID,
        record_id=_RECORD_ID,
        occurred_at="2026-09-12T09:30:00Z",
        classification="authentication",
    )

    assert report_request_object(report=report) == {
        "version": 1,
        "consumer_run_id": _RUN_ID,
        "record_id": _RECORD_ID,
        "occurred_at": "2026-09-12T09:30:00Z",
        "classification": "authentication",
    }
    assert "diagnostic" not in report_request_object(report=report)


def test_the_run_registration_names_the_consumer_owned_destination() -> None:
    assert run_registration_object(
        consumer_run_id=_RUN_ID,
        isolated_root="/tmp/run-root",
        target_path="/tmp/run-root/credential",
        created_at="2026-09-12T09:00:00Z",
        expires_at="2026-09-12T10:00:00Z",
    ) == {
        "version": 1,
        "consumer_run_id": _RUN_ID,
        "isolated_root": "/tmp/run-root",
        "target_path": "/tmp/run-root/credential",
        "created_at": "2026-09-12T09:00:00Z",
        "expires_at": "2026-09-12T10:00:00Z",
    }


def test_every_report_classification_the_protocol_allows_is_declared() -> None:
    assert REPORT_CLASSIFICATIONS == (
        "authentication",
        "rate-limit",
        "provider-outage",
        "unknown",
    )


# ---------------------------------------------------------------------------
# Response parsing — success, declared refusal, and every malformed shape
# ---------------------------------------------------------------------------


def test_a_successful_target_response_yields_its_reference() -> None:
    stdout = _ok(operation="target", target_ref="ref-abc", expires_at="2026-09-13T09:00:00Z")

    assert parse_target_response(stdout=stdout) == "ref-abc"


def test_a_successful_provision_response_yields_the_secret_free_receipt() -> None:
    stdout = _ok(operation="provision", receipt=_receipt_payload())

    parsed = parse_provision_response(stdout=stdout)

    assert parsed == CredentialReceipt(**_receipt_payload())


def test_a_successful_report_response_is_no_refusal_at_all() -> None:
    assert parse_report_response(stdout=_ok(operation="report", duplicate=True)) is None


@pytest.mark.parametrize(
    ("error_type", "expected_remedy_fragment"),
    [
        ("retryable-exhaustion", "llm-provider-manager acquire"),
        ("store-unavailable", "1Password service-account keyring"),
        ("provisioning-failed", "mode 0700"),
        ("invalid-request", "consumer-protocol defect"),
        ("internal-bug", "file it against livespec-overseer"),
        ("a-type-from-the-future", "does not model"),
    ],
)
def test_each_manager_error_type_carries_its_own_actionable_remedy(
    error_type: str, expected_remedy_fragment: str
) -> None:
    """Acceptance criterion 3's "actionable": the remedy is chosen from the TYPE.

    The manager's own `message` is redacted prose it authored; what an operator should
    DO about an exhausted pool differs from an unreachable store, and only this consumer
    knows its own operational context.
    """
    import json

    stdout = json.dumps(
        {"version": 1, "status": "error", "error_type": error_type, "message": "redacted."}
    )

    parsed = parse_provision_response(stdout=stdout)

    assert isinstance(parsed, ManagerRefusal)
    assert parsed.error_type == error_type
    assert expected_remedy_fragment in parsed.remedy


def test_an_error_response_without_a_message_still_refuses_legibly() -> None:
    import json

    stdout = json.dumps({"version": 1, "status": "error", "error_type": "store-unavailable"})

    parsed = parse_target_response(stdout=stdout)

    assert isinstance(parsed, ManagerRefusal)
    assert parsed.message == "(no message given)"


@pytest.mark.parametrize(
    "stdout",
    [
        pytest.param("not json at all", id="not-json"),
        pytest.param("[1, 2, 3]", id="not-an-object"),
        pytest.param('{"version": 1, "status": "ok", "operation": "report"}', id="wrong-operation"),
        pytest.param('{"version": 1, "status": "surprise"}', id="unmodelled-status"),
        pytest.param('{"version": 1, "status": "error", "error_type": ""}', id="empty-error-type"),
    ],
)
def test_a_response_this_build_cannot_model_becomes_a_refusal_not_a_record(stdout: str) -> None:
    parsed = parse_provision_response(stdout=stdout)

    assert isinstance(parsed, ManagerRefusal)
    assert parsed.error_type == MALFORMED_RESPONSE_TYPE


def test_a_target_response_without_a_usable_reference_is_malformed() -> None:
    assert isinstance(
        parse_target_response(stdout=_ok(operation="target", target_ref="")), ManagerRefusal
    )


def test_a_provision_response_without_a_receipt_object_is_malformed() -> None:
    parsed = parse_provision_response(stdout=_ok(operation="provision", receipt="not-an-object"))

    assert isinstance(parsed, ManagerRefusal)
    assert "no receipt object" in parsed.message


@pytest.mark.parametrize(
    ("mutate", "case"),
    [
        pytest.param(lambda members: members.pop("account_id"), "missing-member", id="missing"),
        pytest.param(lambda members: members.update(extra="x"), "extra-member", id="extra"),
        pytest.param(lambda members: members.update(record_id=""), "empty-member", id="empty"),
    ],
)
def test_a_receipt_that_is_not_exactly_the_five_members_is_malformed(
    mutate: object, case: str
) -> None:
    """Closed in BOTH directions: an extra member could only come from another protocol."""
    members = _receipt_payload()
    _ = case
    assert callable(mutate)
    _ = mutate(members)

    parsed = parse_provision_response(stdout=_ok(operation="provision", receipt=members))

    assert isinstance(parsed, ManagerRefusal)
    assert parsed.error_type == MALFORMED_RESPONSE_TYPE


def test_a_receipt_whose_member_is_not_a_string_is_malformed() -> None:
    members: dict[str, object] = {**_receipt_payload(), "lease_expires_at": 17}

    parsed = parse_provision_response(stdout=_ok(operation="provision", receipt=members))

    assert isinstance(parsed, ManagerRefusal)


# ---------------------------------------------------------------------------
# The refusal an operator actually reads
# ---------------------------------------------------------------------------


def test_the_dispatch_refusal_names_the_request_that_failed_and_what_to_do() -> None:
    detail = manager_refusal_detail(
        refusal=refusal(error_type="retryable-exhaustion", message="no valid credential.")
    )

    assert "llm-provider-manager could not provision" in detail
    assert ANTHROPIC_PROVIDER in detail
    assert INFERENCE_KIND in detail
    assert FACTORY_PURPOSE in detail
    assert "retryable-exhaustion" in detail
    assert "no valid credential." in detail
    assert "Remedy: " in detail
