"""The one llm-provider-manager client that actually runs the manager executable.

`_dispatcher_credential_manager` declares the port; this module supplies its production
implementation. The split is what lets every other module — and every hermetic test —
depend on the seam rather than on a subprocess that holds real credentials.

THE SEQUENCE IS FIXED BY THE MANAGER'S CONTRACT, NOT CHOSEN HERE. A dispatch must
(1) write the run registration the `isolated-run` adapter reads, (2) ask `target` for an
opaque reference bound to this run, (3) ask `provision` to select an account and write its
credential to the registered destination, and (4) read those bytes back. Steps 2 and 3 are
separate manager commands because the reference must be issued and PERSISTED before any
credential is selected: that ordering is what makes a refusal leave the destination
byte-identical, since selection never runs until the destination is already proven.

EVERY REFUSAL PATH DISCARDS THE TARGET, AND THE OVERLAY IS NEVER TOUCHED. `provision`
returns a refusal rather than raising, and the caller's overlay write happens strictly
after a success — so "a manager refusal leaves the overlay byte-identical" is a property
of the CALL ORDER here, not of a cleanup that might not run.

STDIN IS THE ONLY REQUEST CHANNEL. Each command takes `<path|->` and `-` means standard
input. Passing a temporary FILE would put a request object on disk for the manager to
read; passing the object on stdin keeps it in a pipe. Neither request nor response
carries credential bytes — only the target file does, and only for as long as step 4 takes.

THE EXECUTABLE IS RESOLVED FROM `PATH` BY ITS DECLARED CONSOLE NAME. The contract makes
that resolution a consumer-host integration prerequisite, so an absent executable is an
integration failure this client REPORTS (as `manager-unreachable`) rather than a condition
it works around. There is deliberately no fallback to a legacy credential pool: a silent
fallback would mean a factory that believes it is running on manager-selected accounts
while it is not.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    CredentialReceipt,
    ManagerRefusal,
    ProvisionedCredential,
    RunFailureReport,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_target import (
    IsolatedTarget,
    discard_isolated_target,
    manager_state_dir,
    prepare_isolated_target,
    read_provisioned_value,
    registration_window,
    run_registration_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_wire import (
    MALFORMED_RESPONSE_TYPE,
    TRANSPORT_FAILURE_TYPE,
    parse_provision_response,
    parse_report_response,
    parse_target_response,
    provision_request_object,
    refusal,
    report_request_object,
    run_registration_object,
    target_request_object,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "MANAGER_EXECUTABLE",
    "MANAGER_TIMEOUT_SECONDS",
    "LlmProviderManagerClient",
    "ManagerCommandResult",
    "ManagerCommandRunner",
    "manager_argv",
    "run_manager_command",
]

# The console entry point livespec-overseer's package metadata declares.
MANAGER_EXECUTABLE: Final = "llm-provider-manager"

# One bound for every manager command. The manager's own external-call timeout tops out
# at 300 seconds, so a consumer that waited longer would only be waiting on a process
# that has already given up.
MANAGER_TIMEOUT_SECONDS: Final = 300.0

_STDIN_FLAG_BY_COMMAND: Final[dict[str, str]] = {
    "target": "--target-json",
    "provision": "--request-json",
    "report": "--report-json",
}
_REGISTRATION_FILE_MODE: Final = 0o600


@dataclass(frozen=True, kw_only=True)
class ManagerCommandResult:
    """One manager invocation's non-secret result: its stdout, or why it never ran."""

    stdout: str
    transport_error: str | None = None


# The injected process seam. A hermetic test supplies a callable returning canned manager
# stdout; production supplies `run_manager_command`.
ManagerCommandRunner = Callable[..., ManagerCommandResult]


def manager_argv(*, command: str) -> tuple[str, ...]:
    """The exact argv for one consumer-protocol command, reading its object from stdin."""
    return (MANAGER_EXECUTABLE, command, _STDIN_FLAG_BY_COMMAND[command], "-")


def run_manager_command(*, command: str, request: dict[str, object]) -> ManagerCommandResult:
    """Run one manager command, writing `request` to its stdin.

    The exit STATUS is deliberately ignored: the contract requires every invocation to
    write exactly one single-line JSON object to stdout, and that object already carries
    the typed outcome the status merely mirrors. Parsing one channel rather than
    reconciling two removes a class of disagreement between them.
    """
    completed = attempt(
        action=lambda: subprocess.run(  # noqa: S603 - fixed argv, no shell, no caller-supplied executable.
            manager_argv(command=command),
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=MANAGER_TIMEOUT_SECONDS,
            check=False,
        ),
        exceptions=(OSError, subprocess.SubprocessError),
    )
    if isinstance(completed, AttemptFailure):
        return ManagerCommandResult(
            stdout="",
            transport_error=f"{type(completed.error).__name__}: {completed.error}",
        )
    return ManagerCommandResult(stdout=completed.stdout)


