"""Tests for the Petri-era client-version refusal the factory-graph gate applies."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

_CHECKS_DIR = Path(__file__).resolve().parents[3] / "dev-tooling" / "checks"


def _module() -> ModuleType:
    if str(_CHECKS_DIR) not in sys.path:
        sys.path.insert(0, str(_CHECKS_DIR))
    return importlib.import_module("_fabro_client_version")


def test_the_client_version_module_exposes_its_public_entry_points() -> None:
    module = _module()

    assert sorted(module.__all__) == ["client_version", "is_petri_era_version", "version_refusal"]


def test_an_unparseable_version_is_refused_naming_the_binary() -> None:
    refusal = _module().version_refusal(binary="/opt/fabro", version=None)

    assert refusal == "Petri-era client control: /opt/fabro did not report a parseable version"


def test_a_pre_petri_version_is_refused_naming_the_floor() -> None:
    refusal = _module().version_refusal(binary="/opt/fabro", version="0.254.0")

    assert refusal == "Petri-era client control: fabro 0.254.0 is older than required 0.396.0"


def test_a_petri_era_version_is_not_refused() -> None:
    assert _module().version_refusal(binary="/opt/fabro", version="0.396.0-nightly.0") is None
    assert _module().version_refusal(binary="/opt/fabro", version="0.408.0-nightly.0") is None
