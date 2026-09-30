"""The dev-tooling ``_vendor`` path must sit BEHIND this repo's own ``_vendor``.

livespec-dev-tooling v1.90.0's wheel ships a PARTIAL ``livespec_runtime``
under ``livespec_dev_tooling/_vendor/`` (the github_budget modules only, no
``work_items``). Every script in ``dev-tooling/checks/`` puts that directory on
``sys.path`` to reach the vendored ``structlog``; when it was front-inserted it
shadowed this repo's full vendored runtime and every check died on
``No module named 'livespec_runtime.work_items'`` (bd-ib-nek3bb). Two guards:
a structural one over the scripts' source, and a behavioral one that loads a
script onto a ``sys.path`` scrubbed of both vendor entries, so the script's own
bootstrap decides the order, and reads that order back.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import livespec_dev_tooling
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS_DIR = _REPO_ROOT / "dev-tooling" / "checks"
_REPO_VENDOR = str(_REPO_ROOT / ".claude-plugin" / "scripts" / "_vendor")
_DT_VENDOR = str(Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor")
_APPEND = "sys.path.append(str(_DT_VENDOR))"
_FRONT_INSERT = "sys.path.insert(0, str(_DT_VENDOR))"


def _scripts_referencing_dev_tooling_vendor() -> list[Path]:
    return sorted(p for p in _CHECKS_DIR.glob("*.py") if "_DT_VENDOR" in p.read_text())


def test_every_check_script_appends_the_dev_tooling_vendor_path() -> None:
    scripts = _scripts_referencing_dev_tooling_vendor()
    assert len(scripts) >= 12, [p.name for p in scripts]
    front_inserting = [p.name for p in scripts if _FRONT_INSERT in p.read_text()]
    not_appending = [p.name for p in scripts if _APPEND not in p.read_text()]
    assert front_inserting == []
    assert not_appending == []


def test_repo_vendor_precedes_dev_tooling_vendor_after_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scrubbed = [entry for entry in sys.path if entry not in {_REPO_VENDOR, _DT_VENDOR}]
    monkeypatch.setattr(sys, "path", scrubbed)
    script = _CHECKS_DIR / "seam_equivalence.py"
    spec = importlib.util.spec_from_file_location("seam_equivalence_vendor_order_probe", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert sys.path.index(_REPO_VENDOR) < sys.path.index(_DT_VENDOR), sys.path
