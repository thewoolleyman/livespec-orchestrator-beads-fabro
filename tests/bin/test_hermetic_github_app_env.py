"""Contract coverage for `conftest.apply_hermetic_github_app_env`.

Two properties of the hermetic App-env support are worth pinning, and
neither is observable from the suite's ordinary behaviour.

The first is that the placeholders ALWAYS win. A `setdefault`/`.get()`
spelling would leave the two credential-coupled regressions running
against the factory's real projected credential and against a stand-in
in CI — the legs would stop measuring the same thing, and whichever one
failed would be the one nobody could reproduce. Nothing in a green run
reports that, because each leg passes while exercising only its own half.

The second is that the scope stays exactly the two measured modules, so
no other credential-refusal test is affected. Those tests observe a
GENUINELY absent credential on purpose; a silently widened allowlist
would hand them one and they would still pass, having quietly stopped
testing the refusal they exist for.

Both cases drive the applier as the total function of a module name and
an injected `setenv` that it is, against a recording double. That makes
each property observable on any host, under either uid, in one run —
and the first case deliberately plants a DIFFERENT ambient value first,
so a regression that consulted the environment fails here in both
environments rather than only in the factory.

Asserts nothing about `_payload.py` and drives no child process — test
support robustness, in the spirit of `test_payload_retention_harness.py`
and `test_payload_candidate_provenance_harness.py`, which likewise cover
scaffolding this repository measures like any other `tests/` file. Not a
Red, and not evidence for any work-item assertion.
"""

import importlib.util
import types
from collections.abc import Callable
from pathlib import Path

import pytest

_CONFTEST_PATH = Path(__file__).with_name("conftest.py")
_CONFTEST_MODULE_NAME = "tests_bin_conftest_for_coverage"

_APP_NAMES = ("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY")
# One of the two files the support is scoped to, and one that must stay
# untouched. Both are real `tests/bin/` modules, so a rename that broke the
# allowlist would surface here rather than in a silent no-op.
_COUPLED_MODULE = "test_payload_canary_subject_is_the_candidate.py"
_UNCOUPLED_MODULE = "test_payload_provisioning_refusal.py"


def _conftest() -> types.ModuleType:
    """Load `tests/bin/conftest.py` by path, so its pytest module identity is irrelevant.

    Three `conftest.py` files live under `tests/` with no `__init__.py`
    beside them, so a plain `import conftest` is ambiguous. The by-path
    load is the same idiom the two harness files named above use.
    """
    spec = importlib.util.spec_from_file_location(_CONFTEST_MODULE_NAME, _CONFTEST_PATH)
    assert spec is not None, f"tests/bin/conftest.py is not loadable: {_CONFTEST_PATH}"
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _recording_setenv(recorded: dict[str, str]) -> Callable[[str, str], None]:
    """Return a `setenv` double that records rather than mutating the process."""

    def _setenv(name: str, value: str) -> None:
        recorded[name] = value

    return _setenv


def test_both_app_names_are_always_set_to_the_explicit_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A coupled module gets the declared placeholders, never an ambient value.

    An ambient value is planted first, and it must NOT win. That is what
    makes this case fail under a `setdefault`/`.get()` regression in CI
    as well as in the factory: without the planted value, an
    environment-consulting implementation would be indistinguishable
    from this one wherever the names are genuinely absent.
    """
    conftest = _conftest()
    for name in _APP_NAMES:
        monkeypatch.setenv(name, "ambient-value-that-must-not-win")
    recorded: dict[str, str] = {}

    conftest.apply_hermetic_github_app_env(
        module_name=_COUPLED_MODULE, setenv=_recording_setenv(recorded)
    )

    assert recorded == dict(conftest.GITHUB_APP_PLACEHOLDERS), (
        "the coupled module must receive exactly the declared placeholders; an "
        "ambient value winning means the factory and CI legs are no longer "
        f"measuring the same thing: {recorded}"
    )
    assert set(recorded) == set(_APP_NAMES), (
        "both names the Dispatcher wrapper requires must be set, or the child "
        f"still refuses before importing anything under test: {sorted(recorded)}"
    )
    assert all(value for value in recorded.values()), (
        "an empty placeholder counts as missing to the App config boundary, so "
        f"it would refuse exactly as absence does: {recorded}"
    )


def test_no_other_module_is_affected() -> None:
    """An uncoupled module is left entirely alone.

    The other credential-refusal tests observe a genuinely absent
    credential deliberately. Handing them one would not fail them — it
    would quietly stop them testing the refusal they exist for — so the
    narrow scope is itself the contract.
    """
    conftest = _conftest()
    recorded: dict[str, str] = {}

    conftest.apply_hermetic_github_app_env(
        module_name=_UNCOUPLED_MODULE, setenv=_recording_setenv(recorded)
    )

    assert recorded == {}, (
        "a module outside the measured population had its environment changed, "
        f"so some other credential-refusal test is no longer observing absence: {recorded}"
    )


def test_the_scope_is_exactly_the_two_measured_modules() -> None:
    """The allowlist holds precisely the two files measured as credential-coupled.

    Pinned as an equality rather than a membership test so the scope
    cannot widen silently: a third entry is exactly the change that
    would blind another refusal test, and it would otherwise produce no
    failing signal anywhere.
    """
    conftest = _conftest()
    measured = frozenset(
        {
            "test_payload_canary_subject_is_the_candidate.py",
            "test_payload_public_cli_routes_after_eviction.py",
        }
    )

    assert measured == conftest.CREDENTIAL_COUPLED_MODULES, (
        "the credential-coupled population changed; re-measure it with both "
        "names unset before widening or narrowing this set: "
        f"{sorted(conftest.CREDENTIAL_COUPLED_MODULES)}"
    )
