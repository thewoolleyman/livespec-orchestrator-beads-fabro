"""Regression coverage for the livespec-runtime vendor boundary."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_spec_stated_judgement_surface_imports_from_the_vendored_runtime() -> None:
    """The plugin bundle supplies the complete shared judgement surface."""
    vendor_module = Path(".claude-plugin/scripts/_vendor/livespec_runtime/spec_stated.py")

    assert vendor_module.is_file()

    module = importlib.import_module("livespec_runtime.spec_stated")

    assert Path(module.__file__).resolve().is_relative_to(vendor_module.parent.resolve())
    assert callable(module.judge)
    assert callable(module.classify)
    assert callable(module.parse_verdict)
