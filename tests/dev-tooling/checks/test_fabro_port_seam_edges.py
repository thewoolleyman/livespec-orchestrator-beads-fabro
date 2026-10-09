"""The Fabro-seam guard's AIM control, driven by widening the exemption.

Its sibling `test_fabro_port_seam` asserts that a real Dispatcher module is
NOT exempt as the repository stands. That is the control's passing arm, and a
passing arm alone cannot show the control is able to fail — which for this one
is the whole question, because widening `FAMILY_PREFIX` is the single cheapest
way to earn this guard's output falsely. A prefix of `_` exempts every private
module in the package, so every finding disappears and the scan prints exactly
what a genuinely clean package prints.

So the widening is performed here, against a seeded throwaway package whose
modules are the real ones, and the guard is required to REFUSE rather than
report that clean scan. The case lives in its own module because the exemption
is read off the check module's own constant: the sibling's cases all share one
loaded module through a fixture, and a monkeypatched prefix leaking into them
would make their clean results meaningless in the opposite direction.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "fabro_port_seam.py"
_PACKAGE_RELPATH = (".claude-plugin", "scripts", "livespec_orchestrator_beads_fabro")

# The widening under test. Every private module in this package opens with it.
_WIDENED_PREFIX = "_"


def _load_check() -> ModuleType:
    assert _CHECK_PATH.is_file()
    spec = importlib.util.spec_from_file_location("fabro_port_seam_aim_control", _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed(*, repo_root: Path, check: ModuleType) -> Path:
    package = repo_root.joinpath(*_PACKAGE_RELPATH)
    source = _REPO_ROOT.joinpath(*_PACKAGE_RELPATH)
    for relpath in (*check.DISCOVERY_ANCHORS, check.AIM_ANCHOR):
        target = package / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(source / relpath, target)
    fixture = check.fixture_path(repo_root=repo_root)
    fixture.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(check.fixture_path(repo_root=_REPO_ROOT), fixture)
    return package


def test_widening_the_family_prefix_fails_the_aim_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check = _load_check()
    package = _seed(repo_root=tmp_path, check=check)

    # The seed is clean BEFORE the widening, so the refusal below cannot be a
    # property of the fixture: without this the case would pass against a guard
    # that refuses every repository it is handed.
    assert check.control_failures(repo_root=tmp_path) == []
    assert check.package_findings(repo_root=tmp_path) == []

    monkeypatch.setattr(check, "FAMILY_PREFIX", _WIDENED_PREFIX)

    # PROOF THE WIDENING LANDED, and that it really does amnesty the Dispatcher:
    # a prefix change that failed to take effect would leave the guard passing
    # for the right reason and this case asserting nothing.
    assert check.is_family_module(path=package / check.AIM_ANCHOR)
    failures = check.control_failures(repo_root=tmp_path)
    assert [failure for failure in failures if failure.startswith("aim control:")]
    assert [failure for failure in failures if check.AIM_ANCHOR in failure]
    monkeypatch.chdir(tmp_path)
    assert check.main() == 1
