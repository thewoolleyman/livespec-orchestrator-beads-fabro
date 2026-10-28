"""The shared environment a fixture ``just check`` run is built from drops ``SKIP_TARGETS``.

The delegated gate client exports its authority-reading members into
``SKIP_TARGETS``, so a test process running under that gate carries a skip list
the fixture run must not merge into its own green token.  The helper under test
is the single place every fixture ``just check`` run builds its environment, so
its two promises are asserted here directly: the inherited skip list is dropped,
and everything else the process inherited is kept.
"""

from __future__ import annotations

import pytest

from tests.integration.fixture_check_env import fixture_check_environment


def test_the_helper_drops_an_inherited_skip_targets_and_keeps_the_rest(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An inherited ``SKIP_TARGETS`` never reaches the fixture; other variables do."""
    monkeypatch.setenv("SKIP_TARGETS", "check-branch-protection-alignment")
    monkeypatch.setenv("FIXTURE_CHECK_ENV_KEPT", "kept-value")

    environment = fixture_check_environment()

    assert "SKIP_TARGETS" not in environment
    assert environment["FIXTURE_CHECK_ENV_KEPT"] == "kept-value"
    assert environment["PATH"]


def test_the_helper_applies_overrides_and_lets_a_caller_set_skip_targets_deliberately(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overrides win over inherited values, including a deliberate ``SKIP_TARGETS``."""
    monkeypatch.setenv("SKIP_TARGETS", "inherited-target")

    environment = fixture_check_environment(overrides={"SKIP_TARGETS": "chosen-target"})

    assert environment["SKIP_TARGETS"] == "chosen-target"
