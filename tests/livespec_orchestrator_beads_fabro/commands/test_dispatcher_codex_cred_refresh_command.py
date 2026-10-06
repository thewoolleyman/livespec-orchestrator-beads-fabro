"""Tests for the guarded Codex refresh command body.

The command is what the five-minute host timer runs
(`livespec-codex-cred-refresh.service`), so it is the half of this item that
decides whether the reconciled refresh guard actually BUYS anything. Widening
eligibility over a refresher that cannot act would only convert a refusal into
an attempt that declines.

It therefore spends the UNGATED app-server `account/read` request rather than
`codex exec`. Upstream gates the ordinary refresh on a five-minute window
(`should_refresh_proactively` in `codex-rs/login/src/auth/manager.rs`), so a
`codex exec` run anywhere in the guard's new five-hour span cannot advance the
expiry; `account/read` with `refreshToken` reaches `AuthManager::refresh_token`
with no expiry predicate at all.

Dropping `codex exec` also drops a PRIVILEGE. The old invocation carried
`--dangerously-bypass-approvals-and-sandbox`, and a hook gate existed solely to
decide whether to pass it, because `exec` runs a model turn that wants a
workspace. `account/read` executes nothing — it is a credential RPC — so no
sandbox bypass is needed, no gate is consulted, and the refresher no longer has
a full-access code path at all.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh import (
    codex_refresh_guard_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    operator_credential_requirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_NOW = 1_000_000

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"


# Any lifetime below the reconciled guard (run budget plus margin) is renewal-due.
# The guard is DERIVED from the requirement this repository's own committed
# workflow resolves, so both figures are positioned relative to the production
# derivation rather than written as literals. `_NOT_DUE_REMAINING` was `100_000`,
# which sat above the retired fixed guard and sits far BELOW the resolved one --
# so the not-due case silently became a due case, and a literal here would keep
# agreeing with itself every time the repository's configuration moved the floor.
#
# `_run` below hands the command `cwd=Path.cwd`, so the requirement it resolves at
# run time is the one resolved here; reading it from the same function is what
# keeps the two in step.
def _guard_seconds() -> int:
    """The eligibility guard this repository's committed workflow resolves."""
    requirement = operator_credential_requirement(repo=Path.cwd())
    assert isinstance(requirement, CredentialLifetimeRequirement), requirement
    return codex_refresh_guard_seconds(run_budget_seconds=requirement.allowance_seconds)


_DUE_REMAINING = 20
_NOT_DUE_REMAINING = _guard_seconds() + 10_000


class _AppServerRunner:
    """Records the app-server conversation the refresher hands it."""

    def __init__(self, *, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[list[str], Path, list[str], float]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        request_lines: list[str],
        timeout_seconds: float,
    ) -> CommandResult:
        self.calls.append((argv, cwd, request_lines, timeout_seconds))
        return self.result


def _auth_json_with_exp(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps({"tokens": {"access_token": f"header.{payload}.sig"}})


def _run(
    *,
    runner: _AppServerRunner,
    reads: object,
    as_json: bool = True,
    dry_run: bool = False,
) -> int:
    module = importlib.import_module(_MODULE)
    read = reads if callable(reads) else (lambda: reads)
    return module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=as_json, dry_run=dry_run),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=read,
        runner_factory=lambda: runner,
    )


def test_refresh_command_module_public_surface() -> None:
    module = importlib.import_module(_MODULE)

    assert module.__all__ == ["run_codex_cred_refresh_with"]


