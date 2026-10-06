"""Coverage for the frozen cycle-13 regression's own scaffolding.

`test_payload_candidate_provenance_on_reselection.py` is FROZEN across its
Red-Green pair, and this repository measures coverage over `tests/` like any
other tree. Its `_candidate` helper has an arm its four cases cannot reach:
every one of them resolves a candidate from an environment that DOES carry a
launcher record, so the branch that removes the variable when no record is
present is never executed.

The established remedy here is to drive the frozen file's scaffolding from a
separate harness rather than edit it — the same thing
`test_payload_retention_harness.py` does for the frozen retention
regression's `_wait_for`. The frozen module is loaded BY PATH so its module
name is irrelevant and nothing imports it as a test.

This asserts nothing about `_payload.py`. It is harness robustness, not
product Red, and it must not be cited as evidence for any work-item
assertion. What it DOES pin is that the no-record arm resolves the candidate
through the `__file__` fall-through rather than raising — which is the
behaviour an in-repo CLI run and a fresh checkout both take.
"""

import importlib.util
import types
from pathlib import Path

import pytest

_FROZEN_TEST_PATH = Path(__file__).with_name("test_payload_candidate_provenance_on_reselection.py")
_FROZEN_MODULE_NAME = "frozen_candidate_provenance_for_coverage"


def _frozen_module() -> types.ModuleType:
    """Load the frozen regression by path, so its own module name is irrelevant."""
    spec = importlib.util.spec_from_file_location(_FROZEN_MODULE_NAME, _FROZEN_TEST_PATH)
    assert spec is not None, f"the frozen regression is not loadable: {_FROZEN_TEST_PATH}"
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_candidate_helper_handles_an_environment_with_no_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The arm the frozen file's own cases cannot reach: no launcher record.

    With neither a harness export nor a launcher record, `plugin_root()` falls
    back to walking up from its own `__file__`, which in an unretained
    in-repo run is the plugin root. The helper must reach that answer rather
    than raise on the missing key.
    """
    module = _frozen_module()

    resolved = module._candidate(  # noqa: SLF001 - the frozen file's own scaffolding is the subject.
        monkeypatch=monkeypatch, environ={}
    )

    assert (
        resolved.name == ".claude-plugin"
    ), f"the no-record arm did not fall back to the plugin root: {resolved}"
