"""The production llm-provider-manager client and the isolated target it offers.

Only the PROCESS is stood in — a runner returning canned manager stdout. Everything else
runs for real: the 0700 target directory is created on disk and its mode inspected, the
run registration is written and read back, the credential is read out of the file a real
manager would have written, and the teardown is observed rather than assumed.

The refusal cases all assert the same two things together: that the refusal is typed, and
that the destination was left in the state the contract requires. Asserting only the
refusal would pass against a client that wrote bytes and then reported failure.
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    CredentialReceipt,
    ManagerRefusal,
    ProvisionedCredential,
    RunFailureReport,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_io import (
    MANAGER_EXECUTABLE,
    MANAGER_TIMEOUT_SECONDS,
    LlmProviderManagerClient,
    ManagerCommandResult,
    manager_argv,
    run_manager_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_target import (
    MANAGER_STATE_REL,
    IsolatedTarget,
    credential_target_root,
    discard_isolated_target,
    manager_state_dir,
    prepare_isolated_target,
    read_provisioned_value,
    registration_window,
    rfc3339_second,
    run_registration_path,
)

_RUN_ID = "dispatch-io-1"
_RECORD_ID = "5f1b7a0c-0000-4000-8000-00000000cafe"
_CREDENTIAL = "sk-ant-oat-provisioned"
_NOW = 1_789_000_000.0


def _receipt_payload() -> dict[str, str]:
    return {
        "record_id": _RECORD_ID,
        "account_id": "anthropic-2",
        "validated_at": "2026-09-12T08:00:00Z",
        "purpose": "factory",
        "lease_expires_at": "2026-09-12T14:00:00Z",
    }


class _ScriptedManager:
    """A manager process stand-in: canned stdout per command, argv recorded.

    `writes` is what a real manager's final provisioning adapter does — it puts the
    selected credential in the registered destination. Driving it through the same
    `provision` call the client makes is what lets the success case read a value the
    client did not plant itself.
    """

    def __init__(
        self,
        *,
        responses: dict[str, str],
        writes: Path | None = None,
        transport_error: str | None = None,
        transport_fails_on: tuple[str, ...] = (),
    ) -> None:
        self.responses = responses
        self.writes = writes
        self.transport_error = transport_error
        # Which commands never reach a manager at all. Named per command so a test can
        # put the launch failure at the SECOND call, where the client has already
        # written a registration and holds a reference.
        self.transport_fails_on = transport_fails_on
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, *, command: str, request: dict[str, object]) -> ManagerCommandResult:
        self.calls.append((command, request))
        if self.transport_error is not None and (
            not self.transport_fails_on or command in self.transport_fails_on
        ):
            return ManagerCommandResult(stdout="", transport_error=self.transport_error)
        if command == "provision" and self.writes is not None:
            _ = self.writes.write_text(f"{_CREDENTIAL}\n", encoding="utf-8")
        return ManagerCommandResult(stdout=self.responses[command])


def _ok(*, operation: str, **members: object) -> str:
    return json.dumps({"version": 1, "status": "ok", "operation": operation, **members})


def _error(*, error_type: str, message: str = "redacted.") -> str:
    return json.dumps(
        {"version": 1, "status": "error", "error_type": error_type, "message": message}
    )


def _client(
    *, tmp_path: Path, manager: _ScriptedManager, state_dir: Path
) -> LlmProviderManagerClient:
    return LlmProviderManagerClient(
        temp_dir=tmp_path,
        runner=manager,
        state_dir=lambda: state_dir,
        clock=lambda: _NOW,
    )


# ---------------------------------------------------------------------------
# The consumer-owned isolated target
# ---------------------------------------------------------------------------


def test_the_per_run_target_directory_is_created_at_the_mode_the_adapter_requires(
    tmp_path: Path,
) -> None:
    """0700 is a PRECONDITION: the adapter refuses to create or chmod it itself."""
    target = prepare_isolated_target(temp_dir=tmp_path, consumer_run_id=_RUN_ID)

    assert isinstance(target, IsolatedTarget)
    assert target.isolated_root == credential_target_root(
        temp_dir=tmp_path, consumer_run_id=_RUN_ID
    )
    assert stat.S_IMODE(target.isolated_root.stat().st_mode) == 0o700
    assert target.target_path.parent == target.isolated_root


def test_preparing_a_target_clears_whatever_a_previous_dispatch_left_behind(
    tmp_path: Path,
) -> None:
    root = credential_target_root(temp_dir=tmp_path, consumer_run_id=_RUN_ID)
    root.mkdir(parents=True)
    stale = root / "credential"
    _ = stale.write_text("another-run-credential", encoding="utf-8")

    target = prepare_isolated_target(temp_dir=tmp_path, consumer_run_id=_RUN_ID)

    assert isinstance(target, IsolatedTarget)
    assert not stale.exists()


def test_an_uncreatable_target_directory_refuses_with_an_actionable_string(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "not-a-dir"
    _ = blocked.write_text("", encoding="utf-8")

    target = prepare_isolated_target(temp_dir=blocked, consumer_run_id=_RUN_ID)

    assert isinstance(target, str)
    assert "could not be created" in target
    assert "refuses to create or chmod it itself" in target


def test_reading_a_target_that_holds_nothing_usable_answers_none(tmp_path: Path) -> None:
    target = prepare_isolated_target(temp_dir=tmp_path, consumer_run_id=_RUN_ID)
    assert isinstance(target, IsolatedTarget)

    assert read_provisioned_value(target=target) is None

    _ = target.target_path.write_text("   \n", encoding="utf-8")
    assert read_provisioned_value(target=target) is None


def test_discarding_a_target_removes_the_credential_copy_and_tolerates_absence(
    tmp_path: Path,
) -> None:
    target = prepare_isolated_target(temp_dir=tmp_path, consumer_run_id=_RUN_ID)
    assert isinstance(target, IsolatedTarget)
    _ = target.target_path.write_text(_CREDENTIAL, encoding="utf-8")

    discard_isolated_target(target=target)
    assert not target.isolated_root.exists()

    discard_isolated_target(target=target)  # second call must not raise


def test_the_manager_state_directory_is_resolved_from_the_account_database() -> None:
    """Not from `HOME`: the manager resolves it that way, so a consumer must too."""
    resolved = manager_state_dir()

    assert resolved.is_absolute()
    assert resolved.parts[-len(MANAGER_STATE_REL.parts) :] == MANAGER_STATE_REL.parts


def test_the_registration_path_is_keyed_by_the_digest_the_adapter_expects(
    tmp_path: Path,
) -> None:
    import hashlib

    path = run_registration_path(state_dir=tmp_path, consumer_run_id=_RUN_ID)

    digest = hashlib.sha256(_RUN_ID.encode("utf-8")).hexdigest()
    assert path == tmp_path / "run-registrations" / f"{digest}.json"


def test_the_registration_window_opens_now_and_closes_within_the_contract_cap() -> None:
    created_at, expires_at = registration_window(now_epoch=_NOW)

    assert created_at == rfc3339_second(epoch=_NOW)
    assert expires_at == rfc3339_second(epoch=_NOW + 3600)
    assert expires_at > created_at


# ---------------------------------------------------------------------------
# The client's argv
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "flag"),
    [("target", "--target-json"), ("provision", "--request-json"), ("report", "--report-json")],
)
def test_each_command_reads_its_object_from_standard_input(command: str, flag: str) -> None:
    """`-` is the contract's stdin spelling; a temp FILE would put the request on disk."""
    assert manager_argv(command=command) == (MANAGER_EXECUTABLE, command, flag, "-")


