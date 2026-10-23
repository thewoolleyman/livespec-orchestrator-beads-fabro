"""Unit cases for the App-reach preflight's reading, its arms and its records.

The integration-tier binding for the heading this realizes is
`tests/integration/test_adopter_dispatch_app_reach_scenario32.py`, which drives
the REAL pre-dispatch wall. What is here is the per-arm reading: the two shapes a
token supplier fails in, the forge read that cannot name the target, a probe
failure that is not a definite negative, and the two surfaces every arm's reading
projects into.

THE TRI-STATE IS WHAT THESE CASES ARE ABOUT. `reaches` is `True`, `False` or
`None`, and only `False` refuses; each unobservable arm is asserted to answer
`None` rather than `False`, because the whole blast-radius argument of the module
rests on an unmeasurable reading not stopping a dispatch, and every one of these
arms is a plausible place for a build to coerce one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_app_reach_preflight as preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_runtime.github_auth.errors import GithubAppAuthError

_APP_ID = "4277313"
_TARGET = "an-adopter-org/an-adopter-repo"
_TOKEN = "ghs_an_installation_token"
# The token accessor's own refusal detail, which is what the supplier returns in
# place of a callable when the App configuration will not resolve. Named rather
# than written inline at the call site, because the parameter it travels through
# is credential-shaped and a literal there reads to the secret-literal lint as a
# hardcoded password — which it is not, and silencing that reading rather than
# satisfying it is what this repository's own rules forbid.
_SUPPLIER_REFUSAL = "C-mode dispatch refused: GITHUB_PRIVATE_KEY is unset"


@dataclass(kw_only=True)
class _Runner:
    """The `gh` seam, keyed on argv and recording every call."""

    results: dict[tuple[str, ...], CommandResult]
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
        del cwd, timeout_seconds, stdin
        self.calls.append(tuple(argv))
        self.envs.append(env)
        return self.results.get(tuple(argv), CommandResult(exit_code=1, stdout="", stderr="?"))

    envs: list[dict[str, str] | None] = field(default_factory=list)


def _runner(*, identity: CommandResult, probe: CommandResult) -> _Runner:
    return _Runner(
        results={
            tuple(preflight.TARGET_IDENTITY_ARGV): identity,
            tuple(preflight.target_reach_argv(target=_TARGET)): probe,
        }
    )


def _named() -> CommandResult:
    return CommandResult(exit_code=0, stdout=f"{_TARGET}\n", stderr="")


def _reading(*, runner: _Runner, token_supplier: object) -> preflight.AppReachReading:
    return preflight.read_app_reach(
        repo=Path("/workspace"),
        runner=runner,
        environ={"GITHUB_APP_ID": _APP_ID},
        token_supplier=token_supplier,  # pyright: ignore[reportArgumentType]
    )


def test_the_probe_carries_the_minted_token_rather_than_the_ambient_login() -> None:
    """The credential under test is the SERVING App's, not the Dispatcher's own.

    Asserted on the child environment the probe is spawned with, because that is
    the only place the distinction is visible: a probe issued with no token
    override answers for whatever `gh` login the host happens to hold, which for
    a fleet operator reaching an adopter repository is a credential that CAN see
    it — a clean, plausible, entirely wrong reach reading.
    """
    runner = _runner(identity=_named(), probe=CommandResult(exit_code=0, stdout="", stderr=""))

    reading = _reading(runner=runner, token_supplier=lambda: _TOKEN)

    assert reading.reaches is True
    assert runner.envs[-1] == {"GH_TOKEN": _TOKEN, "GITHUB_TOKEN": _TOKEN}


def test_a_forge_that_cannot_name_the_target_is_unobservable_and_probes_nothing() -> None:
    """No target name, no installation-scoped read to issue.

    The empty call tail is the load-bearing half: a build that went on to probe
    `repos/` would get a `404` from the forge and record a DEFINITE NEGATIVE for
    a repository it never named, which is the one false refusal available here.
    """
    runner = _runner(
        identity=CommandResult(exit_code=1, stdout="", stderr="gh: no such repository"),
        probe=CommandResult(exit_code=0, stdout="", stderr=""),
    )

    reading = _reading(runner=runner, token_supplier=lambda: _TOKEN)

    assert reading.reaches is None
    assert reading.target == ""
    assert "no such repository" in reading.detail
    assert runner.calls == [tuple(preflight.TARGET_IDENTITY_ARGV)]


def test_a_forge_naming_nothing_at_exit_zero_is_unobservable_too() -> None:
    """Exit zero with empty output is not a named target.

    Its own case rather than a parameter of the one above, because the two arms
    are reached by DIFFERENT readings of the same result — a non-zero code and an
    empty name — and a build testing only the code admits the empty name through
    to a `repos/` probe.
    """
    runner = _runner(
        identity=CommandResult(exit_code=0, stdout="\n", stderr=""),
        probe=CommandResult(exit_code=0, stdout="", stderr=""),
    )

    reading = _reading(runner=runner, token_supplier=lambda: _TOKEN)

    assert reading.reaches is None
    assert runner.calls == [tuple(preflight.TARGET_IDENTITY_ARGV)]


def test_an_unresolvable_app_configuration_is_unobservable_and_names_the_accessor() -> None:
    """The supplier's own refusal string travels into the detail unchanged.

    It is NOT reported as unreachable: an unusable App environment is a
    credential fault the overlay materializer already refuses, and calling it a
    reach failure would send an operator after a per-tenant server for a fault
    that has nothing to do with one.
    """
    runner = _runner(identity=_named(), probe=CommandResult(exit_code=0, stdout="", stderr=""))

    reading = _reading(runner=runner, token_supplier=_SUPPLIER_REFUSAL)

    assert reading.reaches is None
    assert reading.target == _TARGET
    assert "GITHUB_PRIVATE_KEY is unset" in reading.detail
    assert runner.calls == [tuple(preflight.TARGET_IDENTITY_ARGV)]


def test_a_mint_that_reached_the_forge_and_failed_is_routed_as_data() -> None:
    """A `GithubAppAuthError` is caught at this boundary rather than escaping.

    An exception from inside the pre-dispatch wall is a bug-class escape on the
    one path whose purpose is rendering an actionable refusal, which is the same
    reason `_review_fix_cap` one module over wraps its own ledger read.
    """
    runner = _runner(identity=_named(), probe=CommandResult(exit_code=0, stdout="", stderr=""))

    def _raise() -> str:
        raise GithubAppAuthError(detail="the installation mint answered HTTP 500")

    reading = _reading(runner=runner, token_supplier=_raise)

    assert reading.reaches is None
    assert "HTTP 500" in reading.detail


def test_a_probe_failure_that_is_not_a_definite_negative_stays_unobservable() -> None:
    """A transport fault is not evidence the App cannot see the repository.

    This is the arm the module's blast-radius argument rests on: every dispatch
    in the fleet issues this probe, so a build refusing here turns one forge
    hiccup into a line stop for every repository at once.
    """
    runner = _runner(
        identity=_named(),
        probe=CommandResult(exit_code=1, stdout="", stderr="gh: HTTP 503 (Service Unavailable)"),
    )

    reading = _reading(runner=runner, token_supplier=lambda: _TOKEN)

    assert reading.reaches is None
    assert "503" in reading.detail


@pytest.mark.parametrize("stderr", ["gh: HTTP 404", "gh: Not Found (HTTP 404)"])
def test_either_spelling_of_the_forge_not_found_answer_is_the_definite_negative(
    stderr: str,
) -> None:
    """Both spellings `gh` uses, because the CLI's wording is not ours to pin."""
    runner = _runner(identity=_named(), probe=CommandResult(exit_code=1, stdout="", stderr=stderr))

    reading = _reading(runner=runner, token_supplier=lambda: _TOKEN)

    assert reading.reaches is False


