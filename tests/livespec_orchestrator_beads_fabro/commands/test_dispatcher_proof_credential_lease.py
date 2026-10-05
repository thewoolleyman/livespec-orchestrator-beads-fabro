"""One run's lease on its provider-minted proof credentials: mint, then revoke.

Covers the MINTING half of `SPECIFICATION/contracts.md`'s
proof-credential-projection clause (ratified v114) at the unit tier: what the
mint leg hands the projection, the two faults it refuses the dispatch for, and
what the revoke leg does — and journals — after a run has ended. The
integration-tier binding for Scenario 134 drives the same two legs end to end
against a hermetic provider double and a real dispatch.

Every case here stands in the RUNNER rather than the provider, because what the
unit tier can establish is the argv, the cwd, the timeout and the environment
one provider command is addressed with. That the two legs compose across a whole
dispatch is the integration module's claim, not this one's.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_management import (
    PROOF_CREDENTIAL_CAPABILITY_ENV,
    PROOF_CREDENTIAL_NAME_ENV,
    PROOF_CREDENTIAL_SCOPE_ENV,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_lease"
_MODULE_PATH = Path(cast("str", _commands_anchor.__file__)).parent / (
    "_dispatcher_proof_credential_lease.py"
)

_NAME = "ACME_MINTED_READER"
_UNMANAGED_NAME = "ACME_STATUS_READER"
_SCOPE = "01M44FA8SK7XTAHVTVEYBF83A3"
_MINT_ARGV = ["/usr/local/bin/acme-admin", "proof-key", "mint"]
_REVOKE_ARGV = ["/usr/local/bin/acme-admin", "proof-key", "revoke"]
_MANAGED = {_NAME: {"mint": list(_MINT_ARGV), "revoke": list(_REVOKE_ARGV)}}


def _module() -> ModuleType:
    """The module under test, asserting it exists before importing it."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _read_only(*, name: str) -> dict[str, str]:
    return {
        "name": name,
        "purpose": "observe the published deployment state of the deliverable",
        "capability": "read_only",
    }


@dataclass(kw_only=True)
class _Call:
    """One recorded provider invocation, as the runner seam received it."""

    argv: list[str]
    cwd: Path
    timeout_seconds: float
    env: dict[str, str] | None


@dataclass(kw_only=True)
class _Runner:
    """A recording `CommandRunner` returning a scripted result per call."""

    results: list[CommandResult]
    calls: list[_Call] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = stdin
        self.calls.append(_Call(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env))
        return self.results[len(self.calls) - 1]


@dataclass(kw_only=True)
class _Journal:
    """A recording stand-in for `JournalFile`, offering only the `append` seam."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _repo(*, tmp_path: Path, declared: object | None, managed: object | None = None) -> Path:
    """A repository whose committed configuration declares proof credentials."""
    dispatcher: dict[str, object] = {} if declared is None else {"proof_credentials": declared}
    if managed is not None:
        dispatcher["proof_credential_management"] = managed
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({PLUGIN_BLOCK: {"dispatcher": dispatcher}}), encoding="utf-8"
    )
    return tmp_path


def test_a_repository_declaring_no_provider_mints_nothing_and_spawns_nothing(
    tmp_path: Path,
) -> None:
    """Every repository in this fleet is in this posture, so it must cost nothing.

    The empty CALL LIST is the load-bearing half: an empty return alone is
    equally consistent with a build that ran a provider command and discarded
    what it printed.
    """
    module = _module()
    runner = _Runner(results=[])

    minted = module.mint_proof_credentials(
        repo=_repo(tmp_path=tmp_path, declared=[_read_only(name=_UNMANAGED_NAME)]),
        scope=_SCOPE,
        runner=runner,
    )

    assert (minted, runner.calls) == ({}, [])


def test_a_managed_declaration_is_minted_and_addressed_through_the_environment(
    tmp_path: Path,
) -> None:
    """The positive control, asserted on the whole invocation the provider receives.

    The ENVIRONMENT is asserted as the exact mapping, not by containment: the
    scope is what makes revoke addressable later, the capability is what makes
    the minted credential read-scoped, and a surplus key would be a fact about
    this run reaching a command that never asked for it. The argv is asserted
    unchanged from the committed declaration, since the three facts travel in
    the environment precisely so nothing run-specific lands in a command line.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path, declared=[_read_only(name=_NAME)], managed=_MANAGED)
    runner = _Runner(results=[_ok(stdout="acme-minted-value\n")])

    minted = module.mint_proof_credentials(repo=repo, scope=_SCOPE, runner=runner)

    assert minted == {_NAME: "acme-minted-value"}
    assert [call.argv for call in runner.calls] == [_MINT_ARGV]
    assert runner.calls[0].cwd == repo
    assert runner.calls[0].timeout_seconds == module.PROOF_CREDENTIAL_MANAGEMENT_TIMEOUT_SECONDS
    assert runner.calls[0].env == {
        PROOF_CREDENTIAL_NAME_ENV: _NAME,
        PROOF_CREDENTIAL_CAPABILITY_ENV: "read_only",
        PROOF_CREDENTIAL_SCOPE_ENV: _SCOPE,
    }