def test_the_timer_spends_the_ungated_account_read_rpc_not_a_gated_exec(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The refresher drives the route that can renew mid-interval.

    This is the load-bearing assertion of the cycle: `codex exec` provably
    cannot refresh a credential with hours of lifetime left, so a timer that
    kept spending it would attempt and decline across the whole reconciled
    guard while reporting that it had tried.
    """
    runner = _AppServerRunner(result=CommandResult(exit_code=0, stdout="{}\n", stderr=""))
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + _DUE_REMAINING),
            _auth_json_with_exp(exp=_NOW + 864_000),
        )
    )

    exit_code = _run(runner=runner, reads=lambda: next(reads))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["outcome"] == "refreshed"
    assert len(runner.calls) == 1
    argv, cwd, request_lines, timeout_seconds = runner.calls[0]
    assert argv == ["codex", "app-server"]
    assert cwd == Path.cwd()
    assert timeout_seconds == 120.0
    messages = [json.loads(line) for line in request_lines]
    assert [message["method"] for message in messages] == [
        "initialize",
        "initialized",
        "account/read",
    ]
    assert messages[-1]["params"] == {"refreshToken": True}


def test_the_refresher_carries_no_sandbox_bypass_and_consults_no_gate() -> None:
    """`account/read` executes nothing, so the full-access path is gone.

    Asserted on the SOURCE rather than on one invocation's argv, because a
    bypass flag reachable on any other branch would still be a full-access
    code path in the refresher.
    """
    source = Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
        "_dispatcher_codex_cred_refresh_command.py"
    ).read_text(encoding="utf-8")

    assert "dangerously-bypass" not in source
    assert "codex_yolo_gate" not in source
    assert "gate_state" not in source
    # And no `codex exec` invocation survives anywhere in it.
    assert '"exec"' not in source


def test_a_credential_above_the_guard_spends_no_request(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not-due means not spent: the timer normally costs nothing."""
    runner = _AppServerRunner(result=CommandResult(exit_code=0, stdout="{}\n", stderr=""))

    exit_code = _run(runner=runner, reads=_auth_json_with_exp(exp=_NOW + _NOT_DUE_REMAINING))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert runner.calls == []
    assert payload["outcome"] == "noop-not-due"
    assert payload["would_invoke_codex"] is False
    assert payload["invoked_codex"] is False


def test_a_due_dry_run_spends_no_request_but_says_it_would(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--dry-run` is the operator's safe probe; it must never spend one."""
    runner = _AppServerRunner(result=CommandResult(exit_code=0, stdout="{}\n", stderr=""))

    exit_code = _run(
        runner=runner,
        reads=_auth_json_with_exp(exp=_NOW + _DUE_REMAINING),
        dry_run=True,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert runner.calls == []
    assert payload["would_invoke_codex"] is True
    assert payload["invoked_codex"] is False


def test_an_unspendable_request_is_reported_as_such_not_as_a_login_demand(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A request that never reached Codex says nothing about the credential.

    The timer's journal is where an operator later reconstructs an incident, so
    conflating "could not run the app-server" with "the credential is stale"
    is what produces a false `codex login` demand hours later.
    """
    runner = _AppServerRunner(
        result=CommandResult(
            exit_code=127,
            stdout="",
            stderr="codex app-server could not be started: codex",
        )
    )

    exit_code = _run(runner=runner, reads=_auth_json_with_exp(exp=_NOW + _DUE_REMAINING))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["renewal_answered"] is False
    assert "could not be started" in payload["message"]


def test_an_answered_request_that_did_not_advance_the_expiry_is_distinguished(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Codex answered and the expiry held: a different fact, recorded as one."""
    runner = _AppServerRunner(result=CommandResult(exit_code=0, stdout="{}\n", stderr=""))
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + _DUE_REMAINING),
            _auth_json_with_exp(exp=_NOW + _DUE_REMAINING),
        )
    )

    exit_code = _run(runner=runner, reads=lambda: next(reads))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["outcome"] == "still-stale"
    assert payload["renewal_answered"] is True


def test_a_malformed_credential_spends_no_request(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unparseable auth.json is a human problem; no request is spent on it."""
    runner = _AppServerRunner(result=CommandResult(exit_code=0, stdout="{}\n", stderr=""))

    exit_code = _run(runner=runner, reads="{")

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert runner.calls == []
    assert payload["outcome"] == "still-stale"
    assert payload["before"]["malformed"] is True


def test_human_output_stays_actionable_without_json(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The human rendering carries the outcome and the remedy ordering."""
    runner = _AppServerRunner(result=CommandResult(exit_code=0, stdout="{}\n", stderr=""))
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + _DUE_REMAINING),
            _auth_json_with_exp(exp=_NOW + _DUE_REMAINING),
        )
    )

    exit_code = _run(runner=runner, reads=lambda: next(reads), as_json=False)

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "outcome: still-stale" in out
    assert "renewal_answered: true" in out
