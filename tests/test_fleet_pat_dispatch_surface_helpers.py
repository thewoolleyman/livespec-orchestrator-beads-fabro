"""Coverage for the dispatch-surface PAT guard test helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GUARD_TEST_PATH = _REPO_ROOT / "tests" / "test_fleet_pat_dispatch_surface.py"
_MODULE_NAME = "fleet_pat_dispatch_surface_under_test"


def _load_guard_test() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _GUARD_TEST_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_surface_files_includes_files_directories_and_ignores_missing_paths(
    tmp_path: Path,
) -> None:
    guard_test = _load_guard_test()
    direct_file = tmp_path / "direct.txt"
    direct_file.write_text("safe", encoding="utf-8")
    nested = tmp_path / "surface" / "nested.txt"
    nested.parent.mkdir()
    nested.write_text("safe", encoding="utf-8")

    guard_test._REPO_ROOT = tmp_path  # noqa: SLF001
    guard_test._DISPATCH_SURFACES = (  # noqa: SLF001
        Path("direct.txt"),
        Path("surface"),
        Path("missing"),
    )

    assert guard_test._surface_files() == [direct_file, nested]  # noqa: SLF001
    guard_test.test_dispatch_surfaces_do_not_reference_the_retired_fleet_pat()