def test_a_mint_that_fails_refuses_the_dispatch_without_echoing_provider_output(
    tmp_path: Path,
) -> None:
    """A failed mint still has a decision to change, so it is returned as a refusal.

    The refusal is asserted NOT to carry stdout or stderr. The mint command's
    stdout IS the credential, so a build that quoted provider output into a
    refusal would publish the value through the journal that records it — and a
    refusal naming the exit code is as much as can honestly be said.
    """
    module = _module()
    runner = _Runner(
        results=[CommandResult(exit_code=4, stdout="acme-leaked-value", stderr="quota exhausted")]
    )

    refusal = module.mint_proof_credentials(
        repo=_repo(tmp_path=tmp_path, declared=[_read_only(name=_NAME)], managed=_MANAGED),
        scope=_SCOPE,
        runner=runner,
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "4" in refusal
    assert "acme-leaked-value" not in refusal
    assert "quota exhausted" not in refusal


def test_a_mint_that_prints_nothing_refuses_rather_than_projecting_an_empty_value(
    tmp_path: Path,
) -> None:
    """Exit 0 is not the whole contract: the mint must PRINT what it minted.

    Refused rather than skipped, because a silently skipped declaration reaches
    the sandbox with no credential at all and the proof stage then fails
    somewhere else entirely, naming a service rather than this configuration.
    """
    module = _module()

    refusal = module.mint_proof_credentials(
        repo=_repo(tmp_path=tmp_path, declared=[_read_only(name=_NAME)], managed=_MANAGED),
        scope=_SCOPE,
        runner=_Runner(results=[_ok(stdout="   \n")]),
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal


def test_a_declaration_the_resolution_refuses_drives_no_provider_at_all(
    tmp_path: Path,
) -> None:
    """Fail-closed: a repository the pre-dispatch gate refuses mints nothing.

    Unreachable in production — the gate runs first on both dispatch paths — and
    asserted anyway, because the opposite shape drives a provider from a
    declaration nobody admitted.
    """
    module = _module()
    runner = _Runner(results=[])

    minted = module.mint_proof_credentials(
        repo=_repo(
            tmp_path=tmp_path,
            declared=[_read_only(name="BEADS_DOLT_PASSWORD")],
            managed=_MANAGED,
        ),
        scope=_SCOPE,
        runner=runner,
    )

    assert (minted, runner.calls) == ({}, [])


def test_the_revoke_leg_runs_the_revoke_argv_and_journals_the_outcome(
    tmp_path: Path,
) -> None:
    """The revoke leg, addressed by the SAME scope the mint used.

    Both halves in one case. The argv must be the REVOKE one — a leg that reran
    the mint command would also exit 0 and journal a successful revoke — and the
    record must say the revoke happened, because a revoke nothing records is
    indistinguishable from one that never ran.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path, declared=[_read_only(name=_NAME)], managed=_MANAGED)
    runner = _Runner(results=[_ok(stdout="")])
    journal = _Journal()

    module.revoke_proof_credentials(repo=repo, scope=_SCOPE, runner=runner, journal=journal)

    assert [call.argv for call in runner.calls] == [_REVOKE_ARGV]
    assert runner.calls[0].env == {
        PROOF_CREDENTIAL_NAME_ENV: _NAME,
        PROOF_CREDENTIAL_CAPABILITY_ENV: "read_only",
        PROOF_CREDENTIAL_SCOPE_ENV: _SCOPE,
    }
    assert journal.records == [
        {
            "stage": module.PROOF_CREDENTIAL_REVOKE_JOURNAL_STAGE,
            "name": _NAME,
            "scope": _SCOPE,
            "revoked": True,
            "exit_code": 0,
        }
    ]


def test_a_revoke_that_fails_is_journaled_as_unrevoked_rather_than_swallowed(
    tmp_path: Path,
) -> None:
    """The run is over, so a failed revoke has no decision left — only visibility.

    The record is what makes a credential outliving its run FINDABLE. Without
    it, the single observable difference between a clean teardown and a provider
    that refused every revoke is a credential nobody is looking for.
    """
    module = _module()
    journal = _Journal()

    module.revoke_proof_credentials(
        repo=_repo(tmp_path=tmp_path, declared=[_read_only(name=_NAME)], managed=_MANAGED),
        scope=_SCOPE,
        runner=_Runner(results=[CommandResult(exit_code=7, stdout="", stderr="gone")]),
        journal=journal,
    )

    assert [(record["revoked"], record["exit_code"]) for record in journal.records] == [(False, 7)]


def test_the_revoke_leg_runs_without_a_journal(tmp_path: Path) -> None:
    """The journal is optional, so the revoke still happens for a caller holding none.

    Asserted on the CALL rather than on a return value, because this leg returns
    nothing: the claim is that the absence of a journal does not cost the
    provider call itself.
    """
    module = _module()
    runner = _Runner(results=[_ok(stdout="")])

    module.revoke_proof_credentials(
        repo=_repo(tmp_path=tmp_path, declared=[_read_only(name=_NAME)], managed=_MANAGED),
        scope=_SCOPE,
        runner=runner,
    )

    assert [call.argv for call in runner.calls] == [_REVOKE_ARGV]


def test_an_absent_scope_revokes_nothing(tmp_path: Path) -> None:
    """With no scope there is nothing to ask the provider to drop.

    Deliberately NOT a revoke under some substitute value: the scope is the only
    thing addressing the provider, so a substituted one would drop a credential
    belonging to a different run.
    """
    module = _module()
    runner = _Runner(results=[])

    module.revoke_proof_credentials(
        repo=_repo(tmp_path=tmp_path, declared=[_read_only(name=_NAME)], managed=_MANAGED),
        scope=None,
        runner=runner,
    )

    assert runner.calls == []