@dataclass(frozen=True, kw_only=True)
class LlmProviderManagerClient:
    """The production `CredentialManagerClient`, with every impure input injected."""

    temp_dir: Path
    runner: ManagerCommandRunner = field(default=run_manager_command)
    state_dir: Callable[[], Path] = field(default=manager_state_dir)
    clock: Callable[[], float] = field(default=time.time)

    def provision(self, *, consumer_run_id: str) -> ProvisionedCredential | ManagerRefusal:
        """Register, obtain a reference, provision, and read the credential back."""
        target = prepare_isolated_target(temp_dir=self.temp_dir, consumer_run_id=consumer_run_id)
        if isinstance(target, str):
            return refusal(error_type="provisioning-failed", message=target)
        outcome = self._provision_into(target=target, consumer_run_id=consumer_run_id)
        discard_isolated_target(target=target)
        return outcome

    def report(self, *, report: RunFailureReport) -> ManagerRefusal | None:
        """Send one idempotent, secret-free failure report."""
        result = self.runner(command="report", request=report_request_object(report=report))
        transport = _transport_refusal(result=result, command="report")
        if transport is not None:
            return transport
        return parse_report_response(stdout=result.stdout)

    def _provision_into(
        self, *, target: IsolatedTarget, consumer_run_id: str
    ) -> ProvisionedCredential | ManagerRefusal:
        """The steps between creating the target and discarding it."""
        registration = self._register_run(target=target, consumer_run_id=consumer_run_id)
        if registration is not None:
            return registration
        reference = self._issue_reference(consumer_run_id=consumer_run_id)
        if isinstance(reference, ManagerRefusal):
            return reference
        receipt = self._provision_credential(consumer_run_id=consumer_run_id, target_ref=reference)
        if isinstance(receipt, ManagerRefusal):
            return receipt
        value = read_provisioned_value(target=target)
        if value is None:
            return refusal(
                error_type=MALFORMED_RESPONSE_TYPE,
                message=(
                    "the manager reported a successful provision but its isolated target "
                    f"{target.target_path} holds no credential."
                ),
            )
        return ProvisionedCredential(receipt=receipt, value=value)

    def _register_run(
        self, *, target: IsolatedTarget, consumer_run_id: str
    ) -> ManagerRefusal | None:
        """Write the `isolated-run` adapter's registration input; None on success."""
        created_at, expires_at = registration_window(now_epoch=self.clock())
        path = run_registration_path(state_dir=self.state_dir(), consumer_run_id=consumer_run_id)
        record = run_registration_object(
            consumer_run_id=consumer_run_id,
            isolated_root=str(target.isolated_root),
            target_path=str(target.target_path),
            created_at=created_at,
            expires_at=expires_at,
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(json.dumps(record), encoding="utf-8")
            path.chmod(_REGISTRATION_FILE_MODE)
        except OSError as error:
            return refusal(
                error_type=TRANSPORT_FAILURE_TYPE,
                message=(
                    f"the run registration {path} could not be written "
                    f"({type(error).__name__}: {error})."
                ),
            )
        return None

    def _issue_reference(self, *, consumer_run_id: str) -> str | ManagerRefusal:
        result = self.runner(
            command="target", request=target_request_object(consumer_run_id=consumer_run_id)
        )
        transport = _transport_refusal(result=result, command="target")
        return transport if transport is not None else parse_target_response(stdout=result.stdout)

    def _provision_credential(
        self, *, consumer_run_id: str, target_ref: str
    ) -> CredentialReceipt | ManagerRefusal:
        result = self.runner(
            command="provision",
            request=provision_request_object(
                consumer_run_id=consumer_run_id, target_ref=target_ref
            ),
        )
        transport = _transport_refusal(result=result, command="provision")
        if transport is not None:
            return transport
        return parse_provision_response(stdout=result.stdout)


def _transport_refusal(*, result: ManagerCommandResult, command: str) -> ManagerRefusal | None:
    """The refusal for a manager that never answered, or None when it did."""
    if result.transport_error is None:
        return None
    return refusal(
        error_type=TRANSPORT_FAILURE_TYPE,
        message=(f"`{MANAGER_EXECUTABLE} {command}` could not be run ({result.transport_error})."),
    )