# ---------------------------------------------------------------------------
# The real process seam
# ---------------------------------------------------------------------------


def test_the_request_object_is_written_to_the_manager_stdin_and_stdout_is_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production spawn path, with only `subprocess.run` itself replaced.

    Asserting the argv AND the stdin payload together is what proves the request reaches
    the manager through a pipe rather than a temporary file it could be made to read.
    """
    seen: dict[str, object] = {}

    class _Completed:
        stdout = '{"version":1,"status":"ok","operation":"report","duplicate":false}'

    def fake_run(argv: object, **kwargs: object) -> _Completed:
        seen["argv"] = argv
        seen.update(kwargs)
        return _Completed()

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_io"
        ".subprocess.run",
        fake_run,
    )

    result = run_manager_command(command="report", request={"version": 1})

    assert result.transport_error is None
    assert result.stdout == _Completed.stdout
    assert seen["argv"] == manager_argv(command="report")
    assert seen["input"] == json.dumps({"version": 1})
    assert seen["check"] is False
    assert seen["timeout"] == MANAGER_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(FileNotFoundError(2, "No such file or directory"), id="absent-executable"),
        pytest.param(subprocess.TimeoutExpired(cmd="x", timeout=1.0), id="timed-out"),
    ],
)
def test_a_manager_that_could_not_be_launched_or_finished_answers_a_transport_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fake_run(argv: object, **kwargs: object) -> object:
        _ = (argv, kwargs)
        raise error

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_io"
        ".subprocess.run",
        fake_run,
    )

    result = run_manager_command(command="target", request={"version": 1})

    assert result.stdout == ""
    assert result.transport_error is not None
    assert type(error).__name__ in result.transport_error


# ---------------------------------------------------------------------------
# Provisioning, end to end through the client
# ---------------------------------------------------------------------------


def test_a_successful_provision_registers_issues_provisions_and_reads_the_value_back(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "manager-state"
    destination = credential_target_root(temp_dir=tmp_path, consumer_run_id=_RUN_ID) / "credential"
    manager = _ScriptedManager(
        responses={
            "target": _ok(
                operation="target", target_ref="ref-1", expires_at="2026-09-13T09:00:00Z"
            ),
            "provision": _ok(operation="provision", receipt=_receipt_payload()),
        },
        writes=destination,
    )

    provisioned = _client(tmp_path=tmp_path, manager=manager, state_dir=state_dir).provision(
        consumer_run_id=_RUN_ID
    )

    assert isinstance(provisioned, ProvisionedCredential)
    assert provisioned.value == _CREDENTIAL
    assert provisioned.receipt == CredentialReceipt(**_receipt_payload())
    assert [command for command, _ in manager.calls] == ["target", "provision"]


def test_the_run_registration_is_written_before_a_reference_is_requested(
    tmp_path: Path,
) -> None:
    """The adapter reads this file to learn the destination, so order is load-bearing."""
    state_dir = tmp_path / "manager-state"
    destination = credential_target_root(temp_dir=tmp_path, consumer_run_id=_RUN_ID) / "credential"
    registration_path = run_registration_path(state_dir=state_dir, consumer_run_id=_RUN_ID)
    seen: list[bool] = []

    class _RegistrationWatchingManager(_ScriptedManager):
        def __call__(self, *, command: str, request: dict[str, object]) -> ManagerCommandResult:
            seen.append(registration_path.is_file())
            return super().__call__(command=command, request=request)

    manager = _RegistrationWatchingManager(
        responses={
            "target": _ok(
                operation="target", target_ref="ref-1", expires_at="2026-09-13T09:00:00Z"
            ),
            "provision": _ok(operation="provision", receipt=_receipt_payload()),
        },
        writes=destination,
    )

    _ = _client(tmp_path=tmp_path, manager=manager, state_dir=state_dir).provision(
        consumer_run_id=_RUN_ID
    )

    assert seen[0] is True
    record = json.loads(registration_path.read_text(encoding="utf-8"))
    assert record["consumer_run_id"] == _RUN_ID
    assert record["target_path"] == str(destination)
    assert record["isolated_root"] == str(destination.parent)
    assert stat.S_IMODE(registration_path.stat().st_mode) == 0o600


def test_the_credential_copy_is_discarded_once_it_reaches_the_caller(tmp_path: Path) -> None:
    """A second copy of a live credential on disk has no further purpose."""
    state_dir = tmp_path / "manager-state"
    root = credential_target_root(temp_dir=tmp_path, consumer_run_id=_RUN_ID)
    manager = _ScriptedManager(
        responses={
            "target": _ok(
                operation="target", target_ref="ref-1", expires_at="2026-09-13T09:00:00Z"
            ),
            "provision": _ok(operation="provision", receipt=_receipt_payload()),
        },
        writes=root / "credential",
    )

    _ = _client(tmp_path=tmp_path, manager=manager, state_dir=state_dir).provision(
        consumer_run_id=_RUN_ID
    )

    assert not root.exists()


def test_a_refused_target_request_stops_before_any_credential_is_selected(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "manager-state"
    manager = _ScriptedManager(responses={"target": _error(error_type="store-unavailable")})

    provisioned = _client(tmp_path=tmp_path, manager=manager, state_dir=state_dir).provision(
        consumer_run_id=_RUN_ID
    )

    assert isinstance(provisioned, ManagerRefusal)
    assert provisioned.error_type == "store-unavailable"
    assert [command for command, _ in manager.calls] == ["target"]


def test_a_refused_provision_returns_its_type_and_leaves_no_credential_behind(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "manager-state"
    root = credential_target_root(temp_dir=tmp_path, consumer_run_id=_RUN_ID)
    manager = _ScriptedManager(
        responses={
            "target": _ok(
                operation="target", target_ref="ref-1", expires_at="2026-09-13T09:00:00Z"
            ),
            "provision": _error(error_type="retryable-exhaustion", message="pool exhausted."),
        }
    )

    provisioned = _client(tmp_path=tmp_path, manager=manager, state_dir=state_dir).provision(
        consumer_run_id=_RUN_ID
    )

    assert isinstance(provisioned, ManagerRefusal)
    assert provisioned.error_type == "retryable-exhaustion"
    assert not root.exists()


def test_a_success_that_wrote_no_credential_is_refused_rather_than_projected(
    tmp_path: Path,
) -> None:
    """An empty destination after `ok` breaks the adapter's own atomic-write guarantee."""
    state_dir = tmp_path / "manager-state"
    manager = _ScriptedManager(
        responses={
            "target": _ok(
                operation="target", target_ref="ref-1", expires_at="2026-09-13T09:00:00Z"
            ),
            "provision": _ok(operation="provision", receipt=_receipt_payload()),
        }
    )

    provisioned = _client(tmp_path=tmp_path, manager=manager, state_dir=state_dir).provision(
        consumer_run_id=_RUN_ID
    )

    assert isinstance(provisioned, ManagerRefusal)
    assert "holds no credential" in provisioned.message