def test_an_empty_selection_reads_nothing_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drain's idle pass costs no forge read.

    The runner is installed and asserted UNTOUCHED rather than omitted, so the
    case shows the preflight returned before resolving its seams rather than that
    the test supplied none.
    """
    runner = _runner(identity=_named(), probe=CommandResult(exit_code=0, stdout="", stderr=""))
    monkeypatch.setattr(preflight, "ShellCommandRunner", lambda: runner)

    refusal = preflight.app_reach_refusal(repo=Path("/workspace"), items=[], journal=None)

    assert refusal is None
    assert runner.calls == []


def test_a_caller_holding_no_journal_still_gets_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record is reached through its own `append`, so a journal-less caller works.

    Same seam the proof-credential gate publishes and for the same reason: the
    preflight is callable from a hermetic test and from a caller holding none
    without a second serializer, and the REFUSAL must not depend on the record
    having been written.
    """
    runner = _runner(
        identity=_named(),
        probe=CommandResult(exit_code=1, stdout="", stderr="gh: Not Found (HTTP 404)"),
    )
    monkeypatch.setattr(preflight, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(preflight, "serving_app_token_supplier", lambda: (lambda: _TOKEN))
    monkeypatch.setenv("GITHUB_APP_ID", _APP_ID)

    refusal = preflight.app_reach_refusal(
        repo=Path("/workspace"), items=[_item()], journal=object()
    )

    assert refusal is not None
    assert _TARGET in refusal


def test_the_token_supplier_passes_the_self_update_accessor_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ONE name this module resolves its credential through, and it is not a copy.

    Asserted by identity against the accessor the self-update module resolves, so
    a build that grew its own `load_github_app_config` call here — a second
    authority on which App is serving — fails rather than agreeing.
    """
    sentinel: object = object()
    monkeypatch.setattr(preflight, "github_token_supplier", lambda: sentinel)

    assert preflight.serving_app_token_supplier() is sentinel


def test_the_journal_record_carries_every_field_of_the_reading() -> None:
    """Including the detail, which is the only field an unobservable arm has.

    A record projecting the verdict alone makes the two `None` arms — an
    unresolvable configuration and an unreachable forge — indistinguishable
    afterwards, and those have different remedies.
    """
    reading = preflight.AppReachReading(
        app_identity=_APP_ID, target=_TARGET, reaches=None, detail="a transport fault"
    )

    record = preflight.app_reach_journal_record(reading=reading)

    assert record == {
        "stage": preflight.APP_REACH_STAGE,
        "app_identity": _APP_ID,
        "target": _TARGET,
        "reaches": None,
        "detail": "a transport fault",
    }


def _item() -> object:
    """The one field the record projection reads off a selected item: its id."""

    @dataclass(frozen=True, kw_only=True)
    class _Item:
        id: str

    return _Item(id="ad-1")
