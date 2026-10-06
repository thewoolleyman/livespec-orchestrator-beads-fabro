"""Shared fixtures for tests/bin/.

Provides `wrapper_runner` — a callable that exec()'s a shebang
wrapper file with stubbed `_bootstrap` + stubbed
`livespec_orchestrator_beads_fabro.<module>.main` + an expected exit code,
asserts the wrapper raises `SystemExit` with that code.

Also supplies the hermetic GitHub App env the two credential-coupled
regressions named in `CREDENTIAL_COUPLED_MODULES` need; see
`apply_hermetic_github_app_env` for why the placeholders always win
rather than deferring to an ambient value.
"""

import runpy
import sys
import types
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"

# `bin/dispatcher.py` requires the GitHub App env BESIDE the tenant secret
# (`bootstrap(required=("BEADS_DOLT_PASSWORD", "GITHUB_APP_ID",
# "GITHUB_PRIVATE_KEY"))`), so the two regressions below — which drive that
# REAL entry point in a child process — refuse before importing anything
# under test whenever those names are absent. The factory projects them into
# the run; CI has no such projection, so there the children exited 3 and the
# tests failed on their own guard assertions ("the candidate failed for some
# reason other than its own removed module"), which is those guards working
# as designed: they decline to pass on a wrong-cause failure.
#
# A non-secret stand-in is sufficient because the `bootstrap()` precondition
# is the ONLY consumer at this boundary: both files pin an in-memory ledger
# (`fake: true` plus `LIVESPEC_BEADS_FAKE`) and contact no tenant, forge or
# notification service, and `load_github_app_config` keeps `app_id` a `str`
# while the PEM is read only at mint time, which no case here reaches. So a
# placeholder App id and key authenticate nothing. This extends the pattern
# those files already use for `BEADS_DOLT_PASSWORD`, whose placeholder is the
# same kind of non-secret literal — and, like that one, it is set
# EXPLICITLY rather than inherited, so the two files run against the same
# values in CI and in the factory instead of against whatever each host
# happens to project.
GITHUB_APP_PLACEHOLDERS: Mapping[str, str] = {
    "GITHUB_APP_ID": "000000",
    "GITHUB_PRIVATE_KEY": "test-not-a-real-secret",
}

# Measured 2026-10-06 across all 174 `tests/bin` tests with both names unset:
# exactly these two files fail, so the scope is the measured population
# rather than a precaution. `bin/drive.py` calls a bare `bootstrap()` and
# requires neither name, so the drive-route case sharing the second file is
# unaffected either way.
CREDENTIAL_COUPLED_MODULES = frozenset(
    {
        "test_payload_canary_subject_is_the_candidate.py",
        "test_payload_public_cli_routes_after_eviction.py",
    }
)


def apply_hermetic_github_app_env(*, module_name: str, setenv: Callable[[str, str], None]) -> None:
    """Set BOTH App names to their explicit placeholders — for the two modules only.

    Unconditional by decision: the placeholders ALWAYS win, and no
    ambient value is consulted. That is the hermetic property rather
    than a convenience — a `setdefault`/`.get()` spelling would leave
    these two regressions running against the factory's REAL projected
    credential and against a stand-in in CI, so the two legs would no
    longer measure the same thing, and whichever leg failed would be the
    one nobody could reproduce. Taking no `environ` parameter is
    deliberate: the function then CANNOT consult ambient state, so the
    rule is enforced by the signature rather than by the body.

    Applying through an injected `setenv` rather than touching
    `os.environ` directly keeps the scope decision a total function of a
    module name, so both arms are testable without reference to the
    ambient process environment or to pytest internals.
    """
    if module_name not in CREDENTIAL_COUPLED_MODULES:
        return
    for name, placeholder in GITHUB_APP_PLACEHOLDERS.items():
        setenv(name, placeholder)


@pytest.fixture(autouse=True)
def _hermetic_github_app_env(
    *, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply the hermetic App env, for the credential-coupled modules only.

    Scoped to the measured population rather than applied blanket, so no
    other credential-refusal test is affected: every other file in
    `tests/bin/` returns untouched and keeps observing a genuinely absent
    credential. `monkeypatch` undoes the set after each test, so nothing
    leaks into the session or into another module's view.
    """
    apply_hermetic_github_app_env(module_name=request.path.name, setenv=monkeypatch.setenv)


def _stub_module(*, name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attr_name, attr_value in attrs.items():
        setattr(module, attr_name, attr_value)
    return module


@pytest.fixture
def wrapper_runner(*, monkeypatch: pytest.MonkeyPatch) -> Callable[[str, str, int], None]:
    """Return `(wrapper_filename, main_module, expected_exit) -> None`."""

    def _run(wrapper_filename: str, main_module: str, expected_exit: int) -> None:
        wrapper_path = _BIN_DIR / wrapper_filename
        # `**_kwargs` so wrappers that pass `extra_required=...` (the
        # Dispatcher's GitHub App env) run against the same stub.
        monkeypatch.setitem(
            sys.modules,
            "_bootstrap",
            _stub_module(name="_bootstrap", bootstrap=lambda **_kwargs: None),
        )
        monkeypatch.setitem(
            sys.modules,
            main_module,
            _stub_module(name=main_module, main=lambda: expected_exit),
        )
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_path(str(wrapper_path), run_name="__main__")
        assert excinfo.value.code == expected_exit

    return _run
