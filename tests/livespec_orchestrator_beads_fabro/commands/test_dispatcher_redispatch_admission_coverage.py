"""Coverage control for the recorded-factory test double.

The admission scenario's own test module records a failed factory lookup as
``None``.  Exercise that real test-double path as a control: an unreadable run
must remain distinguishable from a successful run with no milestones.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_recorded_factory_double_returns_none_for_an_unreadable_run() -> None:
    source = Path(__file__).with_name("test_dispatcher_redispatch_admission.py")
    spec = importlib.util.spec_from_file_location("redispatch_admission_fixture", source)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    runs_type = vars(module)["_Runs"]
    assert runs_type(succeeded={}).inspect_payload(factory="petri", run_id="missing") is None
