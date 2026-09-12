"""The llm-provider-manager consumer wire protocol: exact objects in, typed results out.

Every object built here is fixed member-for-member by livespec-overseer
`SPECIFICATION/contracts.md` section "The LLM credential-provider operation". The manager
validates its input shape BEFORE recovery and refuses `invalid-request` on a missing
member, an unknown member or a wrong version — so a builder that guesses a field is not a
lenient client, it is a client whose every request is refused.

THE PARSERS ARE STRICT IN THE SAME DIRECTION, AND THAT IS THE POINT. A manager answer is
a single-line JSON object whose success shape is closed. A response carrying an
unexpected receipt member, or a `status` this build does not model, is a response from a
manager speaking a protocol we do not implement; reading it optimistically would mean
provisioning a credential on terms we did not agree to. So anything that is not exactly
the modelled success shape becomes a `ManagerRefusal`, never an exception and never a
partially-trusted record.

WHY REFUSALS ARE DATA AND NOT EXCEPTIONS. A manager refusal is an EXPECTED outcome of a
correct dispatch — an exhausted pool is the system working. It therefore travels the same
error-as-data rail every other dispatch-stage refusal travels, so the loop reports it at
the `run-config-overlay` stage instead of unwinding to the supervisor.

THE REMEDY IS CHOSEN FROM THE ERROR TYPE, NOT FROM THE MESSAGE. The manager's `message` is
redacted prose it authored; what an operator should DO about a `retryable-exhaustion`
differs from a `store-unavailable`, and that mapping belongs to the consumer that knows
its own operational context. `_REMEDIES` is that mapping, complete over the manager's
closed error-type set plus this module's own transport classifications.
"""

from __future__ import annotations

import json
from typing import Final, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    ANTHROPIC_PROVIDER,
    FACTORY_PURPOSE,
    INFERENCE_KIND,
    ISOLATED_RUN_ADAPTER,
    MANAGER_PROTOCOL_VERSION,
    RECEIPT_MEMBERS,
    CredentialReceipt,
    ManagerRefusal,
    RunFailureReport,
)

__all__: list[str] = [
    "MALFORMED_RESPONSE_TYPE",
    "TRANSPORT_FAILURE_TYPE",
    "parse_provision_response",
    "parse_report_response",
    "parse_target_response",
    "provision_request_object",
    "refusal",
    "report_request_object",
    "run_registration_object",
    "target_request_object",
]

# The two classifications this consumer mints itself. They are deliberately NOT spelled
# like the manager's own types: a refusal we invented because the manager never answered
# must not be mistakable for one the manager returned.
TRANSPORT_FAILURE_TYPE: Final = "manager-unreachable"
MALFORMED_RESPONSE_TYPE: Final = "manager-response-malformed"

_OK_STATUS: Final = "ok"
_ERROR_STATUS: Final = "error"

_INSTALL_REMEDY: Final = (
    "Install the livespec-overseer package on this factory host and make the "
    "`llm-provider-manager` console entry point resolvable on the Dispatcher's PATH; "
    "consumer-host installation is an integration prerequisite of the credential "
    "protocol, not something a dispatch can provision for itself."
)
_REMEDIES: Final[dict[str, str]] = {
    TRANSPORT_FAILURE_TYPE: _INSTALL_REMEDY,
    MALFORMED_RESPONSE_TYPE: (
        "The manager answered in a shape this Dispatcher build does not model. Upgrade "
        "this plugin build to one whose consumer protocol matches the installed "
        "llm-provider-manager, and do not hand-edit the response."
    ),
    "invalid-request": (
        "This Dispatcher built a request the manager rejected. Report it as a "
        "consumer-protocol defect; do not retry the same dispatch expecting a "
        "different answer."
    ),
    "invalid-report": (
        "This Dispatcher built a failure report the manager rejected. Report it as a "
        "consumer-protocol defect; the run outcome itself is unaffected."
    ),
    "retryable-exhaustion": (
        "No valid credential satisfies this request right now, and the manager refused "
        "rather than provision a stale or suspect one. Acquire or revalidate an "
        "Anthropic account through `llm-provider-manager acquire`, then re-dispatch."
    ),
    "store-unavailable": (
        "The manager could not reach its secret store. Check the host's 1Password "
        "service-account keyring seeding and vault namespace binding, then re-dispatch."
    ),
    "provisioning-failed": (
        "The manager selected a credential but could not write it to this run's "
        "isolated target. Check that the per-run credential directory exists, is owned "
        "by the dispatching user and is mode 0700, then re-dispatch."
    ),
    "internal-bug": (
        "The manager reported an internal bug. Capture its output and file it against "
        "livespec-overseer; do not re-dispatch until it is diagnosed."
    ),
}
_UNKNOWN_TYPE_REMEDY: Final = (
    "The manager returned an error type this Dispatcher build does not model. Capture "
    "its output and file it against livespec-overseer."
)


def refusal(*, error_type: str, message: str) -> ManagerRefusal:
    """One typed refusal, with the remedy resolved from its type."""
    return ManagerRefusal(
        error_type=error_type,
        message=message,
        remedy=_REMEDIES.get(error_type, _UNKNOWN_TYPE_REMEDY),
    )