def test_an_unwritable_registration_refuses_before_the_manager_is_called(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "manager-state"
    _ = blocked.write_text("", encoding="utf-8")
    manager = _ScriptedManager(responses={})

    provisioned = _client(tmp_path=tmp_path, manager=manager, state_dir=blocked).provision(
        consumer_run_id=_RUN_ID
    )

    assert isinstance(provisioned, ManagerRefusal)
    assert "run registration" in provisioned.message
    assert manager.calls == []


def test_an_unpreparable_target_refuses_as_a_provisioning_failure(tmp_path: Path) -> None:
    blocked = tmp_path / "temp-root"
    _ = blocked.write_text("", encoding="utf-8")
    manager = _ScriptedManager(responses={})

    provisioned = LlmProviderManagerClient(
        temp_dir=blocked,
        runner=manager,
        state_dir=lambda: tmp_path / "manager-state",
        clock=lambda: _NOW,
    ).provision(consumer_run_id=_RUN_ID)

    assert isinstance(provisioned, ManagerRefusal)
    assert provisioned.error_type == "provisioning-failed"
    assert manager.calls == []


@pytest.mark.parametrize("command", ["target", "provision"])
def test_a_manager_that_never_ran_refuses_as_unreachable_and_names_the_install(
    tmp_path: Path, command: str
) -> None:
    """An absent executable is an INTEGRATION FAILURE, never a fallback to a legacy pool."""
    state_dir = tmp_path / "manager-state"
    destination = credential_target_root(temp_dir=tmp_path, consumer_run_id=_RUN_ID) / "credential"
    manager = _ScriptedManager(
        responses={
            "target": _ok(
                operation="target", target_ref="ref-1", expires_at="2026-09-13T09:00:00Z"
            ),
            "provision": _ok(operation="provision", receipt=_receipt_payload()),
        },
        writes=destination,
        transport_error="FileNotFoundError: llm-provider-manager",
        transport_fails_on=(command,),
    )

    provisioned = _client(tmp_path=tmp_path, manager=manager, state_dir=state_dir).provision(
        consumer_run_id=_RUN_ID
    )

    assert isinstance(provisioned, ManagerRefusal)
    assert provisioned.error_type == "manager-unreachable"
    assert MANAGER_EXECUTABLE in provisioned.message
    assert "Install the livespec-overseer package" in provisioned.remedy


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _report() -> RunFailureReport:
    return RunFailureReport(
        consumer_run_id=_RUN_ID,
        record_id=_RECORD_ID,
        occurred_at="2026-09-12T09:30:00Z",
        classification="authentication",
    )


def test_an_accepted_report_returns_no_refusal_and_sends_only_the_four_members(
    tmp_path: Path,
) -> None:
    manager = _ScriptedManager(responses={"report": _ok(operation="report", duplicate=False)})

    outcome = _client(tmp_path=tmp_path, manager=manager, state_dir=tmp_path / "s").report(
        report=_report()
    )

    assert outcome is None
    command, request = manager.calls[0]
    assert command == "report"
    assert set(request) == {
        "version",
        "consumer_run_id",
        "record_id",
        "occurred_at",
        "classification",
    }


def test_a_duplicate_report_is_still_an_acceptance(tmp_path: Path) -> None:
    """Idempotency is the manager's answer to a retry, not an error for the consumer."""
    manager = _ScriptedManager(responses={"report": _ok(operation="report", duplicate=True)})

    assert (
        _client(tmp_path=tmp_path, manager=manager, state_dir=tmp_path / "s").report(
            report=_report()
        )
        is None
    )


def test_a_refused_report_is_surfaced_rather_than_raised(tmp_path: Path) -> None:
    manager = _ScriptedManager(responses={"report": _error(error_type="invalid-report")})

    outcome = _client(tmp_path=tmp_path, manager=manager, state_dir=tmp_path / "s").report(
        report=_report()
    )

    assert isinstance(outcome, ManagerRefusal)
    assert outcome.error_type == "invalid-report"


def test_a_report_that_could_not_reach_the_manager_is_surfaced_as_unreachable(
    tmp_path: Path,
) -> None:
    manager = _ScriptedManager(responses={}, transport_error="FileNotFoundError: absent")

    outcome = _client(tmp_path=tmp_path, manager=manager, state_dir=tmp_path / "s").report(
        report=_report()
    )

    assert isinstance(outcome, ManagerRefusal)
    assert outcome.error_type == "manager-unreachable"
