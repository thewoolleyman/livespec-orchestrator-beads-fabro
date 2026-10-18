"""The stable host identity a dispatch claim is stamped with.

Three cases, and the third is the one that matters: a host whose own name
cannot be read is stamped with a NAMED sentinel rather than with an empty
string, because the grading reads that sentinel as naming no host at all. An
empty string would compare EQUAL between two such hosts, so each would
recover the other's claims — the exact cross-host recovery the owning-host
rule exists to forbid.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_dispatching_host.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host"


def test_the_declared_identity_wins_over_the_kernel_hostname() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    resolved = module.dispatching_host(env={module.DISPATCHING_HOST_ENV_VAR: "  declared-host  "})

    assert resolved == "declared-host"


def test_an_empty_declaration_falls_through_to_the_kernel_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    monkeypatch.setattr(module.socket, "gethostname", lambda: " kernel-host ")

    assert module.dispatching_host(env={module.DISPATCHING_HOST_ENV_VAR: "   "}) == "kernel-host"
    # No `env` at all reads the process environment, which is the production
    # path: the declaration is absent on every ordinary host.
    monkeypatch.delenv(module.DISPATCHING_HOST_ENV_VAR, raising=False)
    assert module.dispatching_host() == "kernel-host"


@pytest.mark.parametrize("hostname", ["", "   "])
def test_an_unreadable_hostname_is_named_rather_than_left_empty(
    *,
    hostname: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    monkeypatch.setattr(module.socket, "gethostname", lambda: hostname)

    assert module.dispatching_host(env={}) == module.UNKNOWN_DISPATCHING_HOST


def test_a_raising_hostname_call_is_named_too(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module(_MODULE_NAME)

    def _refuse() -> str:
        raise OSError("no hostname")

    monkeypatch.setattr(module.socket, "gethostname", _refuse)

    assert module.dispatching_host(env={}) == module.UNKNOWN_DISPATCHING_HOST