def run_registration_object(
    *,
    consumer_run_id: str,
    isolated_root: str,
    target_path: str,
    created_at: str,
    expires_at: str,
) -> dict[str, object]:
    """The `isolated-run` adapter's registration input, which THIS consumer owns.

    The manager reads this file to learn where a run's isolated target lives; the
    contract leaves its creation to the consumer's own contract, which is why it is
    built here rather than requested from the manager.
    """
    return {
        "version": MANAGER_PROTOCOL_VERSION,
        "consumer_run_id": consumer_run_id,
        "isolated_root": isolated_root,
        "target_path": target_path,
        "created_at": created_at,
        "expires_at": expires_at,
    }


def target_request_object(*, consumer_run_id: str) -> dict[str, object]:
    """The `target` request: issue one opaque reference bound to this run."""
    return {
        "version": MANAGER_PROTOCOL_VERSION,
        "consumer_run_id": consumer_run_id,
        "adapter": ISOLATED_RUN_ADAPTER,
    }


def provision_request_object(*, consumer_run_id: str, target_ref: str) -> dict[str, object]:
    """The `provision` request for an Anthropic inference credential at factory purpose.

    `strategy` and `lease_seconds` are deliberately omitted: both are optional with
    manager-side defaults, and the ratified default production strategy IS the manager's
    own `consume-first`. Sending the default explicitly would make this consumer the
    place a strategy change has to be made.
    """
    return {
        "version": MANAGER_PROTOCOL_VERSION,
        "provider": ANTHROPIC_PROVIDER,
        "kind": INFERENCE_KIND,
        "purpose": FACTORY_PURPOSE,
        "consumer_run_id": consumer_run_id,
        "target_ref": target_ref,
    }


def report_request_object(*, report: RunFailureReport) -> dict[str, object]:
    """The `report` request: exactly the four identity members, and no diagnostic."""
    return {
        "version": MANAGER_PROTOCOL_VERSION,
        "consumer_run_id": report.consumer_run_id,
        "record_id": report.record_id,
        "occurred_at": report.occurred_at,
        "classification": report.classification,
    }


def parse_target_response(*, stdout: str) -> str | ManagerRefusal:
    """The issued `target_ref`, or a typed refusal."""
    payload = _success_payload(stdout=stdout, operation="target")
    if isinstance(payload, ManagerRefusal):
        return payload
    reference = payload.get("target_ref")
    if not isinstance(reference, str) or reference == "":
        return refusal(
            error_type=MALFORMED_RESPONSE_TYPE,
            message="target response carries no non-empty target_ref.",
        )
    return reference


def parse_provision_response(*, stdout: str) -> CredentialReceipt | ManagerRefusal:
    """The secret-free receipt of a successful provision, or a typed refusal."""
    payload = _success_payload(stdout=stdout, operation="provision")
    if isinstance(payload, ManagerRefusal):
        return payload
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict):
        return refusal(
            error_type=MALFORMED_RESPONSE_TYPE,
            message="provision response carries no receipt object.",
        )
    members = cast("dict[str, object]", receipt)
    if set(members) != set(RECEIPT_MEMBERS) or not all(
        isinstance(members[name], str) and members[name] != "" for name in RECEIPT_MEMBERS
    ):
        return refusal(
            error_type=MALFORMED_RESPONSE_TYPE,
            message=(
                "provision receipt must carry exactly "
                f"{', '.join(RECEIPT_MEMBERS)} as non-empty strings."
            ),
        )
    return CredentialReceipt(**{name: cast("str", members[name]) for name in RECEIPT_MEMBERS})


def parse_report_response(*, stdout: str) -> ManagerRefusal | None:
    """None when the manager accepted or deduplicated the report; else a typed refusal."""
    payload = _success_payload(stdout=stdout, operation="report")
    return payload if isinstance(payload, ManagerRefusal) else None


def _success_payload(*, stdout: str, operation: str) -> dict[str, object] | ManagerRefusal:
    """The decoded success object for `operation`, or the refusal it really was."""
    try:
        decoded = json.loads(stdout)
    except ValueError:
        return refusal(
            error_type=MALFORMED_RESPONSE_TYPE,
            message=f"{operation} response was not a single JSON object.",
        )
    if not isinstance(decoded, dict):
        return refusal(
            error_type=MALFORMED_RESPONSE_TYPE,
            message=f"{operation} response was not a JSON object.",
        )
    payload = cast("dict[str, object]", decoded)
    if payload.get("status") == _ERROR_STATUS:
        return _declared_refusal(payload=payload, operation=operation)
    if payload.get("status") != _OK_STATUS or payload.get("operation") != operation:
        return refusal(
            error_type=MALFORMED_RESPONSE_TYPE,
            message=f'{operation} response declared neither an "ok" nor an "error" status.',
        )
    return payload


def _declared_refusal(*, payload: dict[str, object], operation: str) -> ManagerRefusal:
    """The manager's own typed error, normalized onto this consumer's refusal shape."""
    error_type = payload.get("error_type")
    message = payload.get("message")
    if not isinstance(error_type, str) or error_type == "":
        return refusal(
            error_type=MALFORMED_RESPONSE_TYPE,
            message=f"{operation} error response carries no error_type.",
        )
    return refusal(
        error_type=error_type,
        message=message if isinstance(message, str) and message != "" else "(no message given)",
    )
