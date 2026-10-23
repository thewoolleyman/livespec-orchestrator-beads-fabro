"""The currency probe authenticates as the SELECTED factory's own client.

The Fabro-currency-admission clause of `SPECIFICATION/contracts.md` evaluates
each configured target against its own serving integration commit, and
`_dispatcher_fabro_currency_sources.serving_integration_commit` is the one read
that resolves it. That read inherits the DISPATCHING PROCESS's environment, and
on a governed repository whose credential wrapper routes its own adopter Fabro
that environment carries a FOREIGN `FABRO_HOME` — a Fabro home holding no login
for the selected factory. The client then reads its credential out of that home,
the server answers `Authentication required.` with no `git_sha`, and admission
refuses with `serving-build-unidentified` before claim.

MEASURED 2026-10-23 on the control node, carrier-petri-v0.382-adeefec4c against
`https://gmktec-xubuntu.perch-rudd.ts.net:32276`: the host default home reports
`server.git_sha` `9f6c38f`, the same home plus a bogus bare `FABRO_DEV_TOKEN`
still reports `9f6c38f`, and an EMPTY `FABRO_HOME` reports
`server.error: Authentication required.` with no commit. So the condition is the
foreign home and not the bare token — and passing the factory's own token through
`FABRO_DEV_TOKEN` is NOT a fix either, because `fabro version` reads `auth.json`
under `FABRO_HOME` rather than that variable.

THE FAKE RUNNER APPLIES `child_env` RATHER THAN RECORDING THE DELTA, which is
what makes these claims about the environment the client would actually run in.
The delta a caller passes is a DELTA — a `None` value REMOVES a name — so a test
that asserted on the mapping alone would pass for a delta naming the right names
with the wrong values, and could not observe the removal at all.

AND THE FIRST CASE'S ANSWER DEPENDS ON THAT CHILD ENVIRONMENT, which is the
control that keeps it from passing on an unscrubbed probe: a runner answering the
version payload unconditionally reports an identified commit whether or not the
foreign home reached the client, so the one reading the defect turns on would be
invisible.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_sources import (
    serving_integration_commit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import child_env

_REPO = Path("/repo")
_SERVER = "https://gmktec-xubuntu.perch-rudd.ts.net:32276"
_FABRO_BIN = "/home/ubuntu/.fabro/bin/fabro"
_SERVING_COMMIT = "9f6c38f"

# The dolt-server credential wrapper's own `export_routing` value, measured on
# the control node: a Fabro home whose `auth.json` holds logins for
# `http://127.0.0.1:32286` and the hp factory only, and none for the selected
# petri factory.
_FOREIGN_HOME = "/home/ubuntu/.fabro-dolt-server"

# The wrapper's bare token, beside its foreign home. It does not cause the
# refusal on its own, which is exactly why it must not be the only thing a fix
# reaches for.
_FOREIGN_DEV_TOKEN = "dolt-server-wrapper-token"


def _version_json() -> str:
    """`fabro version --json` as the selected factory's server answers it."""
    return json.dumps(
        {
            "client": {"version": "0.382.0", "git_sha": "adeefec"},
            "server": {"address": _SERVER, "version": "0.382.0", "git_sha": _SERVING_COMMIT},
        }
    )


def _unauthenticated_json() -> str:
    """The same read, as the server answers a client with no login for it."""
    return json.dumps(
        {
            "client": {"version": "0.382.0", "git_sha": "adeefec"},
            "server": {"error": "Authentication required."},
        }
    )


@dataclass(kw_only=True)
class _Runner:
    """A `fabro version` seam that answers from the CHILD environment it is given."""

    child_environments: list[dict[str, str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del argv, cwd, timeout_seconds, stdin
        # Asserted rather than defaulted: the probe always hands this seam a
        # delta, so a `None` arm here is an arm no call can reach — and an
        # unreachable arm in a fake is a fake that has stopped describing the
        # seam it stands in for.
        assert env is not None
        resolved = child_env(delta=env)
        self.child_environments.append(resolved)
        authenticated = resolved.get("FABRO_HOME") != _FOREIGN_HOME
        return CommandResult(
            exit_code=0,
            stdout=_version_json() if authenticated else _unauthenticated_json(),
            stderr="",
        )


def _factory() -> FactoryTarget:
    return FactoryTarget(name="petri", server=_SERVER, dev_token=None)


def _probe(*, runner: _Runner) -> str | None:
    return serving_integration_commit(
        factory=_factory(), fabro_bin=_FABRO_BIN, runner=runner, cwd=_REPO
    )


def test_the_stood_in_server_withholds_the_commit_from_a_client_in_the_foreign_home() -> None:
    """The control on the SEAM, and the load-bearing case of this module.

    Every other case here asserts an absence or a resolved commit, and all of
    them pass against a seam that answers the version payload whatever child
    environment it is handed. This one establishes that the seam can still
    return the REFUSING answer — which is the question a passing probe cannot
    answer, and the reading the defect itself turned on.
    """
    runner = _Runner()

    result = runner.run(
        argv=[_FABRO_BIN, "version", "--json"],
        cwd=_REPO,
        timeout_seconds=1.0,
        env={"FABRO_HOME": _FOREIGN_HOME},
    )

    assert json.loads(result.stdout)["server"] == {"error": "Authentication required."}


def test_a_foreign_fabro_home_in_the_dispatching_environment_does_not_reach_the_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect's own case: the wrapper's home is set and the commit resolves.

    Before the scrub the client read its credential out of that home, the server
    answered `Authentication required.` with no `git_sha`, and the gate refused
    the dispatch as `serving-build-unidentified` before any claim.
    """
    monkeypatch.setenv("FABRO_HOME", _FOREIGN_HOME)
    runner = _Runner()

    commit = _probe(runner=runner)

    assert commit == _SERVING_COMMIT
    assert "FABRO_HOME" not in runner.child_environments[0]


def test_the_probe_child_environment_carries_no_inherited_bare_dev_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper's other Fabro credential, scrubbed for the same reason.

    The probe authenticates to the selected factory with THAT factory's own
    client settings, so a bare token the target wrapper exported for its own
    adopter Fabro must not address this read.
    """
    monkeypatch.setenv("FABRO_DEV_TOKEN", _FOREIGN_DEV_TOKEN)
    runner = _Runner()

    _ = _probe(runner=runner)

    assert "FABRO_DEV_TOKEN" not in runner.child_environments[0]


def test_the_probe_child_environment_still_binds_the_selected_factorys_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scrub must not take the target binding with it.

    `fabro version` takes no per-subcommand `--server` on the pinned engine, so
    `FABRO_SERVER` is the only thing that points this read at the selected
    factory; an unaddressed read reports whichever server the host's ambient
    configuration names.
    """
    monkeypatch.setenv("FABRO_HOME", _FOREIGN_HOME)
    monkeypatch.setenv("FABRO_DEV_TOKEN", _FOREIGN_DEV_TOKEN)
    runner = _Runner()

    _ = _probe(runner=runner)

    assert runner.child_environments[0]["FABRO_SERVER"] == _SERVER
